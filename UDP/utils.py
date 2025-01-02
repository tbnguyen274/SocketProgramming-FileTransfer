# Description: Utility functions for UDP client and server.
import hashlib
import struct
import socket
import time
import os
import math

# Constants
BUFFER_SIZE = 1024 * 4
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
            # print("Timeout while receiving packet")
            continue
        except Exception as e:
            print(f"Unexpected error in recv_rdt: {e}")


 
 
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
            # print("Timeout while receiving packet")
            continue
        except Exception as e:
            print(f"Error in sliding window receive: {e}")
            continue
        


class AdaptiveWindow:
    def __init__(self, initial_size=10, min_size=5, max_size=50):
        self.window_size = initial_size
        self.min_size = min_size
        self.max_size = max_size
        self.rtt_samples = []
        self.packet_loss_rate = 0
        self.successful_transmissions = 0
        self.failed_transmissions = 0
        
    def calculate_bandwidth_delay_product(self, rtt):
        """Calculate optimal window size based on bandwidth-delay product"""
        if not self.rtt_samples or self.successful_transmissions == 0:
            return self.window_size  # Return current window size if no samples
            
        avg_rtt = sum(self.rtt_samples) / len(self.rtt_samples)
        if avg_rtt == 0:  # Prevent division by zero
            return self.window_size
            
        # Assume bandwidth can be estimated from successful transmission rate
        estimated_bandwidth = self.successful_transmissions / avg_rtt
        return math.ceil(estimated_bandwidth * rtt)
    
    def update_window_size(self, rtt, packet_loss=False):
        """Update window size based on network conditions"""
        if rtt <= 0:  # Protect against invalid RTT values
            return self.window_size
            
        self.rtt_samples.append(rtt)
        if len(self.rtt_samples) > 10:  # Keep last 10 samples
            self.rtt_samples.pop(0)
            
        if packet_loss:
            self.failed_transmissions += 1
            # Decrease window size on packet loss
            self.window_size = max(self.min_size, self.window_size // 2)
        else:
            self.successful_transmissions += 1
            # Calculate packet loss rate
            total_transmissions = self.successful_transmissions + self.failed_transmissions
            self.packet_loss_rate = self.failed_transmissions / total_transmissions if total_transmissions > 0 else 0
            
            if self.packet_loss_rate < 0.05:  # Low packet loss rate
                if len(self.rtt_samples) >= 3:  # Wait for enough samples before using BDP
                    # Gradually increase window size based on BDP
                    optimal_size = self.calculate_bandwidth_delay_product(sum(self.rtt_samples) / len(self.rtt_samples))
                    self.window_size = min(self.max_size, 
                                         min(optimal_size, 
                                             self.window_size + 1))  # Gradual increase
                else:
                    # More conservative increase when we don't have enough samples
                    self.window_size = min(self.max_size, self.window_size + 1)
                
        return self.window_size

def modified_sliding_window_send(client, addr, packets, adaptive_window):
    """Modified sliding window send with adaptive window size"""
    global timeout_interval, estimated_rtt, deviation
    base = 0
    next_seq_num = 0
    window = {}
    max_seq_num = len(packets)
    
    while base < max_seq_num:
        current_window_size = adaptive_window.window_size
        
        # Send packets within the window
        while next_seq_num < min(base + current_window_size, max_seq_num):
            if next_seq_num not in window:
                try:
                    start_time = time.time()
                    response = send_rdt(client, addr, packets[next_seq_num])
                    rtt = time.time() - start_time
                    
                    if response is not None and response > base:
                        # Successful transmission
                        adaptive_window.update_window_size(rtt, packet_loss=False)
                        old_base = base
                        base = response
                        for seq in range(old_base, base):
                            window.pop(seq, None)
                        
                        # Calculate RTT dynamically
                        sample_rtt = time.time() - start_time
                        estimated_rtt = (1 - ALPHA) * estimated_rtt + ALPHA * sample_rtt
                        deviation = (1 - BETA) * deviation + BETA * abs(sample_rtt - estimated_rtt)
                        timeout_interval = max(MIN_TIMEOUT, min(MAX_TIMEOUT, estimated_rtt + 4 * deviation))
                        
                    else:
                        # Failed transmission
                        adaptive_window.update_window_size(rtt, packet_loss=True)
                        
                except Exception as e:
                    print(f"Error sending packet {next_seq_num}: {e}")
                    adaptive_window.update_window_size(timeout_interval, packet_loss=True)
                    return
                    
            window[next_seq_num] = True
            next_seq_num += 1

def modified_sliding_window_recv(client, expected_seq, adaptive_window):
    """Modified sliding window receive with adaptive window size"""
    global timeout_interval, estimated_rtt, deviation
    received_packets = {}
    buffer = {}
    last_received_time = time.time()

    while True:
        try:
            current_window_size = adaptive_window.window_size
            client.settimeout(timeout_interval)
            
            start_time = time.time()
            data, addr, next_seq = recv_rdt(client, expected_seq, buffer)
            rtt = time.time() - start_time
            
            if data:
                # Update window size based on successful reception
                adaptive_window.update_window_size(rtt, packet_loss=False)
                last_received_time = time.time()
                
                # Handle in-order packet
                if next_seq == expected_seq + 1:
                    yield {expected_seq: data}
                    expected_seq = next_seq
                    
                    # Process buffered packets that are now in order
                    while expected_seq in buffer and len(buffer) <= current_window_size:
                        buffered_data = buffer.pop(expected_seq)
                        yield {expected_seq: buffered_data}
                        expected_seq += 1
                
                # Handle out-of-order packet within window size
                elif next_seq > expected_seq + 1 and next_seq <= expected_seq + current_window_size:
                    buffer[next_seq-1] = data
                    
                # Clean up old buffered packets outside window
                current_time = time.time()
                if current_time - last_received_time > timeout_interval:
                    # Packet loss detected, update window size
                    adaptive_window.update_window_size(current_time - last_received_time, packet_loss=True)
                    # Remove packets outside window
                    buffer = {seq: data for seq, data in buffer.items() 
                            if seq <= expected_seq + current_window_size}

        except socket.timeout:
            # Update window size on timeout
            adaptive_window.update_window_size(timeout_interval, packet_loss=True)
            continue
            
        except Exception as e:
            print(f"Error in sliding window receive: {e}")
            adaptive_window.update_window_size(timeout_interval, packet_loss=True)
            continue