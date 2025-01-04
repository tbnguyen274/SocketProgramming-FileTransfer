# Description: Utility functions for UDP client and server.
import hashlib
import struct
import socket
import time
import os

# Constants
BUFFER_SIZE = 1024 * 48
FORMAT = "utf-8"
CUR_PATH = os.path.dirname(os.path.abspath(__file__))
MAX_RETRIES = 3
INVALID_PACKET = 0xFFFFFFFF # Invalid sequence number

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
            
            if response_number == INVALID_PACKET:  # NAK received
                # print("NAK received, resending packet")
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
    """Receive a packet, check checksum, and handle ACK/NAK."""
    global estimated_rtt, deviation, timeout_interval
    while True:
        try:
            client.settimeout(timeout_interval)
            data, addr = client.recvfrom(BUFFER_SIZE)
            
            if len(data) < 32:
                # print("Invalid packet received, sending NAK")
                NAK = struct.pack('!I', INVALID_PACKET)
                client.sendto(NAK, addr)
                continue
            
            # Unpack and verify checksum
            packet_checksum = struct.unpack('!32s', data[:32])[0].decode()
            payload = data[32:] 
            
            if calculate_checksum(payload) == packet_checksum:
                if len(payload) < 4:
                    # print("Invalid packet received, sending NAK")
                    NAK = struct.pack('!I', INVALID_PACKET)
                    client.sendto(NAK, addr)
                    continue
                
                seq_num = struct.unpack('!I', payload[:4])[0]
                data = payload[4:]
                
                # Handle in-order packets
                if seq_num == expected_seq:
                    ack = struct.pack('!I', seq_num + 1)
                    client.sendto(ack, addr)
                    return data, addr, seq_num + 1  # Pass next expected sequence
                
                # Handle out-of-order packets
                elif seq_num > expected_seq:
                    # print("Handling out-of-order packet")
                    # Buffer out-of-order packets
                    received_packets[seq_num] = data
                    ack = struct.pack('!I', expected_seq)  # Reconfirm last ACK
                    client.sendto(ack, addr)
                
                # Handle duplicate packets
                else:
                    # print("Duplicate packet received")
                    ack = struct.pack('!I', expected_seq)
                    client.sendto(ack, addr)
            else:
                # Checksum mismatch, send NAK
                # print("Checksum mismatch, sending NAK")
                NAK = struct.pack('!I', INVALID_PACKET)
                client.sendto(NAK, addr)
        except socket.timeout:
            # print("Timeout while receiving packet")
            continue
        except Exception as e:
            print(f"Unexpected error in recv_rdt: {e}")
