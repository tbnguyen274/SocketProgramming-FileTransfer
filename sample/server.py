import socket

HOST = "127.0.0.1" #loopback
SERVER_PORT = 65432
FORMAT = "utf8"

def recvList(conn):
    list = []
    item = conn.recv(1024).decode(FORMAT)
    while item != "end":
        list.append(item)
        # response
        conn.sendall(item.encode(FORMAT))
        item = conn.recv(1024).decode(FORMAT)
    return list

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

s.bind((HOST, SERVER_PORT))
s.listen()

print("--- SERVER SIDE ---")
print("server: ", HOST, SERVER_PORT)
print("Waiting for Clients")

try:
    conn, addr = s.accept()
    print("Client", addr, "connected")
    print("conn:", conn.getsockname())
    
    msg = None
    while msg != "x":
        msg = conn.recv(1024).decode(FORMAT)
        print("client", addr, "says", msg)
        if (msg == "list"):
            # response
            conn.sendall(msg.encode(FORMAT))
            list = recvList(conn)
            print("received list:")
            print(list)
except:
    print("Error")

print("END")
input()
conn.close()
s.close()