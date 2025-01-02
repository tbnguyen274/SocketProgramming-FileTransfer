import socket
import threading
import sys
import signal
from utils import *

HOST = input("Enter the server IP address: ")
PORT = 12345
ADDR = (HOST, PORT)
NUM_OF_CHUNKS = 4
MAX_RETRIES = 3
OUTPUT_DIR = os.path.join(CUR_PATH, "output")
INPUT_FILE = os.path.join(CUR_PATH, "input.txt")

is_running = True

def signal_handler(sig, frame, client):
    global is_running
    print("Shutting down...")
    is_running = False
    
    # Send the exit signal to the server
    msg_exit = make_packet(0, "EXIT\n".encode())
    ack = send_rdt(client, ADDR, msg_exit)
    if ack != 1:
        print("Failed to exit the server.")
        return
    
    client.close()
    sys.exit(0)


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


def download_file(client, filename, offset, total_size):
    retry_count = 0
    seq_num = 0
    progress = 0
    
    while retry_count < MAX_RETRIES:
        try:
            request = f"REQUEST {filename} {offset} {total_size} {seq_num}\n".encode()          
            msg_request = make_packet(0, request)
            ack = send_rdt(client, ADDR, msg_request)
            if ack != 1:
                print(f"Failed to request file {filename}.")
                return

            file_path = os.path.join(OUTPUT_DIR, filename)
            total_received = 0

            with open(file_path, "wb") as file:
                while total_received < total_size:
                    # Receive the data
                    data, _, seq_num = recv_rdt(client, seq_num, {})

                    file.write(data)
                    total_received += len(data)
                    progress = total_received
                    
                    # Update progress bar
                    print_progress_bar(progress, total_size, prefix="Downloading", suffix=f"of {filename}")
                    
                print(f"Finished downloading {filename}\n")
                break
        
        except Exception as e:
            retry_count += 1
            
            if retry_count == MAX_RETRIES:
                print(f"Error downloading file {filename}: {e}")
            else:
                print(f"Retrying download of {filename}...")


def monitor_input(client, available_files):
    global is_running
    downloaded_files = set()
    unavailable_files = set()
    
    while is_running:
        try:
            # Read input file
            input_files = []
            with open(INPUT_FILE, "r") as f:
                for file in f:
                    input_files.append(file.strip())
            
            print(f"Checking for new files to download...\n")

            for filename in input_files:
                if filename in downloaded_files:
                    continue  # Skip downloaded files

                if filename not in available_files:
                    if filename not in unavailable_files:
                        print(f"{filename} is not available on the server.\n")
                        unavailable_files.add(filename)
                    continue  # Skip unavailable files
                
                print(f"Request to download {filename}... detected.")

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
                
                # Download file
                print("Downloading requested files...")
                download_file(client, filename, 0, file_size)
                downloaded_files.add(filename)
                
                # Respond to the server that the file has been downloaded
                msg_ack = make_packet(0, f"ACK {filename}\n".encode())
                ack = send_rdt(client, ADDR, msg_ack)
                if ack != 1:
                    print("Failed to send ACK.")
                    return
            
            # Sleep for 5 seconds before checking again
            time.sleep(5)
            
        except Exception as e:
            print(f"Error monitoring input file: {e}")
            break
            

def main():
    global is_running
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        print("Connecting to the server ...")
        try:
            # Register signal handler
            signal.signal(signal.SIGINT, lambda sig, frame: signal_handler(sig, frame, client))
            
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

            # Fetch file list
            available_files = fetch_file_list(client)
            
            # Create output directory
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            
            # Monitor input file for new downloads
            monitor_input(client, available_files)
        
        except Exception as e:
            print(f"Error: {e}")
            return
            
if __name__ == "__main__":
    main()