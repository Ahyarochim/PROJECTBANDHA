# yolo_stream.py
import cv2
import struct
from collections import deque
from ultralytics import YOLO
import yaml
import numpy as np
import socket
from config import *

model = YOLO(MODEL_PATH)

# =======================
# VISION UTILS
# =======================
def loadCalibration(path):
    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        mtx = np.array(data["CameraMatrix"])
        dist = np.array(data["dist_coeff"])
        if dist.ndim == 2 and dist.shape[0] == 5:
            dist = dist.T
        return mtx, dist
    except:
        print("Kalibrasi gagal")
        return None, None

def pixel_to_cm(px):
    return px / PIXEL_PER_CM

def cm_to_pulse(cm):
    return int(cm * CM_TO_PULSE)

# =======================
# STREAMING & DETEKSI
# =======================
def start_stream(Camera):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
    sock.settimeout(1.0)

    mtx, dist = loadCalibration(CALIB_FILE)
    if mtx is None or dist is None:
        return

    w, h = WIDTH, HEIGHT
    new_mtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (w, h), 5)
    
    bufferConf = deque(maxlen=5)
    
    while True:
        ret, frame = Camera.read()
        if not ret:
            continue

        undistorted_frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)
        results = model(undistorted_frame, device='cpu')
        boxes = results[0].boxes

        detected = False
        obj_cx = None
        obj_cy = None

        if len(boxes) > 0:
            box = boxes[0]
            x1, y1, x2, y2 = box.xyxy[0]
            conf = float(box.conf[0])
            cx = int((x1 + x2)/2)
            cy = int((y1 + y2)/2)
            bufferConf.append(conf)
            if len(bufferConf) == 5 and sum(bufferConf)/5 > 0.6:
                detected = True
                obj_cx, obj_cy = cx, cy

        annotated = results[0].plot()
        h_, w_ = annotated.shape[:2]
        center_x, center_y = w_//2, h_//2

        # Garis indikator
        color = (0,255,0) if detected and abs(obj_cx-center_x)<=MARGIN and abs(obj_cy-center_y)<=MARGIN else (0,0,255)
        cv2.line(annotated, (center_x, 0), (center_x, h_), color, 2)
        cv2.line(annotated, (0, center_y), (w_, center_y), color, 2)
        cv2.rectangle(annotated, (center_x-MARGIN, center_y-MARGIN), (center_x+MARGIN, center_y+MARGIN), color, 2)
        if detected:
            cv2.circle(annotated, (obj_cx, obj_cy), 6, (255,255,0), -1)

        # Kirim ke HP via UDP
        ok, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            continue
        data = buffer.tobytes()
        if len(data) <= MAX_PACKET_SIZE:
            packet = struct.pack("Q", len(data)) + data
            sock.sendto(packet, (IP_HP, PORT))
