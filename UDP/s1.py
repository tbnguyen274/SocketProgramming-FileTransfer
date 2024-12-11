import socket
import threading
import os
import struct
import time

# Configuration Constants
HOST = '0.0.0.0'
PORT = 12345
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(CUR_PATH, 'files')
FILELIST = os.path.join(CUR_PATH, 'filelist.txt')
BUFFER = 1024
FORMAT = 'utf-8'
MB = 1024 * 1024
TIMEOUT = 1  # Timeout for retransmissions

# Utility Functions
def checksum(data):
    """Calculate checksum for error detection."""
    return sum(data) % 256

def get_file_list():
    """Retrieve the list of files available on the server."""
    file_list = []
    with open(FILELIST, 'r') as list_file:
        for line in list_file:
            if line.strip():
                file_list.append(line.strip())
    return file_list

def scan_files():
    """Scan the server folder and update the file list."""
    scanned_files = []
    folder_content = os.listdir(FOLDER)
    for file in folder_content:
        file_path = os.path.join(FOLDER, file)
        if os.path.isfile(file_path):
            size_mb = round(os.path.getsize(file_path) / MB, 2)
            scanned_files.append(file)
    with open(FILELIST, 'w') as list_file:
        for file in scanned_files:
            size_mb = round(os.path.getsize(os.path.join(FOLDER, file)) / MB, 2)
            list_file.write(f"{file} {size_mb}MB\n")
    return scanned_files

def send_file_chunk(server, client_addr, file, offset, chunk, seq_num):
    """Send a file chunk to the client with retransmission on failure."""
    try:
        with open(os.path.join(FOLDER, file), 'rb') as f:
            total_sent = 0
            f.seek(offset)

            while total_sent < chunk:
                part = f.read(min(BUFFER - 8, chunk - total_sent))
                if not part:
                    break

                # Create packet with checksum and sequence number
                header = struct.pack('!I', seq_num)
                packet = header + part
                packet_checksum = checksum(packet)
                packet = struct.pack('!I', packet_checksum) + packet

                # Send packet
                server.sendto(packet, client_addr)

                # Wait for acknowledgment
                try:
                    server.settimeout(TIMEOUT)
                    ack, _ = server.recvfrom(BUFFER)
                    ack_seq_num = struct.unpack('!I', ack)[0]
                    if ack_seq_num == seq_num:
                        total_sent += len(part)
                        seq_num += 1
                    else:
                        print(f"ACK mismatch for chunk: {seq_num}, retrying...")
                except socket.timeout:
                    print(f"Timeout for chunk: {seq_num}, retrying...")
                    continue
    except Exception as e:
        print(f"Error sending chunk: {e}")

def process_client(server, client_addr):
    """Handle requests from a client."""
    buffer = ""
    delimiter = "\n"
    files = get_file_list()

    while True:
        try:
            data, addr = server.recvfrom(BUFFER)
            if not data:
                break
            buffer += data.decode(FORMAT)

            while delimiter in buffer:
                request, buffer = buffer.split(delimiter, 1)
                print(f"Received request from {client_addr}: {request}")

                if request == 'FILELIST':
                    files = get_file_list()
                    print(files)
                    response = "\n".join(files) + delimiter
                    server.sendto(response.encode(FORMAT), client_addr)

                elif request.startswith('SIZE'):
                    filename = request.split()[1]
                    file_path = os.path.join(FOLDER, filename)
                    if os.path.exists(file_path):
                        size = os.path.getsize(file_path)
                        server.sendto(f"{size}".encode(FORMAT), client_addr)
                    else:
                        server.sendto(b"ERROR: File not found", client_addr)

                elif request.startswith('REQUEST'):
                    _, filename, offset, chunk, seq_num = request.split()
                    offset, chunk, seq_num = int(offset), int(chunk), int(seq_num)
                    if os.path.exists(os.path.join(FOLDER, filename)):
                        threading.Thread(
                            target=send_file_chunk,
                            args=(server, client_addr, filename, offset, chunk, seq_num)
                        ).start()

                elif request.startswith("EXIT"):
                    print(f"Client {client_addr} disconnected.")
                    return
        except Exception as e:
            print(f"Error processing client request: {e}")
            break

def run():
    """Start the UDP server."""
    os.makedirs(FOLDER, exist_ok=True)
    scan_files()

    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((HOST, PORT))
    print(f"Server is running on {HOST}:{PORT}")

    try:
        while True:
            data, addr = server.recvfrom(BUFFER)
            if data.decode(FORMAT).startswith("CONNECT"):
                server.sendto("CONNECTED".encode(FORMAT), addr)
                process_client(server, addr)
    finally:
        server.close()

if __name__ == "__main__":
    run()
