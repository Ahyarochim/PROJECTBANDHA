# autonomous.py
from stream import pixel_to_cm, cm_to_pulse
import serial
import time

stm = serial.Serial('COM5', 115200, timeout=1)

def send_to_stm(command):
    stm.write((command+"\n").encode())

def autonomous_loop(Camera):
    # contoh loop sederhana: ambil posisi dummy dulu
    # nanti bisa diganti pakai output deteksi YOLO
    while True:
        # ambil posisi objek dari YOLO
        obj_cx, center_x = 250, 240  # dummy, ganti pakai hasil YOLO

        offset_px = obj_cx - center_x
        offset_cm = pixel_to_cm(offset_px)
        pulse = cm_to_pulse(abs(offset_cm))

        if offset_cm > 0:
            send_to_stm(f"RIGHT:{pulse}")
        else:
            send_to_stm(f"LEFT:{pulse}")

        time.sleep(0.1)
