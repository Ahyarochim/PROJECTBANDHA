import cv2
from ultralytics import YOLO
import os
import numpy as np
import yaml
from collections import deque
import time

model_path = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Vision\Main Code\best.pt'
yaml_file = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Vision\calibration_Matrix.yaml'
fileName = r"D:\Azqya Old Code 2\PY and NumPy\30 Day Plylist\Day4\Data"

os.makedirs(fileName, exist_ok=True)

model = YOLO(model_path)
WINDOW_NAME = "Frame"

# resolusi kamera
X = 480   # width
Y = 300   # height

camera = cv2.VideoCapture(0)
camera.set(3, X)
camera.set(4, Y)

# ukuran kotak tengah
margin = 100

count = 0
lastCapture = 0
Capture_Delay = 0.8
auto_capture = False

bufferConf = deque(maxlen=5)

def Capture(frame):
    global count, lastCapture
    t = time.time()
    if t - lastCapture >= Capture_Delay:
        filename = os.path.join(fileName, f"Azqya{count}.jpg")
        cv2.imwrite(filename, frame)
        print("Saved:", filename)
        lastCapture = t
        count += 1


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


def UndistortFrame():
    global auto_capture

    mtx, dist = loadCalibration(yaml_file)
    if mtx is None:
        return

    w = int(camera.get(3))
    h = int(camera.get(4))

    newMtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1)
    mapX, mapY = cv2.initUndistortRectifyMap(mtx, dist, None, newMtx, (w, h), 5)

    while True:
        ret, frame = camera.read()
        if not ret:
            break

        undist = cv2.remap(frame, mapX, mapY, cv2.INTER_LINEAR)

        # Dapatkan ukuran frame AKTUAL setelah undistort
        actual_h, actual_w = undist.shape[:2]
        center_x = actual_w // 2
        center_y = actual_h // 2

        # yolo
        results = list(model(undist, stream=True))
        detected = False
        in_center = False  
        obj_cx = None
        obj_cy = None

        if results:
            r = results[0]
            for box in r.boxes:
                label = model.names[int(box.cls[0])]
                conf = float(box.conf[0])

                x1, y1, x2, y2 = box.xyxy[0]
                cx = float((x1 + x2) / 2)
                cy = float((y1 + y2) / 2)

                bufferConf.append(conf)

                if len(bufferConf) == 5:
                    stable_conf = sum(bufferConf) / 5

                    if label == "Azqya" and stable_conf > 0.6:
                        detected = True
                        obj_cx, obj_cy = cx, cy

                        # cek apakah objek berada dalam kotak tengah
                        if (abs(cx - center_x) <= margin and 
                            abs(cy - center_y) <= margin):
                            in_center = True

        annotated = results[0].plot() if results else undist.copy()

        # annotated frame punya ukuran yang sama
        ann_h, ann_w = annotated.shape[:2]
        center_x = ann_w // 2
        center_y = ann_h // 2

        # warna indikator
        color = (255, 0, 0) if in_center else (0, 0, 255)

        # garis tengah vertikal
        cv2.line(annotated, (center_x, 0), (center_x, ann_h), color, 2)

        # garis horisontal
        cv2.line(annotated, (0, center_y), (ann_w, center_y), color, 2)

        # kotak margin
        cv2.rectangle(
            annotated,
            (center_x - margin, center_y - margin),
            (center_x + margin, center_y + margin),
            color,
            2
        )

        # titik objek
        if obj_cx is not None:
            cv2.circle(annotated, (int(obj_cx), int(obj_cy)), 5, (255, 255, 0), -1)

        cv2.imshow(WINDOW_NAME, annotated)

        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        if cv2.getWindowProperty(WINDOW_NAME,cv2.WND_PROP_VISIBLE) <1 :
            break
        
        if key == ord('c'):
            auto_capture = True
        if key == ord('x'):
            auto_capture = False

        if auto_capture and detected:
            Capture(undist)

    camera.release()
    cv2.destroyAllWindows()


UndistortFrame()