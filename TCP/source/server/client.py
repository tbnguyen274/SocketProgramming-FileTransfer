# Description: Client side of the TCP file transfer system

import socket
import threading
import os
import time
import sys
import pickle

'''
- Kết nối đến Server, nhận thông tin danh sách các file từ server và hiển thị trên màn hình.
- Mỗi Client download tuần tự từng file theo danh sách trong tập tin input.txt. Với mỗi một file cần download, client sẽ mở 
đúng 4 kết nối song song đến Server để bắt đầu download các phần của 1 file. Có thể dựa vào dung lượng của file và chia 4 để 
yêu cầu server gửi từng chunk cho mỗi kết nối.
- Sau khi tải xong các chunks, nối các phần đã download của một file thành file hoàn chỉnh. (kiểm tra bằng cách kiểm tra tổng
dung lượng và mở file thành công)

'''

HOST = '127.0.0.1'
PORT = 12345
ADDR = (HOST, PORT)
NUM_OF_CHUNKS = 4
MAX_RETRIES = 3
BUFFER_SIZE = 4096
FORMAT = "utf-8"

# Get the directory of the current script
CURRENT_WORKSPACE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(CURRENT_WORKSPACE, "output")

# Active download threads
active_threads = []

# Function to fetch the file list from the server
def fetch_file_list(client):
    client.send("FILELIST\n".encode(FORMAT))
    file_list = client.recv(BUFFER_SIZE).decode()
    print("Available files on the server:")
    print(f"{file_list}")
        
        
# Function to download a chunk
def download_chunk(filename, order, offset, chunk_size, part_id, progress):
    retry_count = 0
    while retry_count < MAX_RETRIES:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.connect(ADDR)
                
                # send the connect signal to the server
                client.send(f"CHUNK {order}\n".encode(FORMAT))
                
                request = f"REQUEST {filename} {offset} {chunk_size}\n"
                client.send(request.encode(FORMAT))

                # Receive the chunk data
                chunk_path = os.path.join(OUTPUT_DIR, f"{filename}.part{part_id}")
                total_received = 0
                
                with open(chunk_path, "wb") as chunk_file:
                    while total_received < chunk_size:
                        packet = client.recv(BUFFER_SIZE)
                        if not packet:
                            break
                        chunk_file.write(packet)
                        total_received += len(packet)
                        progress[part_id] = total_received

                break
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                print(f"Error downloading chunk {part_id} of {filename}: {e}")
            else:
                print(f"Retrying chunk {part_id} of {filename}...")
    
# Function to download a file
def download_file(filename, file_size):
    chunk_size = file_size // NUM_OF_CHUNKS
    remainder = file_size % NUM_OF_CHUNKS
    progress = [0] * NUM_OF_CHUNKS
    threads = []

    # Start threads for each chunk
    for i in range(NUM_OF_CHUNKS):
        offset = i * chunk_size
        order = i + 1
        if i == NUM_OF_CHUNKS - 1:
            chunk_size += remainder
        thread = threading.Thread(target=download_chunk, args=(filename, order, offset, chunk_size, i, progress))
        threads.append(thread)
        active_threads.append(thread)  # Track active threads
        thread.start()

    # Wait for all threads to complete
    for thread in threads:
        thread.join()

    # Merge chunks into the final file
    path = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(path, "wb") as final_file:
            for i in range(NUM_OF_CHUNKS):
                part_filename = os.path.join(OUTPUT_DIR, f"{filename}.part{i}")
                try:
                    with open(part_filename, "rb") as chunk_file:
                        final_file.write(chunk_file.read())
                    os.remove(part_filename)  # Clean up chunk files
                except IOError as e:
                    print(f"Error processing chunk {i}: {e}")
    except IOError as e:
        print(f"Error creating final file: {e}")

    print(f"{filename} downloaded successfully!")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.connect(ADDR)
        
        # Send the connect signal to the server
        client.send("CONNECT\n".encode())
        
        # Receive the welcome message from the server
        welcome = client.recv(BUFFER_SIZE).decode()
        print(welcome)
        
        # Fetch the file list from the server
        fetch_file_list(client)

        files = []

        # Construct the full path to the input file
        input_file_path = os.path.join(CURRENT_WORKSPACE, "input.txt")

        # Read the list of files to download
        with open(input_file_path, "r") as f:
            for file in f:
                files.append(file.strip())
        
        # Ensure the output directory exists
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # Download each file in the list
        for filename in files:
                client.send(f"SIZE {filename}\n".encode())
                file_size = int(client.recv(BUFFER_SIZE).decode())
                download_file(filename, file_size)
                
                # Respond to the server that the file has been downloaded
                client.send(f"ACK {filename}\n".encode())
        
        # Wait for all threads to complete
        for thread in active_threads:
            thread.join()
        
        print("All files downloaded successfully!")
        
        # don't let the terminal window close immediately
        input("Press Enter to exit...")
        
        # Send the exit signal to the server
        client.send("EXIT\n".encode())
        
        # Close the client connection
        client.close()
        
    
if __name__ == "__main__":
    main()