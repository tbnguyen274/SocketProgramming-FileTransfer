import socket
import threading
import sys
from utils import *


HOST = socket.gethostbyname(socket.gethostname())
HOST = '192.168.1.40'
PORT = 12345
ADDR = (HOST, PORT)
NUM_OF_CHUNKS = 4
MAX_RETRIES = 3
OUTPUT_DIR = os.path.join(CUR_PATH, "output")
INPUT_FILE = os.path.join(CUR_PATH, "input.txt")


def fetch_file_list(client):
    msg_file_list = make_packet(0, "FILE_LIST\n".encode())
    ack = send_rdt(client, ADDR, msg_file_list)
    if ack != 1:
        print("Failed to fetch file list.")
        return
    file_list, _, _ = recv_rdt(client, 0, {})
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

def download_file(client, filename, offset, chunk_size, part_id, progress, total_progress, total_size):
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
            print("OK")
            chunk_path = os.path.join(OUTPUT_DIR, filename)
            total_received = 0

            with open(chunk_path, "wb") as chunk_file:
                while total_received < chunk_size:
                    data, _, seq_num = recv_rdt(client, seq_num, {})

                    chunk_file.write(data)
                    total_received += len(data)
                    # print(f"Received packet {seq_num} with size {len(data)}")
                    progress[part_id] = total_received
                    total_progress[0] = sum(progress)
                    
                    print_progress_bar(total_progress[0], total_size, prefix="Downloading", suffix=f"of {filename}")
                    
                print(f"Finished downloading {filename}\n")
                break
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                print(f"Error downloading chunk {part_id} of {filename}: {e}")
            else:
                print(f"Retrying chunk {part_id} of {filename}...")


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        print("Connecting to the server...")
        try:
            # Handshake - CONNECT
            msg_hello = make_packet(0, "CONNECT".encode())
            ack = send_rdt(client, ADDR, msg_hello)
            if ack != 1:
                print("Failed to connect to the server.")
                return
            else:
                print("Connected to the server.")
            
            # Receive welcome message
            welcome, _, _ = recv_rdt(client, 0, {})
            print(welcome.decode())

            
            available_files = fetch_file_list(client)
            
            input_files = []
            with open(INPUT_FILE, "r") as f:
                for file in f:
                    input_files.append(file.strip())
            
            os.makedirs(OUTPUT_DIR, exist_ok=True)  # Create output directory if it doesn't exist
            
            downloaded_files = set()
            unavailable_files = set()
            
            for filename in input_files:
                if filename in downloaded_files:
                    continue  # Skip downloaded files

                if filename not in available_files:
                    if filename not in unavailable_files:
                        print(f"{filename} is not available on the server.\n")
                        unavailable_files.add(filename)
                    continue  # Skip unavailable files
                
                # Request file size
                msg_size = make_packet(0, f"SIZE {filename}\n".encode())
                ack = send_rdt(client, ADDR, msg_size)
                if ack != 1:
                    print("Failed to fetch file size.")
                    return
                
                # Receive file size
                file_size, _, _ = recv_rdt(client, 0, {})
                file_size = int(file_size.decode())
                print(f"Size of {filename}: {file_size}")
                
                print("Downloading requested files...")
                download_file(client, filename, 0, file_size, 0, [0] * NUM_OF_CHUNKS, [0], file_size)

            print("Finished downloading requested files.")
            input("Press Enter to exit...")
            msg_exit = make_packet(0, "EXIT\n".encode())

            ack = send_rdt(client, ADDR, msg_exit)
            if ack != 1:
                print("Failed to exit the server.")
                return
        except KeyboardInterrupt:
            print("\nExiting...")
            msg_exit = make_packet(0, "EXIT\n".encode())

            ack = send_rdt(client, ADDR, msg_exit)
            if ack != 1:
                print("Failed to exit the server.")
                return
            
if __name__ == "__main__":
    main()