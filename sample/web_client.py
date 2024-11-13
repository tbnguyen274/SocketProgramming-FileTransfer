import socket

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(("example.com", 80))
request = "GET / HTTP/1.0\r\nHost:example.com\r\n\r\n"
s.send(request.encode())
data = s.recv(10000)
print(data)
s.close()