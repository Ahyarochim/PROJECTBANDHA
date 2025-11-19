# udp_client.py
import socket

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

while True:
    msg = input("Send: ").encode()
    sock.sendto(msg, ("127.0.0.1", 5005))
    data, _ = sock.recvfrom(1024)
    print("Reply:", data.decode())
