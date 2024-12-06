import socket
import os
import threading

HOST = '127.0.0.1'
PORT = 12345
FOLDER = './files'
FILELIST = './files.txt'
BUFFER = 4096
FORMAT = 'utf-8'
MB = 1048576
MAX_CONNECTIONS = 10

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

def sendFileChunk(client, file, offset, chunk):
    with open(os.path.join(FOLDER, file), 'rb') as f:
        totalSent = 0
        f.seek(offset)

        while totalSent < chunk:
            part = f.read(BUFFER if chunk - totalSent > BUFFER else chunk - totalSent)
            sent = client.send(part)
            totalSent += sent
            f.seek(offset + totalSent)

def processClient(server, client, addr):
    #print(f"Client {addr} connected successfully.")
    
 
    buffer = ""
    delimiter = "\n"
    while True:
        try:
            data = client.recv(BUFFER).decode(FORMAT)
            if not data:
                break
            
            buffer += data
            while delimiter in buffer:
                request, buffer = buffer.split(delimiter, 1)
                if request == "CONNECT":
                    print(f"Client {addr} connected successfully.")
                    welcome = f"Welcome to the server, {addr}!\n"
                    client.send(welcome.encode(FORMAT))
                    
                elif request == 'FILELIST':
                    files = getFileList()
                    client.sendall('\n'.join(files).encode(FORMAT) + delimiter.encode(FORMAT))
                    
                elif request.startswith('SIZE'):
                    fileName = request.split()[1]
                    client.send(str(os.path.getsize(os.path.join(FOLDER, fileName))).encode(FORMAT) + delimiter.encode(FORMAT))
                    
                elif request.startswith('CHUNK'):
                    order = request.split()[1]
                    print(f"Connection from {addr} to download chunk {order}.")
                    
                elif request.startswith('REQUEST'):
                    info = request.split()
                    fileName = info[1]
                    offset = int(info[2])
                    chunk = int(info[3])

                    if os.path.exists(os.path.join(FOLDER, fileName)):
                        sendFileChunk(client, fileName, offset, chunk)
                        
                elif request.startswith('ACK'):
                    fileName = request.split()[1]
                    print(f"Client {addr} successfully downloaded {fileName}.")
                    
                elif request.startswith("EXIT"):
                    print(f"Client {addr} disconnected.\n")
                    client.close()
                    return
        except Exception as e:
            print(f"Error processing request from {addr}: {e}")
            break

    client.close()
    #print(f"Client {addr} disconnected.")

    

def run():
    scanFiles()
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(MAX_CONNECTIONS)
    print(f"Server is running on port: {PORT}.\n")
    
    try:
        while True:
            conn, addr = server.accept()

            clientThread = threading.Thread(target=processClient, args=(server, conn, addr))  
            clientThread.start()
    finally:
        server.close()

if __name__ == "__main__":
    run()