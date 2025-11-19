import cv2
import socket
from ultralytics import YOLO
import struct
import time

IP_HP = "10.107.3.167"
Port = 6000
WIDTH, HEIGHT = 480, 360
FPS = 15
JPEG_QUALITY = 50
MODEL_PATH = r'best.pt'
MAX_PACKET_SIZE = 60000  

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
sock.settimeout(1.0) 

Camera = cv2.VideoCapture(0)
Camera.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
Camera.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
Camera.set(cv2.CAP_PROP_FPS, FPS)
Camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not Camera.isOpened():
    print(" Kamera tidak bisa dibuka!")
    exit()

try:
    model = YOLO(MODEL_PATH)
    model.fuse()
    print(" Model loaded!")
except Exception as e:
    print(f" Error loading model: {e}")
    Camera.release()
    exit()

frame_count = 0
target_delay = 1.0 / FPS


try:
    while True:
        start_time = time.time()
        ret, frame = Camera.read()
        if not ret:
            print(" Frame tidak terbaca, skip...")
            continue
        
        if frame.shape[1] != WIDTH or frame.shape[0] != HEIGHT:
            frame = cv2.resize(frame, (WIDTH, HEIGHT))

        try:
            results = model(frame, device='cpu') #verbose=False
            annotated = results[0].plot()
        except Exception as e:
            print(f"YOLO error: {e}")
            annotated = frame
            
        Ok_encode, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not Ok_encode:
            print(" Encoding gagal!")
            continue
        
        data = buffer.tobytes()
        data_size = len(data)
        
        if data_size > MAX_PACKET_SIZE:
            print(f" Data terlalu besar ({data_size} bytes), turunkan JPEG quality!")
            continue
        
        packet = struct.pack("Q", data_size) + data
        
        try:
            sock.sendto(packet, (IP_HP, Port))
        except socket.error as e:
            print(f"Socket error: {e}")
            time.sleep(0.5)
            continue
        
        elapsed = time.time() - start_time
        if elapsed < target_delay:
            sleep_time = max(0, target_delay - elapsed)
            time.sleep(sleep_time)

except KeyboardInterrupt:
    print("\n Streaming dihentikan oleh user")
except Exception as e:
    print(f"\n Error tidak terduga: {e}")
finally:
    print(" Membersihkan resource...")
    Camera.release()
    sock.close()
    print(" Cleanup selesai!")