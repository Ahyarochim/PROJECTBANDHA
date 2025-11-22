import numpy as np
import cv2
import glob
import yaml

squareSizeCm = 2.7
patternSize = (7,7)
imagePath = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Vision\Calibrate Foto\Data Foto Papan Catur\\*.jpg'

objp = np.zeros((patternSize[0]*patternSize[1], 3), np.float32)
objp[:,:2] = np.mgrid[0:patternSize[0], 0:patternSize[1]].T.reshape(-1,2)
objp = objp * squareSizeCm

objPoints = []
jpgPoints = []

criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)

images = glob.glob(imagePath)
img_size = None
found = 0
pixel_distances = []

for fname in images:
    img = cv2.imread(fname)
    if img is None:
        print(f"❌ Gagal memuat gambar: {fname}")
        continue
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret, corners = cv2.findChessboardCorners(gray, patternSize, None)
    
    if ret:
        objPoints.append(objp)
        img_size = gray.shape[::-1]

        corners2 = cv2.cornerSubPix(gray, corners, (11,11), (-1,-1), criteria)
        jpgPoints.append(corners2)

        # Ambil jarak antar dua titik pertama (pixel)
        p1 = corners2[0][0]
        p2 = corners2[1][0]
        dist_px = np.linalg.norm(p2 - p1)
        pixel_distances.append(dist_px)

        img = cv2.drawChessboardCorners(img, patternSize, corners2, ret)
        cv2.imshow("corners", img)
        cv2.waitKey(300)

        found += 1

cv2.destroyAllWindows()
print(f"Jumlah Gambar Valid: {found}")

if found > 0:
    print("⏳ Sedang memproses Kalibrasi Kamera...")
    ret, mtrx, dist, rvecs, tvecs = cv2.calibrateCamera(objPoints, jpgPoints, img_size, None, None)

    # Hitung PIXEL_PER_CM rata-rata dari semua gambar
    PIXEL_PER_CM = np.mean(pixel_distances) / squareSizeCm
    print(f"PIXEL_PER_CM = {PIXEL_PER_CM:.3f}")

    data = {
        "squareSize": squareSizeCm,
        "patternSize": list(patternSize),
        "CameraMatrix": mtrx.tolist(),
        "dist_coeff": dist.tolist(),
        "PIXEL_PER_CM": float(PIXEL_PER_CM)  # simpan sekaligus di YAML
    }

    with open("Calibration_Matrix_CM.yaml", "w") as f:
        yaml.dump(data, f)

    print("Selesai. File YAML sudah diperbarui dengan PIXEL_PER_CM")
