import cv2
import os
import time

windowName = "Camera"

camera = cv2.VideoCapture(0)
if not(camera.isOpened):
    print("Camera is bot Opend")
    exit

camera.set(cv2.CAP_PROP_FRAME_WIDTH, 400)
camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 360)

count = 0
lastCapture = 0
Captur_Deelay = 0.001

auto_capture = False
fileName = r"D:\Azqya Old Code 2\PY and NumPy\30 Day Plylist\Calibrate Foto\Data Foto Papan Catur" #path foldernyan nya
os.makedirs(fileName, exist_ok=True)

def Capture(frame):
        global count, lastCapture
        currentTime = time.time()
        if currentTime - lastCapture >= Captur_Deelay:
            filename = os.path.join(fileName, f"Calibration{count}.jpg") 
            cv2.imwrite(filename, frame)
            print(f"Holaa O_o Gambar tersimpan: {filename}")
            count += 1
            lastCapture = currentTime

while True:
    success,frame = camera.read()
    if not success :
        break

    width = 700
    rasio = width/frame.shape[1]
    height = int(frame.shape[0]*rasio)
    cv2.namedWindow(windowName, cv2.WINDOW_NORMAL)

    frame = cv2.flip(frame,1)
    cv2.imshow(windowName, frame)

    
    key = cv2.waitKey(1) & 0xFF 

    if  key == ord('q'):
       break
    if cv2.getWindowProperty(windowName,cv2.WND_PROP_VISIBLE) <1 :
        break
    if auto_capture:
        Capture(frame)

    if key == ord('c'):
       auto_capture = True
       print(f"X for stop")
    elif key == ord('x'):
        Capture()

camera.release()
cv2.destroyAllWindows()