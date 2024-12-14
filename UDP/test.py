import socket
import struct
import time
import hashlib

# Function to calculate checksum
def calculate_checksum(data):
    return hashlib.md5(data).hexdigest()

# Server code
def udp_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind(("127.0.0.1", 12345))
    print("Server is ready to send data.")

    # Simulated file data
    file_data = b"This is a sample file data to test UDP reliable transfer."
    chunk_size = 20  # Size of each chunk to send
    sequence_number = 0

    while sequence_number * chunk_size < len(file_data):
        # Extract chunk
        chunk = file_data[sequence_number * chunk_size:(sequence_number + 1) * chunk_size]

        # Calculate checksum
        checksum = calculate_checksum(chunk.encode() if isinstance(chunk, str) else chunk)

        # Prepare packet (sequence number, checksum, data)
        packet = struct.pack("I32s{}s".format(len(chunk)), sequence_number, checksum.encode(), chunk)

        # Send packet
        server_socket.sendto(packet, ("127.0.0.1", 54321))
        print(f"Sent packet {sequence_number}")

        # Wait for ACK
        try:
            server_socket.settimeout(1)  # 1-second timeout
            ack, _ = server_socket.recvfrom(1024)
            ack_number = struct.unpack("I", ack)[0]

            if ack_number == sequence_number:
                print(f"ACK {ack_number} received")
                sequence_number += 1
            else:
                print("Incorrect ACK received, resending packet")
        except socket.timeout:
            print("Timeout, resending packet")

# Client code
def udp_client():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.bind(("127.0.0.1", 54321))

    print("Client is ready to receive data.")
    expected_sequence_number = 0
    received_data = b""

    while True:
        # Receive packet
        packet, addr = client_socket.recvfrom(1024)

        # Unpack packet
        seq_number, checksum, chunk = struct.unpack("I32s{}s".format(len(packet) - 36), packet)
        checksum = checksum.decode()

        # Verify checksum
        if checksum == calculate_checksum(chunk):
            if seq_number == expected_sequence_number:
                print(f"Received packet {seq_number} correctly")
                received_data += chunk

                # Send ACK
                ack = struct.pack("I", seq_number)
                client_socket.sendto(ack, addr)
                expected_sequence_number += 1
            else:
                print(f"Out-of-order packet {seq_number} received, expected {expected_sequence_number}")
        else:
            print(f"Packet {seq_number} has a checksum error")

        # Break the loop if all data is received (for demonstration purposes)
        if len(received_data) >= len(b"This is a sample file data to test UDP reliable transfer."):
            break

    print("File received successfully:", received_data.decode())

# Run server and client (for testing, run these in separate processes or threads)
# Uncomment the following lines to test
import threading
server_thread = threading.Thread(target=udp_server)
client_thread = threading.Thread(target=udp_client)
server_thread.start()
client_thread.start()
server_thread.join()
client_thread.join()
