# udp_server.py
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", 5005))

print("UDP server ready")

while True:
    data, addr = sock.recvfrom(1024)
    print("From", addr, ":", data.decode())
    sock.sendto(b"ACK", addr)
