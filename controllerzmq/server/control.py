import zmq
import json
import time

# Inisialisasi konteks dan socket ZMQ
ctx = zmq.Context()
sock = ctx.socket(zmq.PUSH)
sock.connect("tcp://127.0.0.1:5555")

# Loop pengiriman data kontrol setiap 1 detik
while True:
    data = {
        "type": "CONTROL",
        "command": "MOVE",
        "vx": 30,
        "vy": -10,
        "rotation": 15
    }

    sock.send_string(json.dumps(data))
    print("Sent control:", data)
    time.sleep(1)