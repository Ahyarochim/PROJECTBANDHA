import cv2

for i in range(10):
    cam = cv2.VideoCapture(i)
    if cam.isOpened():
        print(f"Index {i} : TERDETEKSI")
        cam.release()
    else:
        print(f"Index {i} : -")
