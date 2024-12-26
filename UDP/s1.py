import socket
import os
import threading
import struct
import hashlib

HOST = '0.0.0.0'
PORT = 12345
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(CUR_PATH, 'files')
FILELIST = os.path.join(CUR_PATH, 'filelist.txt')
BUFFER = 4096
FORMAT = 'utf-8'
MB = 1024 * 1024
TIMEOUT = 1  # Timeout for retransmissions

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

def make_packet(seq_num, data):
    header = struct.pack('!I', seq_num)
    checksum_value = calculate_checksum(header + data)
    checksum_value = checksum_value.encode() if isinstance(checksum_value, str) else checksum_value
    packet = struct.pack('!32s', checksum_value) + header + data
    return packet

def send_rdt(server, packet, client_addr):
    while True:
        server.sendto(packet, client_addr)
        try:
            server.settimeout(TIMEOUT)
            ack, _ = server.recvfrom(BUFFER)
            ack_number = struct.unpack('!I', ack)[0]
            return ack_number
        except socket.timeout:
            print("Timeout, resending packet")

def recv_rdt(server):
    while True:
        try:
            data, addr = server.recvfrom(BUFFER)
            packet_checksum = struct.unpack('!32s', data[:32])[0].decode()
            data = data[32:]
            if calculate_checksum(data) == packet_checksum:
                seq_num = struct.unpack('!I', data[:4])[0]
                ack = struct.pack('!I', seq_num + 1)
                server.sendto(ack, addr)
                data = data[4:]
                return data, addr
            else:
                print("Checksum mismatch, discarding packet")
        except socket.timeout:
            continue

def send_file_chunk(server, client_addr, file, offset, chunk, seq_num, request_id):
    with open(os.path.join(FOLDER, file), 'rb') as f:
        totalSent = 0
        f.seek(offset)
        print(seq_num)
        while totalSent < chunk:
            part = f.read(min(BUFFER - 4 - 32, chunk - totalSent))
            if not part:
                break
            
            packet = make_packet(seq_num, part)
            # print(f"Sending packet {seq_num} with size {len(packet)}")
            
            ack_number = send_rdt(server, packet, client_addr)
            if ack_number == seq_num + 1:
                seq_num += 1
                totalSent += len(part)
            else:
                f.seek(offset + totalSent - len(part))
                totalSent -= len(part)
        active_requests.remove(request_id)

active_requests = set()

def handle_client(server, client_addr, files):
    buffer = ""
    delimiter = "\n"
    while True:
        try:
            data, addr = recv_rdt(server)
            if not data:
                break
            buffer += data.decode(FORMAT)

            while delimiter in buffer:
                request, buffer = buffer.split(delimiter, 1)
                print(f"Received request from {client_addr}: {request}")
                if request == 'FILELIST':
                    files = get_file_list()
                    msg_file_list = make_packet(0, '\n'.join(files).encode(FORMAT) + delimiter.encode(FORMAT))
                    ack = send_rdt(server, msg_file_list, client_addr)
                    if ack != 1:
                        print("Failed to send file list.")
                        break
                
                elif request.startswith('SIZE'):
                    fileName = request.split()[1]
                    print(f"Request for file size: {fileName}")
                    data = str(os.path.getsize(os.path.join(FOLDER, fileName))).encode(FORMAT) + delimiter.encode(FORMAT)
                    msg_size = make_packet(0, data)
                    ack = send_rdt(server, msg_size, client_addr)
                    if ack != 1:
                        print("Failed to send file size.")
                        break
                
                elif request.startswith("REQUEST"):
                    info = request.split()
                    fileName = info[1]
                    offset = int(info[2])
                    chunk = int(info[3])
                    seq_num = int(info[4])
                    print(f"Request for file chunk: {fileName} {offset} {chunk} {seq_num}")
                    request_id = (addr, fileName, offset, chunk, seq_num)
                    
                    if os.path.exists(os.path.join(FOLDER, fileName)) and request_id not in active_requests:
                        active_requests.add(request_id)
                        send_file_chunk(server, addr, fileName, offset, chunk, seq_num, request_id)
                    else:
                        print(f"File {fileName} not found or request already active.")
                        break
                
                elif request.startswith("EXIT"):
                    return
        except Exception as e:
            print(f"Error processing request from {client_addr}: {e}")
            break

def run():
    files = scan_available_files()
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((HOST, PORT))
    print(socket.gethostbyname(socket.gethostname()))
    print(f"Server is running on port: {PORT}.\n")
    try:
        data, addr = recv_rdt(server)
        if data.decode(FORMAT) == "CONNECT":
            print(f"Connection request from {addr}")
            welcome = "Welcome to the server!\n".encode(FORMAT)
            msg_welcome = make_packet(0, welcome)
            ack = send_rdt(server, msg_welcome, addr)
            if ack != 1:
                print(f"Failed to send welcome message to {addr}")
                return
        else:
            print(f"Invalid connection request from {addr}")
            return
        
        
        
        #while True:
        data, addr = recv_rdt(server)
        if data.decode(FORMAT).startswith("HANDLE"):
            print(f"Client {addr} connected.\n")
            handle_client(server, addr, files)
            
            
    finally:
        print("Server shutting down...")
        server.close()

if __name__ == "__main__":
    run()