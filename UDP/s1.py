import socket
import os
import threading
import struct
import hashlib
import logging
from utils import *

HOST = socket.gethostbyname(socket.gethostname())
PORT = 12345
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(CUR_PATH, 'files')
FILE_LIST = os.path.join(CUR_PATH, 'filelist.txt')
BUFFER_SIZE = 1024 * 4
FORMAT = 'utf-8'
MB = 1024 * 1024
TIMEOUT = 3  # Timeout for retransmissions

def get_file_list():
    fileList = []
    scan_available_files()

    with open(FILE_LIST, 'r') as list:
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
    with open(FILE_LIST, 'w') as list:
        for file in scannedFiles:
            list.write(f"{file} {round(os.path.getsize(os.path.join(FOLDER, file)) / MB, 2)}MB\n")
    # return scannedFiles

def send_file_chunk(server, client_addr, file, offset, chunk, seq_num, request_id):
    with open(os.path.join(FOLDER, file), 'rb') as f:
        totalSent = 0
        f.seek(offset)
        print(seq_num)
        saved = -2
        count_saved = 0
        while totalSent < chunk:
            part = f.read(min(BUFFER_SIZE - 4 - 32, chunk - totalSent))
            if not part:
                break
            
            packet = make_packet(seq_num, part)
            # print(f"Sending packet {seq_num} with size {len(packet)}")
            
            ack_number = send_rdt(server, client_addr, packet)
            if saved == ack_number:
                count_saved += 1
                if count_saved == 1:
                    exit()
            else:
                saved = ack_number
                count_saved = 0
            
            if ack_number == seq_num + 1:
                seq_num += 1
                totalSent += len(part)
            else:
                f.seek(offset + totalSent - len(part))
                totalSent -= len(part)
        active_requests.remove(request_id)

active_requests = set()

def handle_client(server, client_addr):
    buffer = ""
    delimiter = "\n"
    while True:
        try:
            data, addr, _ = recv_rdt(server, 0, {})
            if not data:
                break
            buffer += data.decode(FORMAT)

            while delimiter in buffer:
                request, buffer = buffer.split(delimiter, 1)
                print(f"Received request from {client_addr}: {request}")
                if request == 'FILE_LIST':
                    files = get_file_list()
                    print(files)
                    msg_file_list = make_packet(0, '\n'.join(files).encode(FORMAT) + delimiter.encode(FORMAT))
                    ack = send_rdt(server, client_addr, msg_file_list)
                    if ack != 1:
                        print("Failed to send file list.")
                        break
                
                elif request.startswith('SIZE'):
                    fileName = request.split()[1]
                    print(f"Request for file size: {fileName}")
                    data = str(os.path.getsize(os.path.join(FOLDER, fileName))).encode(FORMAT) + delimiter.encode(FORMAT)
                    msg_size = make_packet(0, data)
                    ack = send_rdt(server, client_addr, msg_size)
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
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((HOST, PORT))
    
    print(f"Server is running on {HOST} : {PORT}\n")
    try:
        data, addr, _ = recv_rdt(server, 0, {})
        if data.decode(FORMAT) == "CONNECT":
            print(f"Connection request from {addr}")
            welcome = "Welcome to the server!\n".encode(FORMAT)
            msg_welcome = make_packet(0, welcome)
            ack = send_rdt(server, addr, msg_welcome)
            if ack != 1:
                print(f"Failed to send welcome message to {addr}")
                return
        else:
            print(f"Invalid connection request from {addr}")
            return
        
        data, addr, _ = recv_rdt(server, 1, {})
        if data.decode(FORMAT).startswith("HANDLE"):
            print(f"Client {addr} connected.\n")
            handle_client(server, addr)
            
            
    finally:
        print("Server shutting down...")
        server.close()

if __name__ == "__main__":
    run()