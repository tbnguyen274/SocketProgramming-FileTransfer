# utils.py
import hashlib
import struct
import socket
import time

BUFFER_SIZE = 1024 * 4
INITIAL_TIMEOUT = 1.0  # Initial timeout in seconds
ALPHA = 0.125  # Smoothing factor for RTT
BETA = 0.25  # Smoothing factor for deviation
MIN_TIMEOUT = 1.0  # seconds
MAX_TIMEOUT = 60.0  # seconds

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

def recv_rdt(client, expected_seq, received_packets):
    """Receive a packet, check checksum, and handle ACK/NACK."""
    global estimated_rtt, deviation, timeout_interval
    while True:
        try:
            client.settimeout(timeout_interval)
            data, addr = client.recvfrom(BUFFER_SIZE)
            
            # Unpack and verify checksum
            packet_checksum = struct.unpack('!32s', data[:32])[0].decode()
            payload = data[32:]
            if calculate_checksum(payload) == packet_checksum:
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
                print("Checksum mismatch, sending NACK")
                nack = struct.pack('!I', -1)
                client.sendto(nack, addr)
        except socket.timeout:
            print("Timeout while receiving packet")
            continue
        except Exception as e:
            print(f"Unexpected error in recv_rdt: {e}")

def send_rdt(client, addr, packet):
    """Send a packet and handle retransmissions with dynamic timeout."""
    global estimated_rtt, deviation, timeout_interval
    while True:
        start_time = time.time()  # Measure RTT
        client.sendto(packet, addr)
        try:
            client.settimeout(timeout_interval)
            response, _ = client.recvfrom(BUFFER_SIZE)
            response_number = struct.unpack('!I', response)[0]
            # print(f"Received ACK {response_number}")
            
            if response_number == -1:  # NACK received
                print("NACK received, resending packet")
                continue
            
            # Calculate RTT dynamically
            sample_rtt = time.time() - start_time
            estimated_rtt = (1 - ALPHA) * estimated_rtt + ALPHA * sample_rtt
            deviation = (1 - BETA) * deviation + BETA * abs(sample_rtt - estimated_rtt)
            timeout_interval = max(MIN_TIMEOUT, min(MAX_TIMEOUT, estimated_rtt + 4 * deviation))
            
            return response_number  # ACK received
        except socket.timeout:
            print("Timeout, resending packet")
            
def sliding_window_send(client, addr, packets, window_size):
    """Improved sliding window send with per-packet timers and selective retransmissions."""
    base = 0
    next_seq_num = 0
    timers = {}
    acked = set()
    max_seq_num = len(packets)

    while base < max_seq_num:
        # Send packets within the window
        while next_seq_num < base + window_size and next_seq_num < max_seq_num:
            if next_seq_num not in acked:
                client.sendto(packets[next_seq_num], addr)
                timers[next_seq_num] = time.time()  # Start timer for the packet
            next_seq_num += 1

        try:
            # Wait for ACK
            client.settimeout(timeout_interval)
            response, _ = client.recvfrom(BUFFER_SIZE)
            ack_num = struct.unpack('!I', response)[0]

            if ack_num > base:
                # Mark packets as acknowledged
                acked.update(range(base, ack_num))
                base = ack_num  # Slide the window forward

            # Remove acknowledged packets' timers
            for seq in list(timers.keys()):
                if seq < base:
                    del timers[seq]

        except socket.timeout:
            # Handle timeout for individual packets
            for seq, send_time in timers.items():
                if time.time() - send_time > timeout_interval:
                    print(f"Retransmitting packet {seq}")
                    client.sendto(packets[seq], addr)
                    timers[seq] = time.time()  # Reset timer

def sliding_window_recv(client, expected_seq, window_size):
    """Improved sliding window receive with out-of-order buffering and selective acknowledgment."""
    received_packets = {}
    buffer = {}

    while True:
        data, addr, seq_num = recv_rdt(client, expected_seq, buffer)
        if seq_num == expected_seq:
            received_packets[seq_num - 1] = data
            expected_seq += 1
            # Deliver buffered in-order packets
            while expected_seq in buffer:
                received_packets[expected_seq] = buffer.pop(expected_seq)
                expected_seq += 1

            # Send cumulative ACK
            ack = struct.pack('!I', expected_seq)
            client.sendto(ack, addr)
        elif seq_num > expected_seq:
            # Buffer out-of-order packets
            buffer[seq_num] = data
            # Send duplicate ACK for the last successfully received sequence
            ack = struct.pack('!I', expected_seq)
            client.sendto(ack, addr)

        yield received_packets  # Yield received data for application processing
