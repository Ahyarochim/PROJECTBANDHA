import cv2
import socket
from ultralytics import YOLO
import os
import numpy as np
import yaml
from collections import deque
import time
import serial
import sys


# ===== FILE =====
model_path = r'best.pt'
yml_File = r'calibration_Matrix.yaml'

# ===== SERIAL CONFIG (pastikan sesuai port STM32) =====
SERIAL_PORT = "COM5"        # Windows -> ubah sesuai PC kamu
BAUDRATE = 115200

# ===== UDP CONFIG =====
IP_HP = "10.104.223.162"
Port = 6000
WIDTH, HEIGHT = 480, 360
FPS = 15
JPEG_QUALITY = 50
MAX_PACKET_SIZE = 60000  

model = YOLO(model_path)
margin = 100
bufferConf = deque(maxlen=5)

# KONSTANTA UNTUK HITUNG JARAK
REAL_FACE_WIDTH_CM = 20.0  # ubah sesuai ukuran sebenarnya

def loadCalibration(path):
    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        return np.array(data["CameraMatrix"]), np.array(data["dist_coeff"])
    except:
        print("Kalibrasi gagal")
        return None, None


def calculateDistance(bbox_width_pixels, focal_length_x, real_width_cm):
    if bbox_width_pixels <= 0:
        return None
    return (real_width_cm * focal_length_x) / bbox_width_pixels


def init_serial():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
        time.sleep(2)
        print(f"[OK] Terhubung ke STM32 ({SERIAL_PORT})")
        return ser
    except Exception as e:
        print(f"[ERROR] Serial gagal: {e}")
        return None


sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
sock.settimeout(1.0)

Camera = cv2.VideoCapture(0)
Camera.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
Camera.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)


def UndistortFrame():
    ser = init_serial()
    mtx, dist = loadCalibration(yml_File)
    if mtx is None: return

    focal_length_x = mtx[0, 0]
    w = int(Camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(Camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
    new_mtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (w, h), 5)

    while True:
        ret, frame = Camera.read()
        if not ret: continue

        undistorted = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)
        results = model(undistorted, device='cpu')
        boxes = results[0].boxes

        distance_cm = None

        if len(boxes) > 0:
            box = boxes[0]
            x1, y1, x2, y2 = box.xyxy[0]
            conf = float(box.conf[0])
            bbox_width = int(x2 - x1)

            bufferConf.append(conf)
            if len(bufferConf) == 5 and sum(bufferConf) / 5 > 0.6:
                distance_cm = calculateDistance(bbox_width, focal_length_x, REAL_FACE_WIDTH_CM)

                if distance_cm:
                    print(f"[INFO] Distance = {distance_cm:.1f} cm")

                    # ======== KIRIM KE STM32 ========
                    if ser and ser.is_open:
                        try:
                            msg = f"{distance_cm:.1f}\n"
                            ser.write(msg.encode())
                        except Exception as e:
                            print(f"[Serial ERROR] {e}")

        annotated = results[0].plot()

        ok, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if ok:
            data = buffer.tobytes()
            if len(data) <= MAX_PACKET_SIZE:
                header = f"{len(data):08d}".encode('ascii')
                sock.sendto(header + data, (IP_HP, Port))


    Camera.release()
    sock.close()
    if ser and ser.is_open:
        ser.close()


UndistortFrame()
