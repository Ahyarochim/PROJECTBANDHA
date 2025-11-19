import numpy as np 
import cv2 
import glob
import yaml

squareSizeCm = 2.7#misal
patternSize = (7,7)

imagePath = r'D:\Azqya Old Code 2\PY and NumPy\30 Day Plylist\Calibrate Foto\Data Foto Papan Catur\\*.jpg'

objp = np.zeros((patternSize[0]*patternSize[1], 3) , np.float32)
objp[:,:2] = np.mgrid[0:patternSize[0], 0:patternSize[1]].T.reshape(-1,2)
objp = objp*squareSizeCm

objPoints =[]
jpgPoints =[]

criteria =(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30,0.001)

images = glob.glob(imagePath)
img_size=None
found = 0

for fname in images:
    img = cv2.imread(fname)
    gray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    if img is None:
        print(f"❌ Gagal memuat gambar: {fname}")
        continue
    
    ret, corners = cv2.findChessboardCorners(gray, (7, 7), None)

    if ret:
        objPoints.append(objp)
        img_size = gray.shape[::-1]

        corners2 = cv2.cornerSubPix(
            gray,
            corners,
            (11,11),
            (-1,-1),
            criteria
        )
        jpgPoints.append(corners2)

        img = cv2.drawChessboardCorners(img,patternSize, corners2,ret)
        cv2.imshow("corners", img)
        cv2.waitKey(300)

        found += 1

cv2.destroyAllWindows()
print(f"Jumlah Gambar Valid :{found}")

if found > 0:
    print("⏳ Sedang memproses Kalibrasi Kamera... Proses ini mungkin memerlukan waktu beberapa saat.")
    ret, mtrx, dist, rvecs,tvecs = cv2.calibrateCamera(
        objPoints,jpgPoints, img_size, None, None
    )

    data ={
        "squareSize" : squareSizeCm,
        "patternSize" : list(patternSize),
        "CameraMatrix": mtrx.tolist(),
        "dist_coeff" : dist.tolist()
    }

    with open ("calibration_Matrix.yaml","w") as f:
        yaml.dump(data,f)
    print("Selesai")