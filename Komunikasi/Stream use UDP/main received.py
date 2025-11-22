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
import threading


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

# GLOBAL VARIABLES untuk komunikasi serial
serial_lock = threading.Lock()
last_stm32_response = ""
stm32_data_confirmed = False


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
        print(f"[INFO] Waiting for STM32 to be ready...")
        time.sleep(3)  # Tunggu STM32 siap
        
        # Flush buffer untuk bersihkan data lama
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        print(f"[OK] Connected to STM32 at {SERIAL_PORT} ({BAUDRATE} baud)")
        return ser
    except Exception as e:
        print(f"[ERROR] Cannot open serial port: {e}")
        print("[INFO] Program will continue without serial communication")
        return None


# ===== THREAD UNTUK MENERIMA DATA DARI STM32 =====
def serial_read_thread(ser):
    """Thread terpisah untuk membaca data dari STM32 secara kontinyu."""
    global last_stm32_response, stm32_data_confirmed
    
    buffer = ""
    
    while ser and ser.is_open:
        try:
            if ser.in_waiting > 0:
                # Baca data yang tersedia
                incoming = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                buffer += incoming
                
                # Cek apakah ada line lengkap (diakhiri \n)
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    
                    if line:  # Jika tidak kosong
                        with serial_lock:
                            last_stm32_response = line
                        
                        # Print response dari STM32
                        print(f"📥 [STM32]: {line}")
                        
                        # Cek apakah ini konfirmasi data diterima
                        if "RX:" in line or "X=" in line or "Y=" in line:
                            stm32_data_confirmed = True
                            print("   ✅ STM32 mengkonfirmasi data diterima!\n")
            
            time.sleep(0.01)  # Delay kecil untuk tidak overload CPU
            
        except Exception as e:
            print(f"[ERROR] Serial read error: {e}")
            break


# ===== FUNGSI KIRIM DATA KE STM32 DENGAN KONFIRMASI =====
def send_data_to_stm32(ser, dist_x_cm, dist_y_cm, timeout=2.0):
    """
    Kirim data ke STM32 dan tunggu konfirmasi.
    
    Args:
        ser: Serial object
        dist_x_cm: Jarak X dalam cm
        dist_y_cm: Jarak Y dalam cm
        timeout: Waktu tunggu konfirmasi (detik)
    
    Returns:
        True jika berhasil dan dikonfirmasi, False jika gagal
    """
    global stm32_data_confirmed
    
    if not ser or not ser.is_open:
        print("[ERROR] Serial port not open!")
        return False
    
    try:
        # Reset flag konfirmasi
        stm32_data_confirmed = False
        
        # Format data: "X:10.50,Y:5.25\n"
        data_to_send = f"X:{dist_x_cm:.2f},Y:{dist_y_cm:.2f}\n"
        
        # Kirim data
        with serial_lock:
            bytes_written = ser.write(data_to_send.encode())
            ser.flush()  # Pastikan data terkirim
        
        # Print info pengiriman
        print("\n" + "="*70)
        print("📤 MENGIRIM DATA KE STM32...")
        print(f"   Data: {data_to_send.strip()}")
        print(f"   X = {dist_x_cm:.2f} cm, Y = {dist_y_cm:.2f} cm")
        print(f"   Bytes sent: {bytes_written}")
        print(f"   Port: {ser.port}")
        
        # Tunggu konfirmasi dari STM32
        print(f"   ⏳ Menunggu konfirmasi dari STM32 (timeout: {timeout}s)...")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if stm32_data_confirmed:
                print("   ✅ DATA BERHASIL DIKIRIM DAN DIKONFIRMASI!")
                print("="*70 + "\n")
                return True
            time.sleep(0.05)
        
        # Timeout - tidak ada konfirmasi
        print("   ⚠️  TIMEOUT: Tidak ada konfirmasi dari STM32")
        print("   Kemungkinan: STM32 tidak merespons atau data tidak sampai")
        print("="*70 + "\n")
        return False
        
    except Exception as e:
        print(f"\n[ERROR] Gagal kirim ke STM32: {e}\n")
        return False


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
    global stm32_data_confirmed
    
    # Inisialisasi serial
    ser = init_serial()
    
    # Jika serial berhasil, start thread untuk baca data
    read_thread = None
    if ser and ser.is_open:
        read_thread = threading.Thread(target=serial_read_thread, args=(ser,), daemon=True)
        read_thread.start()
        print("[OK] Serial read thread started\n")
    
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
    last_send_time = 0
    
    try:
        print("\n" + "="*70)
        print("🚀 PROGRAM STARTED - Monitoring objek...")
        print("="*70 + "\n")
        
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
                    if label == "bukan azqya" and stable_conf > 0.6:
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

                        # Print ke terminal (setiap 1 detik untuk tidak spam)
                        current_time = time.time()
                        if current_time - last_send_time > 1.0:
                            print(f"🎯 [{label}] Conf: {stable_conf:.2f} | "
                                  f"X: {dist_x_cm:+.2f} cm | Y: {dist_y_cm:+.2f} cm | "
                                  f"In Center: {'✅' if in_center else '❌'}")
                        
                        # ===== KIRIM DATA KE STM32 =====
                        if in_center:
                            if not data_sent:
                                success = send_data_to_stm32(ser, dist_x_cm, dist_y_cm, timeout=2.0)
                                
                                if success:
                                    data_sent = True
                                    last_send_time = time.time()
                                else:
                                    print("⚠️  Pengiriman gagal, akan coba lagi saat objek masuk margin lagi\n")
                        else:
                            # Reset flag jika objek keluar dari margin
                            if data_sent:
                                print("\n⚠️  [INFO] Objek keluar dari margin - Siap kirim data lagi\n")
                                data_sent = False
                                stm32_data_confirmed = False

            # Tentukan warna garis
            color = (0, 255, 0) if in_center else (0, 0, 255)

            # GAMBAR GARIS & INDIKATOR
            cv2.line(annotated, (center_x, 0), (center_x, h), color, 2)
            cv2.line(annotated, (0, center_y), (w, center_y), color, 2)

            cv2.rectangle(
                annotated,
                (center_x - margin, center_y - margin),
                (center_x + margin, center_y + margin),
                color, 2
            )

            # Tampilkan jarak X dan Y di frame
            cv2.putText(
                annotated,
                f"X: {dist_x_cm:+.2f} cm",
                (center_x + margin + 10, center_y - 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 0),
                2
            )
            cv2.putText(
                annotated,
                f"Y: {dist_y_cm:+.2f} cm",
                (center_x + margin + 10, center_y - 39),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 0, 0),
                2
            )
            
            # Tampilkan status konfirmasi STM32
            status_text = "STM32: OK" if stm32_data_confirmed else "STM32: Waiting"
            status_color = (0, 255, 0) if stm32_data_confirmed else (0, 0, 255)
            cv2.putText(
                annotated,
                status_text,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                status_color,
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

    except KeyboardInterrupt:
        print("\n\n[INFO] Program dihentikan oleh user (Ctrl+C)")
    
    finally:
        print("\n[INFO] Cleaning up...")
        Camera.release()
        sock.close()
        if ser and ser.is_open:
            ser.close()
            print("[OK] Serial port closed")
        print("[OK] Program terminated\n")


if __name__ == "__main__":
    UndistortFrame()