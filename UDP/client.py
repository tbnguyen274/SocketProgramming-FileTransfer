import socket
import threading
import os
import struct
import sys
import hashlib
from utils import *

HOST = socket.gethostbyname(socket.gethostname())
PORT = 12345
ADDR = (HOST, PORT)
NUM_OF_CHUNKS = 4
MAX_RETRIES = 3
BUFFER_SIZE = 1024 * 4
FORMAT = "utf-8"
TIMEOUT = 3  # Timeout for retransmissions

CUR_PATH = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(CUR_PATH, "output")
active_threads = []


def fetch_file_list(client):
    msg_file_list = make_packet(0, b"FILE_LIST\n")
    ack = send_rdt(client, ADDR, msg_file_list)
    if ack != 1:
        print("Failed to fetch file list.")
        return
    file_list, _ = recv_rdt(client)
    file_list = file_list.decode()
    
    print("Available files on the server:")
    print(f"{file_list}")
    
    file_array = file_list.split("\n")
    file_names = [file.split()[0] for file in file_array if file.strip()]
    return file_names

progress_lock = threading.Lock()

def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=50, fill='#'):
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    with progress_lock:
        sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
        sys.stdout.flush()
        if iteration == total:
            sys.stdout.write('\n')



def download_chunk(client, filename, order, offset, chunk_size, part_id, progress, total_progress, total_size):
    retry_count = 0
    seq_num = 0
    while retry_count < MAX_RETRIES:
        try:
            request = f"REQUEST {filename} {offset} {chunk_size} {seq_num}\n".encode()          
            msg_request = make_packet(0, request)
            ack = send_rdt(client, ADDR, msg_request)
            if ack != 1:
                print(f"Failed to request chunk {part_id} of {filename}.")
                return
            chunk_path = os.path.join(OUTPUT_DIR, f"{filename}.part{part_id}")
            total_received = 0

            with open(chunk_path, "wb") as chunk_file:
                while total_received < chunk_size:
                    data, _ = recv_rdt(client)

                    chunk_file.write(data)
                    total_received += len(data)
                    # print(f"Received packet {seq_num} with size {len(data)}")
                    progress[part_id] = total_received
                    total_progress[0] = sum(progress)
                    
                    # print progress of current chunk
                    print_progress_bar(total_received, chunk_size, prefix=f"Chunk {part_id} of {filename}:")
                    
                    seq_num += 1
                

                print(f"Chunk {part_id} of {filename} downloaded successfully.")
                break
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                print(f"Error downloading chunk {part_id} of {filename}: {e}")
            else:
                print(f"Retrying chunk {part_id} of {filename}...")

def download_file(client, filename, file_size):
    chunk_size = file_size // NUM_OF_CHUNKS
    remainder = file_size % NUM_OF_CHUNKS
    progress = [0] * NUM_OF_CHUNKS
    total_progress = [0]
    threads = []
    for i in range(NUM_OF_CHUNKS):
        offset = i * chunk_size
        order = i + 1
        if i == NUM_OF_CHUNKS - 1:
            chunk_size += remainder
        print(f"Downloading chunk {i} of {filename}...")
        download_chunk(client, filename, order, offset, chunk_size, i, progress, total_progress, file_size)

    
    msg_exit = make_packet(0, b"EXIT")
    ack = send_rdt(client, ADDR, msg_exit)
    if ack != 1:
        print("Failed to exit the server.")
        return
    
    path = os.path.join(OUTPUT_DIR, filename)
    try:
        with open(path, "wb") as final_file:
            for i in range(NUM_OF_CHUNKS):
                part_filename = os.path.join(OUTPUT_DIR, f"{filename}.part{i}")
                try:
                    with open(part_filename, "rb") as chunk_file:
                        final_file.write(chunk_file.read())
                    os.remove(part_filename)
                except IOError as e:
                    print(f"Error processing chunk {i}: {e}")
    except IOError as e:
        print(f"Error creating final file: {e}")
    print(f"{filename} downloaded successfully!")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        print("Connecting to the server...")
        
        # Connect to the server using reliable UDP
        hello = make_packet(0, b"CONNECT")
        ack = send_rdt(client, ADDR, hello)
        if ack != 1:
            print("Failed to connect to the server.")
            return
        else:
            print("Connected to the server.")
        welcome, _ = recv_rdt(client)
        print(welcome.decode())
        
        handle_msg = make_packet(1, b"HANDLE")
        ack = send_rdt(client, ADDR, handle_msg)
        if ack != 2:
            print("Failed to connect to the server.")
            return
        
        available_files = fetch_file_list(client)
        input_files = []
        input_file_path = os.path.join(CUR_PATH, "input.txt")
        with open(input_file_path, "r") as f:
            for file in f:
                input_files.append(file.strip())
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        filename = input_files[0]
        msg_size = make_packet(0, f"SIZE {filename}\n".encode())
        ack = send_rdt(client, ADDR, msg_size)
        if ack != 1:
            print("Failed to fetch file size.")
            return
        
        file_size, _ = recv_rdt(client)
        file_size = int(file_size.decode())
        msg_exit = make_packet(0, b"EXIT\n")
        ack = send_rdt(client, ADDR, msg_exit)
        if ack != 1:
            print("Failed to exit the server.")
            return
        else:
            print(f"File size of {filename}: {file_size}")

        print("Downloading requested files...")
        download_file(client, filename, file_size)

        print("Finished downloading requested files.")
        input("Press Enter to exit...")
        client.sendto("EXIT\n".encode(), ADDR)

if __name__ == "__main__":
    main()