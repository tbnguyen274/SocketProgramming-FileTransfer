import socket
import os
import threading
import struct
import time

HOST = '0.0.0.0'
PORT = 12345
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(CUR_PATH, 'files')
FILELIST = os.path.join(CUR_PATH, 'filelist.txt')
BUFFER = 1024
FORMAT = 'utf-8'
MB = 1024 * 1024
TIMEOUT = 10  # Timeout for retransmissions

def getFileList():
    fileList = []
    with open(FILELIST, 'r') as list:
        for file in list:
            if file:
                fileList.append(file.strip())
    return fileList

def scanFiles():
    scannedFiles = []
    folder = os.listdir(FOLDER)
    for file in folder:
        if os.path.isfile(os.path.join(FOLDER, file)):
            scannedFiles.append(file)
    with open(FILELIST, 'w') as list:
        for file in scannedFiles:
            list.write(f"{file} {round(os.path.getsize(os.path.join(FOLDER, file)) / MB, 2)}MB\n")
    return scannedFiles

def checksum(data):
    return sum(data) % 256

def sendFileChunk(server, client_addr, file, offset, chunk, seq_num):
    with open(os.path.join(FOLDER, file), 'rb') as f:
        totalSent = 0
        f.seek(offset)
        while totalSent < chunk:
            part = f.read(min(BUFFER, chunk - totalSent))
            packet = struct.pack('!I', seq_num) + part
            packet_checksum = checksum(packet)
            packet = struct.pack('!I', packet_checksum) + packet
            server.sendto(packet, client_addr)
            totalSent += len(part)
            seq_num += 1
            try:
                server.settimeout(TIMEOUT)
                ack, _ = server.recvfrom(BUFFER)
                ack_seq_num = struct.unpack('!I', ack)[0]
                if ack_seq_num != seq_num - 1:
                    raise Exception("ACK sequence number mismatch")
            except:
                f.seek(offset + totalSent - len(part))
                totalSent -= len(part)
                seq_num -= 1

def processClient(server, client_addr, files):
    buffer = ""
    delimiter = "\n"
    while True:
        try:
            data, addr = server.recvfrom(BUFFER)
            if not data:
                break
            buffer += data.decode(FORMAT)
            print(f"Received data from {client_addr}: {buffer}")
            while delimiter in buffer:
                request, buffer = buffer.split(delimiter, 1)
                print(f"Received request from {client_addr}: {request}")
                if request == 'FILELIST':
                    files = getFileList()
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
                    if os.path.exists(os.path.join(FOLDER, fileName)):
                        threading.Thread(target=sendFileChunk, args=(server, client_addr, fileName, offset, chunk, seq_num)).start()
                elif request.startswith("EXIT"):
                    print(f"Client {client_addr} disconnected.\n")
                    return
        except Exception as e:
            print(f"Error processing request from {client_addr}: {e}")
            break

def run():
    files = scanFiles()
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind((HOST, PORT))
    print(f"Server is running on port: {PORT}.\n")
    try:
        while True:
            data, addr = server.recvfrom(BUFFER)
            if data.decode(FORMAT).startswith("CONNECT"):
                server.sendto("CONNECTED".encode(FORMAT), addr)
                processClient(server, addr, files)
    finally:
        server.close()

if __name__ == "__main__":
    run()