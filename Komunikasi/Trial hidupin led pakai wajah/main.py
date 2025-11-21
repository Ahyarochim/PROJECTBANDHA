import cv2
import socket
from ultralytics import YOLO
import os
import numpy as np
import yaml
# from collections import deque
import time

model_path = r'D:\Ahya Rochim\Kuliah\BANDHAYUDHA\PROJECT BANDHA\Komunikasi\Trial hidupin led pakai wajah\best.pt'

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

IP_HP = "10.104.144.56"
Port = 6000
WIDTH, HEIGHT = 480, 360
FPS = 15
JPEG_QUALITY = 50
MODEL_PATH = r'best.pt'
MAX_PACKET_SIZE = 60000  

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
sock.settimeout(1.0) 

camera =cv2.VideoCapture(0)
camera.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
camera.set(cv2.CAP_PROP_FPS, FPS)
camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

def Capture(frame):
    global count, lastCapture
    currentTime = time.time()
    if currentTime - lastCapture >= Capture_Delay:
        filename = os.path.join(fileName, f"Azqya{count}.jpg") 
        cv2.imwrite(filename, frame)
        print(f"Holaa O_o Gambar tersimpan: {filename}")
        count += 1
        lastCapture = currentTime


yaml_file = r'D:\Ahya Rochim\Kuliah\BANDHAYUDHA\PROJECT BANDHA\Komunikasi\Trial hidupin led pakai wajah\calibration_Matrix.yaml'

# bufferConf = deque(maxlen=5)
# bufferCenter = deque(maxlen=5)

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
        
frame_count = 0
target_delay = 1.0 / FPS

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
        start_time = time.time()
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

        Ok_encode, buffer = cv2.imencode('.jpg', anotade_frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not Ok_encode:
            print(" Encoding gagal!")
            continue
        
        data = buffer.tobytes()
        data_size = len(data)
        
        header = f"{data_size:08d}".encode('ascii')  # "00012345" as 8 ASCII bytes
        packet = header + data

        try:
            sock.sendto(packet, (IP_HP, Port))
        except socket.error as e:
            print(f"Socket error: {e}")
            time.sleep(0.5)
            continue
        
        elapsed = time.time() - start_time
        if elapsed < target_delay:
            sleep_time = max(0, target_delay - elapsed)
            time.sleep(sleep_time)

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
sock.close()
cv2.destroyAllWindows()