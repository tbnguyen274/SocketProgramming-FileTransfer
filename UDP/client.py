import socket
import threading
import os
import time
import struct
import sys
import hashlib

HOST = socket.gethostbyname(socket.gethostname())
PORT = 12345
ADDR = (HOST, PORT)
NUM_OF_CHUNKS = 20
MAX_RETRIES = 3
BUFFER_SIZE = 1024
FORMAT = "utf-8"
TIMEOUT = 10  # Timeout for retransmissions

CUR_PATH = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(CUR_PATH, "output")
active_threads = []

def checksum(data):
    return hashlib.md5(data).hexdigest()

def fetch_file_list(client):
    client.sendto("FILELIST\n".encode(FORMAT), ADDR)
    file_list, _ = client.recvfrom(BUFFER_SIZE)
    file_list = file_list.decode()
    print("Available files on the server:")
    print(f"{file_list}")
    file_array = file_list.split("\n")
    file_names = [file.split()[0] for file in file_array if file.strip()]
    return file_names

def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=50, fill='#'):
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()
    if iteration == total:
        sys.stdout.write('\n')

def download_chunk(client, filename, order, offset, chunk_size, part_id, progress, total_progress, total_size):
    retry_count = 0
    seq_num = 0
    while retry_count < MAX_RETRIES:
        try:
            #with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                print(client)
                client.settimeout(TIMEOUT)
                request = f"REQUEST {filename} {offset} {chunk_size} {seq_num}\n"
                client.sendto(request.encode(FORMAT), ADDR)
                chunk_path = os.path.join(OUTPUT_DIR, f"{filename}.part{part_id}")
                total_received = 0
                
                with open(chunk_path, "wb") as chunk_file:
                    while total_received < chunk_size:
                        print("Waiting to receive packet...")

                        packet, _ = client.recvfrom(BUFFER_SIZE)
                        print("Packet received")
                        print(packet)
                        
                        # Extract checksum
                        packet_checksum = struct.unpack('!32s', packet[:32])[0].decode()
                        packet = packet[32:]
                        
                        # Verify checksum
                        if checksum(packet) != packet_checksum:
                            print(f"Checksum mismatch in chunk {part_id} of {filename}.")
                            print(f"Expected: {packet_checksum}")
                            print(f"Received: {checksum(packet)}")
                            client.sendto(f"EXIT\n".encode(), ADDR)
                            break
                        else:
                            print("Checksum verified")
                        
                        # Extract sequence number
                        received_seq_num = struct.unpack('!I', packet[:4])[0]
                        if received_seq_num != seq_num:
                            print(f"Out-of-order packet {received_seq_num} received, expected {seq_num}. Retrying...")
                            continue
                        
                        data = packet[4:]
                        
                        # Write data to file
                        chunk_file.write(data)
                        total_received += len(data)
                        print(f"Received packet {seq_num} with size {len(data)}")
                        # progress[part_id] = total_received
                        # total_progress[0] += len(data)
                        # print_progress_bar(total_progress[0], total_size, prefix='Progress:', suffix='Complete', length=50)
                        
                        # Send ACK = seq_num + 1
                        seq_num += 1
                        ack = struct.pack('!I', seq_num)
                        print(f"Sending ACK {seq_num}")
                        client.sendto(ack, ADDR)
                print(f"Chunk {part_id} of {filename} downloaded successfully.")
                break
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                print(f"Error downloading chunk {part_id} of {filename}: {e}")
            else:
                print(f"Retrying chunk {part_id} of {filename}...")

def download_file(filename, file_size):
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
        thread = threading.Thread(target=download_chunk, args=(filename, order, offset, chunk_size, i, progress, total_progress, file_size))
        threads.append(thread)
        active_threads.append(thread)
        thread.start()
    for thread in threads:
        thread.join()
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
        client.sendto("CONNECT\n".encode(FORMAT), ADDR)
        welcome, _ = client.recvfrom(BUFFER_SIZE)
        print(welcome.decode())
        available_files = fetch_file_list(client)
        input_files = []
        input_file_path = os.path.join(CUR_PATH, "input.txt")
        with open(input_file_path, "r") as f:
            for file in f:
                input_files.append(file.strip())
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # for filename in input_files:
        #     if filename not in available_files:
        #         print(f"{filename} not found on the server.")
        #         continue
        #     print(f"Downloading {filename}...")
            
        #     client.sendto(f"SIZE {filename}\n".encode(FORMAT), ADDR)
        #     print("SIZE request sent for", filename)  # Debug statement
        #     file_size, _ = client.recvfrom(BUFFER_SIZE)
        #     print("SIZE response received for", filename)
        #     file_size = int(file_size.decode())
        #     print("File size:", file_size)
            
        #     download_file(filename, file_size)
        
        # test dowwnload one chunk
        filename = input_files[0]
        client.sendto(f"SIZE {filename}\n".encode(FORMAT), ADDR)
        print("SIZE request sent for", filename)
        file_size, _ = client.recvfrom(BUFFER_SIZE)
        print("SIZE response received for", filename)
        file_size = int(file_size.decode())
        print("File size:", file_size)
        
        active_threads = []
        # Calculate chunk size
        chunk_size = file_size // NUM_OF_CHUNKS
        remainder = file_size % NUM_OF_CHUNKS
        offset = 0
        order = 1
        if remainder > 0:
            chunk_size += remainder
        thread = threading.Thread(target=download_chunk, args=(client, filename, order, offset, chunk_size, 0, None, None, file_size))
        thread.start()
        active_threads.append(thread)
        
        for thread in active_threads:
            thread.join()
        
        print("Finished downloading requested files.")
        input("Press Enter to exit...")
        client.sendto("EXIT\n".encode(), ADDR)

if __name__ == "__main__":
    main()