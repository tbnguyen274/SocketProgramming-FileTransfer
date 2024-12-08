# Description: Client side of the TCP file transfer system

import socket
import threading
import os
import time
import sys
import signal

'''
- Kết nối đến Server, nhận thông tin danh sách các file từ server và hiển thị trên màn hình.
- Mỗi Client download tuần tự từng file theo danh sách trong tập tin input.txt. Với mỗi một file cần download, client sẽ mở 
đúng 4 kết nối song song đến Server để bắt đầu download các phần của 1 file. Có thể dựa vào dung lượng của file và chia 4 để 
yêu cầu server gửi từng chunk cho mỗi kết nối.
- Sau khi tải xong các chunks, nối các phần đã download của một file thành file hoàn chỉnh. (kiểm tra bằng cách kiểm tra tổng
dung lượng và mở file thành công)
'''
# HOST = '192.168.1.192'
HOST = socket.gethostbyname(socket.gethostname())
PORT = 12345
ADDR = (HOST, PORT)
NUM_OF_CHUNKS = 4
MAX_RETRIES = 3
BUFFER_SIZE = 1024
FORMAT = "utf-8"

# Get the directory of the current script
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(CUR_PATH, "output")

# Active download threads
active_threads = []

# Flag for program state
is_running = True

# Signal handler for graceful shutdown
def signal_handler(sig, frame, client):
    global is_running
    print("Shutting down...")
    is_running = False
    
    # Send the exit signal to the server
    client.send("EXIT\n".encode())
    client.close()
    
    for thread in active_threads:
        thread.join()  # Wait for all threads to finish
    sys.exit(0)

# Register signal handler
#signal.signal(signal.SIGINT, signal_handler)

# Function to fetch the file list from the server
def fetch_file_list(client):
    client.send("FILELIST\n".encode(FORMAT))
    file_list = client.recv(BUFFER_SIZE).decode()
    print("Available files on the server:")
    print(f"{file_list}")
    
    file_array = file_list.split("\n")
    file_names = [file.split()[0] for file in file_array if file.strip()]
    
    return file_names

# Function to download a chunk
def display_chunk_progress(progress, filename):
    progress_str = []
    for part_id, chunk in enumerate(progress):
        downloaded = chunk["downloaded"]
        total = chunk["total"]
        percent_complete = (downloaded / total) * 100 if total > 0 else 0
        progress_str.append(f"part {part_id + 1} .... {percent_complete:.0f}%")
    print(f"\rDownloading {filename}: " + " | ".join(progress_str), end="")

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
                        progress[part_id]["downloaded"] = total_received
                        display_chunk_progress(progress, filename)  # Update progress for all chunks

                break
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                print(f"\nError downloading chunk {part_id} of {filename}: {e}")
            else:
                print(f"\nRetrying chunk {part_id} of {filename}...")

def download_file(filename, file_size):
    chunk_size = file_size // NUM_OF_CHUNKS
    remainder = file_size % NUM_OF_CHUNKS
    progress = [{"downloaded": 0, "total": chunk_size} for _ in range(NUM_OF_CHUNKS)]

    if remainder:
        progress[-1]["total"] += remainder  # Add remainder to the last chunk

    threads = []

    # Start threads for each chunk
    for i in range(NUM_OF_CHUNKS):
        offset = i * chunk_size
        order = i + 1
        thread = threading.Thread(target=download_chunk, args=(filename, order, offset, progress[i]["total"], i, progress))
        threads.append(thread)
        active_threads.append(thread)
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
                    print(f"\nError processing chunk {i}: {e}")
    except IOError as e:
        print(f"\nError creating final file: {e}")

    print(f"\n{filename} downloaded successfully!\n")


# Function to monitor the input file for new downloads
def monitor_input_file(client, available_files):
    downloaded_files = set()
    unavailable_files = set()

    while is_running:
        try:
            # Construct the full path to the input file
            input_file_path = os.path.join(CUR_PATH, "input.txt")

            # Read the list of files to download
            input_files = []
            with open(input_file_path, "r") as f:
                for file in f:
                    input_files.append(file.strip())

            print(f"Checking for new files to download...\n")
            
            # Check new file to download
            for filename in input_files:
                if filename in downloaded_files:
                    continue  # Skip downloaded files

                if filename not in available_files:
                    if filename not in unavailable_files:
                        print(f"{filename} is not available on the server.\n")
                        unavailable_files.add(filename)
                    continue  # Skip unavailable files
                
                print(f"Request to download {filename}... detected.")
                client.send(f"SIZE {filename}\n".encode())
                file_size = int(client.recv(BUFFER_SIZE).decode())
                download_file(filename, file_size)

                # Respond to the server that the file has been downloaded
                client.send(f"ACK {filename}\n".encode())
                downloaded_files.add(filename)

            # Sleep for 5 seconds before checking again
            time.sleep(5)

        except Exception as e:
            print(f"Error monitoring input file: {e}")
            break

def main():
    global is_running
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        # Register signal handler for Ctrl+C
        signal.signal(signal.SIGINT, lambda sig, frame: signal_handler(sig, frame, client))
                
        # Send the connect signal to the server
        client.connect(ADDR)
        client.send("CONNECT\n".encode())
        
        # Receive the welcome message from the server
        welcome = client.recv(BUFFER_SIZE).decode()
        print(welcome)
        
        # Fetch the file list from the server
        available_files = fetch_file_list(client)

        # Ensure the output directory exists
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # Start a thread to download new files
        # monitor_thread = threading.Thread(target=monitor_input_file, args=(client, available_files))
        # monitor_thread.start()

        # Keep main thread running
        # while is_running:
        #     time.sleep(1)

        # Wait monitor finish
        # monitor_thread.join()
        
        monitor_input_file(client, available_files)

if __name__ == "__main__":
    main()
