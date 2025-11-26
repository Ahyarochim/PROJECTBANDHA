import cv2
from ultralytics import YOLO
import os
import numpy as np
import yaml
from collections import deque
import time

model_path = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Vision\Main Code\best.pt'

model= YOLO(model_path)
WINDOW_NAME = "Frame"
count = 0

fileName = r"D:\Azqya Old Code 2\PY and NumPy\30 Day Plylist\Day4\Data"
os.makedirs(fileName, exist_ok=True) 
Capture_Delay = 0.8
auto_capture = False

center_x = 720 // 2
center_y = 480 // 2
margin = 50 

camera =cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 720)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def Capture(frame):
    global count, lastCapture
    currentTime = time.time()
    if currentTime - lastCapture >= Capture_Delay:
        filename = os.path.join(fileName, f"Azqya{count}.jpg") 
        cv2.imwrite(filename, frame)
        print(f"Holaa O_o Gambar tersimpan: {filename}")
        count += 1
        lastCapture = currentTime


yaml_file = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Vision\calibration_Matrix.yaml'

bufferConf = deque(maxlen=5)
bufferCenter = deque(maxlen=5)

for box in results.boxes:
    lebel = model.names[int(box.cls[0])]
    conf = float(box.conf[0])
    x1,y1,x2,y2 = box.xyxy[0]

    cx = (x1 + x2) / 2
    cy = (y1 - y2) / 2

    bufferConf.append(conf)
    bufferCenter.append((cx,cy))

    if len(bufferConf) < 5 :
        continue
    steabelConf = sum(bufferConf) / len(bufferConf)
    steabelCx = sum([p[0] for p in bufferCenter]) / len(bufferCenter)
    steabelCy = sum([p[1] for p in bufferCenter]) / len(bufferCenter)

    if lebel == "azqya" and steabelConf > 0.6:
        detected = True
        # pos_cm = pixel_to_cm(cx,cy)
        print("Azqya")
        pass

detected = False

def loadCalibration(yaml_file):
    try:
        with open(yaml_file, 'r') as f :
            data= yaml.safe_load(f)
        mtx= np.array(data['CameraMatrix'])
        dist= np.array(data['dist_coeff'])

        if dist.ndim == 2 and dist.shape[0] == 5:
            dist = dist.T
        return mtx, dist

    except FileNotFoundError:
        print("File gak ada")
    except FileExistsError:
        print("Eror saat memuat data")
def UndisortFrame():
    global auto_capture
    mtx, dist = loadCalibration(yaml_file)
    if mtx is None and dist is None:
        print("parameternya Gak Kebaca")
        return 
    w = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

    newMatrix, roi = cv2.getOptimalNewCameraMatrix(mtx,dist,(w,h),1,(w,h))
    mapX, mapY = cv2.initUndistortRectifyMap(mtx,dist,None,newMatrix,(w,h),5)

    while True :
        success,frame = camera.read()
        if not success :
            break
        # frame = cv2.flip(frame,1)
        undisorted= cv2.remap(frame,mapX,mapY,cv2.INTER_LINEAR)
        result = model (undisorted, stream= True)

        anotade_frame_ist = list(result)

        if len(anotade_frame_ist) == 0:
            anotade_frame = frame
        else:
            anotade_frame = anotade_frame_ist[0].plot()

        for r in result:
            boxes = r.boxes
            if not boxes:
                continue
        cv2.imshow(WINDOW_NAME, anotade_frame)

        key = cv2.waitKey(1) & 0xFF 

        if  key == ord('q'):
            break
        if cv2.getWindowProperty(WINDOW_NAME,cv2.WND_PROP_VISIBLE) <1 :
            break
        if auto_capture:
            Capture(frame)

        if key == ord('c'):
            auto_capture = True
            print(f"X for stop")
        elif key == ord("x"):
            auto_capture= False
            print("Bay bayy ...")

UndisortFrame()
camera.release()
cv2.destroyAllWindows()