# Description: Utility functions for UDP client and server.
import hashlib
import struct
import socket
import time
import os

# Constants
BUFFER_SIZE = 1024 * 4
FORMAT = "utf-8"
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
MAX_RETRIES = 3
INVALID_PACKET = 0xFFFFFFFF

# Constants for reliable UDP
INITIAL_TIMEOUT = 1.0  # Initial timeout in seconds
ALPHA = 0.125  # Smoothing factor for RTT
BETA = 0.25  # Smoothing factor for deviation
MIN_TIMEOUT = 1.0  # seconds
MAX_TIMEOUT = 10.0  # seconds

# Variables for dynamic timeout
estimated_rtt = INITIAL_TIMEOUT
deviation = 0.0
timeout_interval = INITIAL_TIMEOUT


def calculate_checksum(data):
    """Calculate the MD5 checksum of the given data."""
    return hashlib.md5(data).hexdigest()


def make_packet(seq_num, data):
    """Create a packet with a sequence number, checksum, and data."""
    header = struct.pack('!I', seq_num)
    checksum_value = calculate_checksum(header + data)
    checksum_value = checksum_value.encode() if isinstance(checksum_value, str) else checksum_value
    return struct.pack('!32s', checksum_value) + header + data

def extract_seq_num(packet):
    """Extract sequence number from packet with checksum"""
    # Skip 32 bytes checksum, then read 4 bytes sequence number
    return struct.unpack('!I', packet[32:36])[0]

def extract_data(packet):
    """Extract data from packet, skipping checksum and sequence number"""
    # Skip 32 bytes checksum and 4 bytes sequence number
    return packet[36:]

def verify_packet(packet):
    """Verify packet integrity using checksum"""
    stored_checksum = packet[:32].strip(b'\x00')  # First 32 bytes are checksum
    actual_data = packet[32:]  # Rest is header + data
    calculated_checksum = calculate_checksum(actual_data).encode()
    return stored_checksum == calculated_checksum


# def send_rdt(client, addr, packet):
#     while True:
#         client.sendto(packet, addr)
#         try:
#             client.settimeout(TIMEOUT)
#             response, _ = client.recvfrom(BUFFER_SIZE)
#             response_number = struct.unpack('!I', response)[0]
#             if response_number == 0:  # NACK received
#                 print("NACK received, resending packet")
#                 continue
#             return response_number  # ACK received
#         except socket.timeout:
#             print("Timeout, resending packet")


# def recv_rdt(client):
#     """Receive a packet and send an acknowledgment."""
#     while True:
#         try:
#             data, addr = client.recvfrom(BUFFER_SIZE)
#             packet_checksum = struct.unpack('!32s', data[:32])[0].decode()
#             payload = data[32:]
#             if calculate_checksum(payload) == packet_checksum:
#                 seq_num = struct.unpack('!I', payload[:4])[0]
#                 ack = struct.pack('!I', seq_num + 1)
#                 client.sendto(ack, addr)
#                 return payload[4:], addr
#             else:
#                 print("Checksum mismatch, sending NACK")
#                 nack = struct.pack('!I', 0) # NACK with sequence number 0 (invalid packet)
#                 client.sendto(nack, addr)
#         except socket.timeout:
#             print("Timeout while receiving packet")
#         except struct.error as e:
#             print(f"Packet structure error: {e}")
#         except Exception as e:
#             print(f"Unexpected error in recv_rdt: {e}")


def send_rdt(client, addr, packet):
    """Send a packet and handle retransmissions with dynamic timeout."""
    global estimated_rtt, deviation, timeout_interval
    while True:
        start_time = time.time()  # Measure RTT
        client.sendto(packet, addr)
        try:
            client.settimeout(timeout_interval)
            response, _ = client.recvfrom(BUFFER_SIZE)
            
            if len(response) < 4:
                # print("Invalid packet received, resending")
                continue
            
            # print(response)
            response_number = struct.unpack('!I', response)[0]
            # print(f"Received ACK {response_number}")
            
            if response_number == INVALID_PACKET:  # NACK received
                # print("NACK received, resending packet")
                continue
            
            # Calculate RTT dynamically
            sample_rtt = time.time() - start_time
            estimated_rtt = (1 - ALPHA) * estimated_rtt + ALPHA * sample_rtt
            deviation = (1 - BETA) * deviation + BETA * abs(sample_rtt - estimated_rtt)
            timeout_interval = max(MIN_TIMEOUT, min(MAX_TIMEOUT, estimated_rtt + 4 * deviation))
            
            return response_number  # ACK received
        except socket.timeout:
            print("Timeout, resending packet")


