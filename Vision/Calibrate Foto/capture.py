import cv2
import os
import numpy as np
import os
import yaml
import time

windowName = "Camera"
calibrationFile = 'calibration_Matrix.yaml'

count = 0
lastCapture = 0
Captur_Deelay = 0.001

auto_capture = False
fileName = r"D:\Azqya Old Code 2\PY and NumPy\30 Day Plylist\Calibrate Foto\Data Foto Papan Catur" #path foldernyan nya
os.makedirs(fileName, exist_ok=True)

yaml_file = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Vision\calibration_Matrix.yaml'

camera = cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, 400)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

def Capture(frame):
        global count, lastCapture
        currentTime = time.time()
        if currentTime - lastCapture >= Captur_Deelay:
            filename = os.path.join(fileName, f"Calibration{count}.jpg") 
            cv2.imwrite(filename, frame)
            print(f"Holaa O_o Gambar tersimpan: {filename}")
            count += 1
            lastCapture = currentTime

def load_calibration_data(yaml_file):
    try:
        with open(yaml_file,'r') as f:
            data= yaml.safe_load(f)

        mtx= np.array(data['CameraMatrix'])
        dist= np.array(data['dist_coeff'])

        if dist.ndim == 2 and dist.shape[0] == 5:
            dist = dist.T
        return mtx, dist

    except FileNotFoundError:
        print(f"Eror karena file gak ada")
        return None, None
    except Exception:
        print(f"Eror saat memuat data yml")
        
def UndistortVidio():
    global auto_capture
    mtx, dist = load_calibration_data(yaml_file)

    if mtx is None or dist is None :
        print("Gagal Melanjutkan, Parameternya gak ada")
        return
    w = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

    newMatrix, roi = cv2.getOptimalNewCameraMatrix(mtx,dist,(w,h),1,(w,h))
    mapX, mapY = cv2.initUndistortRectifyMap(mtx,dist,None,newMatrix,(w,h),5)

    while True:
        success,frame = camera.read()
        if not success :
            break

        # width = 700
        # rasio = width/frame.shape[1]
        # height = int(frame.shape[0]*rasio)
        cv2.namedWindow(windowName, cv2.WINDOW_NORMAL)

        frame = cv2.flip(frame,1)
        UndistortVidioFrame= cv2.remap(frame,mapX,mapY,cv2.INTER_LINEAR)

        cv2.imshow('Original', frame)
        cv2.imshow(windowName, UndistortVidioFrame)

        print("Camera Matrix:\n", mtx)
        print("Distortion:\n", dist)

        key = cv2.waitKey(1) & 0xFF 

        if  key == ord('q'):
            break
        if cv2.getWindowProperty(windowName,cv2.WND_PROP_VISIBLE) <1 :
            break
        if auto_capture:
            Capture(UndistortVidioFrame)

        if key == ord('c'):
            auto_capture = True
            print(f"X for stop")
        elif key == ord('x'):
            Capture(UndistortVidioFrame)


UndistortVidio()
camera.release()
cv2.destroyAllWindows()

