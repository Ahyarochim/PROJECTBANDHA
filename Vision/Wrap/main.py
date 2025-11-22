# main.py
import cv2
from yolo_stream import start_stream
from autonomous import autonomous_loop
from configurasi import WIDTH, HEIGHT, FPS

Camera = cv2.VideoCapture(0)
Camera.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
Camera.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
Camera.set(cv2.CAP_PROP_FPS, FPS)

mode = input("Pilih mode (manual/autonomous): ")
if mode.lower() == "manual":
    start_stream(Camera)
elif mode.lower() == "autonomous":
    autonomous_loop(Camera)