def recv_rdt(client, expected_seq, received_packets):
    """Receive a packet, check checksum, and handle ACK/NACK."""
    global estimated_rtt, deviation, timeout_interval
    while True:
        try:
            client.settimeout(timeout_interval)
            data, addr = client.recvfrom(BUFFER_SIZE)
            
            if len(data) < 32:
                # print("Invalid packet received, sending NACK")
                nack = struct.pack('!I', INVALID_PACKET)
                client.sendto(nack, addr)
                continue
            
            # Unpack and verify checksum
            packet_checksum = struct.unpack('!32s', data[:32])[0].decode()
            payload = data[32:]
            if calculate_checksum(payload) == packet_checksum:
                
                if len(payload) < 4:
                    # print("Invalid packet received, sending NACK")
                    nack = struct.pack('!I', INVALID_PACKET)
                    client.sendto(nack, addr)
                    continue
                
                seq_num = struct.unpack('!I', payload[:4])[0]
                data = payload[4:]
                
                # Handle out-of-order packets
                if seq_num == expected_seq:
                    ack = struct.pack('!I', seq_num + 1)
                    client.sendto(ack, addr)
                    return data, addr, seq_num + 1  # Pass next expected sequence
                
                elif seq_num > expected_seq:
                    # print("Handling out-of-order packet")
                    # Buffer out-of-order packets
                    received_packets[seq_num] = data
                    ack = struct.pack('!I', expected_seq)  # Reconfirm last ACK
                    client.sendto(ack, addr)
                
                else:
                    # Duplicate packet
                    # print("Duplicate packet received")
                    ack = struct.pack('!I', expected_seq)
                    client.sendto(ack, addr)
            else:
                # Checksum mismatch, send NACK
                # print("Checksum mismatch, sending NACK")
                nack = struct.pack('!I', INVALID_PACKET)
                client.sendto(nack, addr)
        except socket.timeout:
            print("Timeout while receiving packet")
            continue
        except Exception as e:
            print(f"Unexpected error in recv_rdt: {e}")


 


# selective repeat            

def sliding_window_send(client, addr, packets, window_size):
    """Improved sliding window send with per-packet timers and selective retransmissions."""
    global estimated_rtt, deviation, timeout_interval
    base = 0
    next_seq_num = 0
    window = {}
    max_seq_num = len(packets)

    while base < max_seq_num:
        # Send packets within the window
        while next_seq_num < min(base + window_size, max_seq_num):
            if next_seq_num not in window:
                try:
                    start_time = time.time()  # Measure RTT
                    response = send_rdt(client, addr, packets[next_seq_num])
                    
                    if response is not None and response > base:
                        old_base = base
                        base = response
                        # Clear acknowledged packets
                        for seq in range(old_base, base):
                            window.pop(seq, None)
                        
                        # Calculate RTT dynamically
                        sample_rtt = time.time() - start_time
                        estimated_rtt = (1 - ALPHA) * estimated_rtt + ALPHA * sample_rtt
                        deviation = (1 - BETA) * deviation + BETA * abs(sample_rtt - estimated_rtt)
                        timeout_interval = max(MIN_TIMEOUT, min(MAX_TIMEOUT, estimated_rtt + 4 * deviation))
                        
                except Exception as e:
                    print(f"Error sending packet {next_seq_num}: {e}")
                    return
            window[next_seq_num] = True
            next_seq_num += 1

        # Check for timeouts and handle retransmissions
        try:
            client.settimeout(timeout_interval)
            response, _ = client.recvfrom(BUFFER_SIZE)
            # print(f"Received ACK {response}")
            
            # Check if this is a file request (starts with checksum)
            if len(response) > 32 and b'SIZE' in response:
                # Skip file request
                nack = struct.pack('!I', INVALID_PACKET)  # Use a specific value to indicate NACK
                client.sendto(nack, addr)
                continue
            
            if len(response) >= 4:
                ack_num = struct.unpack('!I', response)[0]
                if ack_num > base:
                    old_base = base
                    base = ack_num
                    # Clear acknowledged packets
                    for seq in range(old_base, base):
                        window.pop(seq, None)
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Warning in sliding window: {e}")  # Changed to warning
            if "unpack requires" in str(e):
                continue  # Skip invalid packets
            return
        
        
def sliding_window_recv(client, expected_seq, window_size):
    """Improved sliding window receive with out-of-order buffering."""
    global estimated_rtt, deviation, timeout_interval
    received_packets = {}
    buffer = {}

    while True:
        try:
            client.settimeout(timeout_interval)
            data, addr, next_seq = recv_rdt(client, expected_seq, buffer)
            
            if data:  # Only process if we got valid data
                # Handle in-order packet
                if next_seq == expected_seq + 1:
                    yield {expected_seq: data}
                    expected_seq = next_seq
                    
                    # Process buffered packets that are now in order
                    while expected_seq in buffer:
                        buffered_data = buffer.pop(expected_seq)
                        yield {expected_seq: buffered_data}
                        expected_seq += 1
                # Handle out-of-order packet
                elif next_seq > expected_seq + 1:
                    buffer[next_seq-1] = data

        except socket.timeout:
            print("Timeout while receiving packet")
            continue
        except Exception as e:
            print(f"Error in sliding window receive: {e}")
            continue