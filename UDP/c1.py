import socket
import threading
import os
import struct
import time
import sys

# Configuration Constants
HOST = socket.gethostbyname(socket.gethostname())
PORT = 12345
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(CUR_PATH, "output")
BUFFER = 1024
FORMAT = "utf-8"
TIMEOUT = 1  # Timeout for retransmissions
NUM_OF_CHUNKS = 4
MAX_RETRIES = 3

# Utility Functions
def checksum(data):
    """Calculate checksum for error detection."""
    return sum(data) % 256

def print_progress_bar(iteration, total, prefix='', suffix='', decimals=1, length=50, fill='#'):
    """Display a progress bar in the terminal."""
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()
    if iteration == total:
        sys.stdout.write('\n')

def fetch_file_list(client):
    """Retrieve the list of available files from the server."""
    client.sendto("FILELIST\n".encode(FORMAT), (HOST, PORT))
    print("Fetching available files from the server...")
    file_list, _ = client.recvfrom(BUFFER)
    print("Available files on the server:")
    file_list = file_list.decode().strip()
    print(file_list)
    return [line.split()[0] for line in file_list.split('\n') if line.strip()]

def download_chunk(filename, offset, chunk_size, part_id, progress, total_progress, total_size):
    """Download a file chunk and save it locally."""
    retry_count = 0
    seq_num = 0
    chunk_path = os.path.join(OUTPUT_DIR, f"{filename}.part{part_id}")

    while retry_count < MAX_RETRIES:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
                client.settimeout(TIMEOUT)
                request = f"REQUEST {filename} {offset} {chunk_size} {seq_num}\n"
                client.sendto(request.encode(FORMAT), (HOST, PORT))
                with open(chunk_path, "wb") as chunk_file:
                    total_received = 0

                    while total_received < chunk_size:
                        packet, _ = client.recvfrom(BUFFER)
                        packet_checksum = struct.unpack('!I', packet[:4])[0]
                        packet = packet[4:]

                        if checksum(packet) != packet_checksum:
                            continue

                        received_seq_num = struct.unpack('!I', packet[:4])[0]
                        if received_seq_num != seq_num:
                            continue

                        chunk_file.write(packet[4:])
                        total_received += len(packet[4:])

                        progress[part_id] = total_received
                        total_progress[0] += len(packet[4:])
                        print_progress_bar(total_progress[0], total_size, prefix='Progress:', suffix='Complete', length=50)

                        ack = struct.pack('!I', seq_num)
                        client.sendto(ack, (HOST, PORT))
                        seq_num += 1
                break
        except Exception as e:
            retry_count += 1
            if retry_count == MAX_RETRIES:
                print(f"Error downloading chunk {part_id} of {filename}: {e}")
            else:
                print(f"Retrying chunk {part_id} of {filename}...")

def download_file(filename, file_size):
    """Download a file by splitting it into chunks."""
    chunk_size = file_size // NUM_OF_CHUNKS
    remainder = file_size % NUM_OF_CHUNKS
    progress = [0] * NUM_OF_CHUNKS
    total_progress = [0]

    threads = []
    for i in range(NUM_OF_CHUNKS):
        offset = i * chunk_size
        if i == NUM_OF_CHUNKS - 1:
            chunk_size += remainder
        thread = threading.Thread(target=download_chunk, args=(filename, offset, chunk_size, i, progress, total_progress, file_size))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    output_path = os.path.join(OUTPUT_DIR, filename)
    with open(output_path, "wb") as final_file:
        for i in range(NUM_OF_CHUNKS):
            part_path = os.path.join(OUTPUT_DIR, f"{filename}.part{i}")
            with open(part_path, "rb") as part_file:
                final_file.write(part_file.read())
            os.remove(part_path)

    print(f"{filename} downloaded successfully!")

def main():
    """Main function for the client program."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        print("Connecting to the server...")
        client.sendto("CONNECT\n".encode(FORMAT), (HOST, PORT))
        welcome, _ = client.recvfrom(BUFFER)
        print(welcome.decode())

        available_files = fetch_file_list(client)
        print(available_files)
        input_files = []

        input_file_path = os.path.join(CUR_PATH, "input.txt")
        with open(input_file_path, "r") as f:
            for file in f:
                input_files.append(file.strip())

        for filename in input_files:
            if filename not in available_files:
                print(f"{filename} not found on the server.")
                continue

            client.sendto(f"SIZE {filename}\n".encode(FORMAT), (HOST, PORT))
            file_size, _ = client.recvfrom(BUFFER)
            file_size = int(file_size.decode())
            print(f"Downloading {filename} ({file_size} bytes)...")

            download_file(filename, file_size)

            client.sendto(f"ACK {filename}\n".encode(FORMAT), (HOST, PORT))

        print("Finished downloading requested files.")

if __name__ == "__main__":
    main()
