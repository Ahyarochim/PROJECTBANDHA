import cv2
import socket
from ultralytics import YOLO
import os
import numpy as np
import yaml
from collections import deque
import struct
import time
import serial


#FILE
model_path = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Komunikasi\Stream use UDP\best.pt'
yml_File= r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Komunikasi\Stream use UDP\Calibration_Matrix copy.yaml'

# ===== SERIAL CONFIG (STM32) =====
SERIAL_PORT = "COM3"  # Windows: "COM3", "COM4", dll | Linux: "/dev/ttyACM0" atau "/dev/ttyUSB0"
BAUDRATE = 115200

# ===== UDP CONFIG =====
IP_HP = "10.105.42.54"
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

        print(">> DEBUG: Keys:", data.keys())
        print(">> DEBUG: CameraMatrix:", data["CameraMatrix"])
        print(">> DEBUG: dist_coeff:", data["dist_coeff"])
        print(">> DEBUG: PIXEL_PER_CM:", data["PIXEL_PER_CM"])
        
        mtx = np.array(data["CameraMatrix"])
        dist = np.array(data["dist_coeff"])
        dist = dist.reshape(1, -1)
        pxlPercm = float(data["PIXEL_PER_CM"])

        return mtx, dist, pxlPercm
    except Exception as e:
        print(f"Kalibrasi gagal: {e}")
        return None, None, None


# ===== INIT SERIAL =====
def init_serial():
    """Inisialisasi koneksi serial ke STM32."""
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
        time.sleep(2)  # Tunggu STM32 siap
        print(f"[OK] Connected to STM32 at {SERIAL_PORT} ({BAUDRATE} baud)")
        return ser
    except Exception as e:
        print(f"[ERROR] Cannot open serial port: {e}")
        print("[INFO] Program will continue without serial communication")
        return None


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


# ===== MAIN LOOP =====
def UndistortFrame():
    # Inisialisasi serial
    ser = init_serial()
    
    mtx, dist, pxlPercm = loadCalibration(yml_File)
    if mtx is None or dist is None:
        if ser and ser.is_open:
            ser.close()
        return
    
    w = int(Camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(Camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
    new_mtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (w, h), 5)
    
    # Flag untuk tracking pengiriman data
    data_sent = False
    
    try:
        while True:
            ret, frame = Camera.read()
            if not ret:
                continue

            # UNDISTORT & DETECT
            undistorted_frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)
            results = model(undistorted_frame, device='cpu')
            boxes = results[0].boxes

            annotated = results[0].plot() if results else undistorted_frame
            h, w = annotated.shape[:2]
            center_x = w // 2
            center_y = h // 2

            # INIT
            detected = False
            obj_cx = None
            obj_cy = None
            in_center = False
            dist_x_cm = 0
            dist_y_cm = 0

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
                    if label == "Azqya" and stable_conf > 0.6:
                        detected = True
                        obj_cx, obj_cy = cx, cy
                        
                        # Hitung offset dari center
                        offset_x = obj_cx - center_x
                        offset_y = obj_cy - center_y

                        # Konversi ke cm
                        dist_x_cm = offset_x / pxlPercm
                        dist_y_cm = offset_y / pxlPercm
                        
                        # CEK apakah objek masuk margin
                        if (abs(cx - center_x) <= margin and 
                            abs(cy - center_y) <= margin):
                            in_center = True

                        # Print ke terminal
                        print(f"[{label}] Confidence: {stable_conf:.2f} | "
                              f"Jarak X: {dist_x_cm:.2f} cm | "
                              f"Jarak Y: {dist_y_cm:.2f} cm | "
                              f"In Center: {in_center}")
                        
                        # ===== KIRIM DATA KE STM32 =====
                        # Kirim jika objek berada di dalam margin (in_center = True)
                        if in_center:
                            if not data_sent:  # Kirim hanya sekali
                                if ser and ser.is_open:
                                    try:
                                        # Format: "X:10.5,Y:5.2\n"
                                        data_to_send = f"X:{dist_x_cm:.2f},Y:{dist_y_cm:.2f}\n"
                                        ser.write(data_to_send.encode())
                                        
                                        # Print dengan jelas di terminal
                                        print("\n" + "="*70)
                                        print("✅ DATA BERHASIL DIKIRIM KE STM32!")
                                        print(f"   📤 Data: {data_to_send.strip()}")
                                        print(f"   📍 X = {dist_x_cm:.2f} cm, Y = {dist_y_cm:.2f} cm")
                                        print("="*70 + "\n")
                                        
                                        data_sent = True  # Set flag supaya tidak kirim lagi
                                    except Exception as e:
                                        print(f"\n[ERROR] Gagal kirim ke STM32: {e}\n")
                        else:
                            # Reset flag jika objek keluar dari margin
                            if data_sent:
                                print("\n⚠️  [INFO] Objek keluar dari margin - Siap kirim data lagi\n")
                                data_sent = False

            # Tentukan warna garis
            color = (0, 255, 0) if in_center else (0, 0, 255)

            # GAMBAR GARIS & INDIKATOR
            cv2.line(annotated, (center_x, 0), (center_x, h), color, 2)  # Garis vertikal
            cv2.line(annotated, (0, center_y), (w, center_y), color, 2)  # Garis horizontal

            cv2.rectangle(  # Kotak margin
                annotated,
                (center_x - margin, center_y - margin),
                (center_x + margin, center_y + margin),
                color, 2
            )

            # Tampilkan jarak X dan Y di frame
            cv2.putText(
                annotated,
                f"X: {dist_x_cm:.2f} cm",
                (center_x + margin + 10, center_y - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 0),
                2
            )
            cv2.putText(
                annotated,
                f"Y: {dist_y_cm:.2f} cm",
                (center_x + margin + 10, center_y - 39),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 0),
                2
            )

            # Gambar titik tengah objek
            if obj_cx is not None:
                cv2.circle(annotated, (int(obj_cx), int(obj_cy)), 5, (255, 255, 0), -1)

            # Kirim ke Android via UDP
            ok, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                continue

            data = buffer.tobytes()
            data_size = len(data)

            if data_size <= MAX_PACKET_SIZE:
                header = f"{data_size:08d}".encode('ascii')
                packet = header + data
                sock.sendto(packet, (IP_HP, Port))

    finally:
        Camera.release()
        sock.close()
        if ser and ser.is_open:
            ser.close()
            print("[OK] Serial port closed")


if __name__ == "__main__":
    UndistortFrame()