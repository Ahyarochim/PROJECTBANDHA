import cv2
import socket
from ultralytics import YOLO
import os
import numpy as np
import yaml
from collections import deque
import struct
import time


#FILE
model_path = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Komunikasi\Stream use UDP\best.pt'
yml_File= r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Komunikasi\Stream use UDP\calibration_Matrix.yaml'

IP_HP = "10.104.17.134"
Port = 6000
WIDTH, HEIGHT = 480, 360
FPS = 15
JPEG_QUALITY = 50
MAX_PACKET_SIZE = 60000  

model = YOLO(model_path)

# GARIS INDIKATOR
margin = 100
bufferConf = deque(maxlen=5)

# LOAD KALIBRASI
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


# SOCKET
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
sock.settimeout(1.0) 

# CAMERA
Camera = cv2.VideoCapture(0)
Camera.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
Camera.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
Camera.set(cv2.CAP_PROP_FPS, FPS)
Camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not Camera.isOpened():
    print(" Kamera tidak bisa dibuka!")
    exit()

frame_count = 0
target_delay = 1.0 / FPS


# MAIN LOOP
def UndistortFrame():
    mtx, dist = loadCalibration(yml_File)
    if mtx is None or dist is None:
        return
    
    w = int(Camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(Camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
    new_mtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (w, h), 5)
    
    try:
        while True:
            ret, frame = Camera.read()
            if not ret:
                continue

            # YOLO DETECT

            undistorted_frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)
            results = model(undistorted_frame, device='cpu')
            boxes = results[0].boxes

            # INIT
            detected = False
            obj_cx = None
            obj_cy = None

            # CEK OBJEK & HITUNG POSISI
            if len(boxes) > 0:
                box = boxes[0]
                x1, y1, x2, y2 = box.xyxy[0]
                label = model.names[int(box.cls[0])]
                conf = float(box.conf[0])

                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)

                bufferConf.append(conf)

                if len(bufferConf) == 5:
                    stable_conf = sum(bufferConf) / 5

                    if stable_conf > 0.6:
                        detected = True
                        obj_cx, obj_cy = cx, cy
           
            # BUAT ANNOTATED FRAME
            annotated = results[0].plot()

            h, w = annotated.shape[:2]
            center_x = w // 2
            center_y = h // 2

            # CEK apakah objek masuk margin
            in_center = False
            if detected and abs(obj_cx - center_x) <= margin and abs(obj_cy - center_y) <= margin:
                in_center = True

            color = (0,255,0) if in_center else (0,0,255)

            # GAMBAR GARIS >>> 
            cv2.line(annotated, (center_x, 0), (center_x, h), color, 2)           ### >> Garis vertikal
            cv2.line(annotated, (0, center_y), (w, center_y), color, 2)           ### >> Garis horizontal

            cv2.rectangle(                                                    ### >> Kotak margin
                annotated,
                (center_x - margin, center_y - margin),
                (center_x + margin, center_y + margin),
                color, 2
            )

            if detected:                                                      ### >> Titik tengah objek
                cv2.circle(annotated, (obj_cx, obj_cy), 6, (255,255,0), -1)


            # Kirim ke Android via UDP
            ok, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                continue

            data = buffer.tobytes()
            data_size = len(data)

            if data_size <= MAX_PACKET_SIZE:
                packet = struct.pack("Q", data_size) + data
                sock.sendto(packet, (IP_HP, Port))


    finally:
        Camera.release()
        sock.close()



UndistortFrame()