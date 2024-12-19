import socket
import os
import threading
import struct
import time
import hashlib

HOST = '0.0.0.0'
PORT = 12345
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(CUR_PATH, 'files')
FILELIST = os.path.join(CUR_PATH, 'filelist.txt')
BUFFER = 1024
FORMAT = 'utf-8'
MB = 1024 * 1024
TIMEOUT = 10  # Timeout for retransmissions

def get_file_list():
    fileList = []
    with open(FILELIST, 'r') as list:
        for file in list:
            if file:
                fileList.append(file.strip())
    return fileList

def scan_available_files():
    scannedFiles = []
    folder = os.listdir(FOLDER)
    for file in folder:
        if os.path.isfile(os.path.join(FOLDER, file)):
            scannedFiles.append(file)
    with open(FILELIST, 'w') as list:
        for file in scannedFiles:
            list.write(f"{file} {round(os.path.getsize(os.path.join(FOLDER, file)) / MB, 2)}MB\n")
    return scannedFiles

def calculate_checksum(data):
    return hashlib.md5(data).hexdigest()

def send_file_chunk(server, client_addr, file, offset, chunk, seq_num, request_id):
    with open(os.path.join(FOLDER, file), 'rb') as f:
        totalSent = 0
        f.seek(offset)
        while totalSent < chunk:
            part = f.read(min(BUFFER - 4 - 32, chunk - totalSent))
            if not part:
                break
            
            # Create packet with checksum and sequence number
            header = struct.pack('!I', seq_num)
            checksum = calculate_checksum(header + part)
            checksum = checksum.encode() if isinstance(checksum, str) else checksum
            packet = struct.pack('!32s', checksum) + header + part
            print(f"Sending packet {seq_num} with size {len(packet)}")
            print(packet)
            
            # Send packet
            server.sendto(packet, client_addr)
            print(f"Sent packet {seq_num}")
            totalSent += len(part)
            ack, _ = server.recvfrom(BUFFER)
            print(f"Received ACK {ack}")
            
            # Wait for ACK
            try:
                server.settimeout(TIMEOUT)
                ack, _ = server.recvfrom(BUFFER)
                print(f"Received ACK {ack}")
                ack_number = struct.unpack('!I', ack)[0]
                
                if ack_number == seq_num + 1:
                    seq_num += 1
                else:
                    raise Exception("Incorrect ACK received, resending packet")
            except:
                f.seek(offset + totalSent - len(part))
                totalSent -= len(part)
                print("Timeout, resending packet")
        f.close()
        active_requests.remove(request_id)

active_requests = set()

def handle_client(server, client_addr, files):
    buffer = ""
    delimiter = "\n"
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
                    server.sendto('\n'.join(files).encode(FORMAT) + delimiter.encode(FORMAT), client_addr)
                elif request.startswith('SIZE'):
                    fileName = request.split()[1]
                    print(f"Request for file size: {fileName}")
                    server.sendto(str(os.path.getsize(os.path.join(FOLDER, fileName))).encode(FORMAT) + delimiter.encode(FORMAT), client_addr)
                elif request.startswith('REQUEST'):
                    info = request.split()
                    fileName = info[1]
                    offset = int(info[2])
                    chunk = int(info[3])
                    seq_num = int(info[4])
                    print(f"Request for file chunk: {fileName} {offset} {chunk} {seq_num}")
                    request_id = (client_addr, fileName, offset, chunk, seq_num)
                    print(f"Request for file chunk: {fileName} {offset} {chunk} {seq_num}")
                    
                    if os.path.exists(os.path.join(FOLDER, fileName)) and request_id not in active_requests:
                        active_requests.add(request_id)
                        threading.Thread(target=send_file_chunk, args=(server, client_addr, fileName, offset, chunk, seq_num, request_id)).start()
                elif request.startswith("EXIT"):
                    print(f"Client {client_addr} disconnected.\n")
                    return
        except Exception as e:
            print(f"Error processing request from {client_addr}: {e}")
            break

def run():
    files = scan_available_files()
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((HOST, PORT))
    print(f"Server is running on port: {PORT}.\n")
    try:
        while True:
            data, addr = server.recvfrom(BUFFER)
            print(f"Received data from {addr}: {data.decode(FORMAT)}")
            if data.decode(FORMAT).startswith("CONNECT"):
                server.sendto("CONNECTED".encode(FORMAT), addr)
            handle_client(server, addr, files)
    finally:
        server.close()

if __name__ == "__main__":
    run()