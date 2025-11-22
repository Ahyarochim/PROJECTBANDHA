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


#FILE
model_path = r'D:\Ahya Rochim\Kuliah\BANDHAYUDHA\PROJECT BANDHA\Komunikasi\Stream use UDP\best.pt'
yml_File = r'D:\Ahya Rochim\Kuliah\BANDHAYUDHA\PROJECT BANDHA\Komunikasi\Stream use UDP\Calibration_Matrix copy.yaml'

# SERIAL CONFIG (STM32)
SERIAL_PORT = "/dev/ttyACM0"  # Ubah sesuai port STM32 di Linux (biasanya /dev/ttyUSB0 atau /dev/ttyACM0)
BAUDRATE = 115200

# UDP CONFIG
IP_HP = "10.104.223.162"
Port = 6000
WIDTH, HEIGHT = 480, 360
FPS = 15
JPEG_QUALITY = 50
MAX_PACKET_SIZE = 60000  

model = YOLO(model_path)

# GARIS INDIKATOR
margin = 100
bufferConf = deque(maxlen=5)

# ===== KONSTANTA UNTUK DISTANCE CALCULATION =====
# PENTING: Ukur lebar wajah Azqya secara fisik (telinga ke telinga atau pipi ke pipi)
REAL_FACE_WIDTH_CM = 20.0  # Ganti dengan ukuran sebenarnya dalam cm!

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


# HITUNG JARAK
def calculateDistance(bbox_width_pixels, focal_length_x, real_width_cm):
    """
    Menghitung jarak objek dari kamera menggunakan pinhole camera model
    
    Distance = (Real_Width × Focal_Length) / Pixel_Width
    
    Args:
        bbox_width_pixels: Lebar bounding box dalam piksel
        focal_length_x: Focal length kamera dari matrix kalibrasi (fx)
        real_width_cm: Lebar objek sebenarnya dalam cm
    
    Returns:
        Jarak dalam cm
    """
    if bbox_width_pixels == 0:
        return None
    
    distance_cm = (real_width_cm * focal_length_x) / bbox_width_pixels
    return distance_cm


# INIT SERIAL
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


# MAIN LOOP
def UndistortFrame():
    # Inisialisasi serial
    ser = init_serial()
    
    mtx, dist = loadCalibration(yml_File)
    if mtx is None or dist is None:
        if ser and ser.is_open:
            ser.close()
        return
    
    # Ambil focal length dari camera matrix
    focal_length_x = mtx[0, 0]  # fx
    focal_length_y = mtx[1, 1]  # fy
    print(f"Focal Length: fx={focal_length_x:.2f}, fy={focal_length_y:.2f}")
    
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

            # YOLO DETECT
            undistorted_frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)
            results = model(undistorted_frame, device='cpu')
            boxes = results[0].boxes

            # INIT
            detected = False
            obj_cx = None
            obj_cy = None
            distance_cm = None

            # CEK OBJEK & HITUNG POSISI + JARAK
            if len(boxes) > 0:
                box = boxes[0]
                x1, y1, x2, y2 = box.xyxy[0]
                label = model.names[int(box.cls[0])]
                conf = float(box.conf[0])

                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                
                # Hitung lebar bounding box
                bbox_width = int(x2 - x1)
                bbox_height = int(y2 - y1)

                bufferConf.append(conf)

                if len(bufferConf) == 5:
                    stable_conf = sum(bufferConf) / 5

                    if stable_conf > 0.6:
                        detected = True
                        obj_cx, obj_cy = cx, cy
                        
                        # HITUNG JARAK!
                        distance_cm = calculateDistance(
                            bbox_width, 
                            focal_length_x, 
                            REAL_FACE_WIDTH_CM
                        )
                        
                        # Print ke terminal
                        print(f"[{label}] Confidence: {stable_conf:.2f} | "
                              f"BBox: {bbox_width}x{bbox_height}px | "
                              f"Distance: {distance_cm:.1f} cm ({distance_cm/100:.2f} m)")
                        
                        # KIRIM KE STM32 jika jarak = 50cm (±2cm toleransi) - HANYA SEKALI
                        if distance_cm is not None and abs(distance_cm - 50.0) < 2.0:
                            if not data_sent:  # Kirim hanya jika belum pernah kirim
                                adjusted_distance = distance_cm - 5  # 50cm - 5 = 45cm
                                if ser and ser.is_open:
                                    try:
                                        # Format: "45.0\n" (sesuai format yang diharapkan STM32)
                                        data_to_send = f"{adjusted_distance:.1f}\n"
                                        ser.write(data_to_send.encode())
                                        
                                        # Print dengan jelas di terminal
                                        print("\n" + "="*70)
                                        print("✅ DATA BERHASIL DIKIRIM KE STM32!")
                                        print(f"   📤 Data: {data_to_send.strip()} cm")
                                        print(f"   🤖 Robot akan maju: {adjusted_distance:.1f} cm")
                                        print("="*70 + "\n")
                                        
                                        data_sent = True  # Set flag supaya tidak kirim lagi
                                    except Exception as e:
                                        print(f"\n[ERROR] Gagal kirim ke STM32: {e}\n")
                        else:
                            # Reset flag jika jarak jauh dari 50cm (lebih dari 10cm)
                            if distance_cm is not None and abs(distance_cm - 50.0) > 10.0:
                                if data_sent:
                                    print("\n⚠️  [INFO] Jarak berubah jauh - Siap kirim data lagi\n")
                                    data_sent = False
           
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
                
                # Tampilkan jarak di frame
                if distance_cm:
                    distance_text = f"{distance_cm:.1f} cm"
                    cv2.putText(
                        annotated, 
                        distance_text,
                        (obj_cx - 50, obj_cy - 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),  # Kuning
                        2
                    )

            # Kirim ke Android via UDP
            ok, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if not ok:
                continue

            data = buffer.tobytes()
            data_size = len(data)

            if data_size <= MAX_PACKET_SIZE:
                # Format header as 8-character ASCII string (e.g., "00016640")
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