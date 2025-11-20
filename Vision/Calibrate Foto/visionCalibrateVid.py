import cv2
import numpy as np
import yaml
import os

calibrationFile = r"D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Vision\Calibrate Foto\calibration_Matrix.yaml"

def loadCalibrationData(yaml_file):
    try:
        with open(yaml_file,'r') as f:
            data = yaml.safe_load(f)
        
        mtx = np.array(data['CameraMatrix'])
        dist = np.array(data['dist_coeff']) 
        if dist.ndim == 2 and dist.shape[0] == 5:
            dist= dist.T
        print("Parameter Kalibrasi Dimuat")
        return mtx, dist
    
    except FileNotFoundError:
        print(f"❌ EROR: File '{yaml_file}' tidak ditemukan.")
        return None, None
    except Exception as e:
        print(f"❌ Eror saat memuat data yml: {e}") 
        return None, None 

def undistortVidio():
    mtx, dist = loadCalibrationData(calibrationFile)
    
    if mtx is None or dist is None:
        print("Gagal melanjutkan karena parameter kalibrasi tidak dimuat.")
        return
    camera = cv2.VideoCapture(0)
    if not camera.isOpened():
        print('❌ Eror, tidak bisa buka kamera nya.')
        return
    
    w = int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))

    newMatrix, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w,h), 1, (w,h))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, newMatrix, (w,h), 5) # <--- FIX: Tambah ukuran frame dan tipe data

    while True:
        ret,frame = camera.read()

        if not ret:
            print("❌ Gagal Menerima frame")
            break

        frame= cv2.flip(frame,1) 
        undistorted_frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)

        cv2.imshow('Undistorted Frame', undistorted_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
        
    camera.release()
    cv2.destroyAllWindows()

if __name__=='__main__':
    undistortVidio()