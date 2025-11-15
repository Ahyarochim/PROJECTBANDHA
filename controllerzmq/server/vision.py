import zmq
import json
import time

# Inisialisasi konteks dan socket ZMQ
ctx = zmq.Context()
sock = ctx.socket(zmq.PUSH)
sock.connect("tcp://127.0.0.1:5555")

# Loop pengiriman data vision setiap 1 detik
while True:
    data = {
        "type": "VISION",
        "object": "fake",
        "x": 120,
        "y": 45,
        "conf": 0.91
    }

    sock.send_string(json.dumps(data))
    print("Sent vision:", data)
    time.sleep(1)