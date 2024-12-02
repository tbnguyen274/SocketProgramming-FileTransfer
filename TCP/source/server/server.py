import socket
import os
import threading
import pickle

HOST = '127.0.0.1'
PORT = 12345
FILEPATH = './files'
BUFFER = 4096
FORMAT = 'utf-8'
MB = 1048576
MAX_CONNECTIONS = 10

def getFileList():
    scannedFiles = []

    with open('./files.txt', 'r') as files:
        for file in files:
            scannedFiles.append(file.strip())
    
    return scannedFiles

def sendFileChunk(client, file, offset, chunk):
    with open(os.path.join(FILEPATH, file), 'rb') as f:
        totalSent = 0
        f.seek(offset)            
        while totalSent < chunk:
            part = f.read(BUFFER if chunk - totalSent > BUFFER else chunk - totalSent)
            sent = client.send(part)
            totalSent += sent
            f.seek(offset + totalSent)

def processClient(server, client):
    request = client.recv(BUFFER).decode(FORMAT)

    if request == 'Filelist':
        files = getFileList()
        filesWithSize = []
        for file in files:
            filesWithSize.append(f"{file} - {os.path.getsize(os.path.join(FILEPATH, file)) / MB} MB")

        client.sendall('\n'.join(filesWithSize).encode(FORMAT))
    elif request.startswith('SIZE'):
        fileName = request.split()[1]
        client.send(str(os.path.getsize(os.path.join(FILEPATH, fileName))).encode(FORMAT))
    elif request.startswith('REQUEST'):
        info = request.split()
        fileName = info[1]
        offset = int(info[2])
        chunk = int(info[3])

        sendFileChunk(client, fileName, offset, chunk)

    client.close()

    

def run():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(MAX_CONNECTIONS)
    print(f"Server is running on port: {PORT}.\n\n")

    try:
        while True:
            conn, addr = server.accept()

            clientThread = threading.Thread(target=processClient, args=(server, conn))  
            clientThread.start()
    finally:
        server.close()

if __name__ == "__main__":
    run()