import cv2
import numpy as np
import yaml
import os

def load_calibration_data(yaml_file):
    with open(yaml_file, 'r') as f:
        data = yaml.safe_load(f)
    

    mtx = np.array(data['CameraMatrix'])
    dist = np.array(data['dist_coeff'])
    # OpenCV memerlukan dist_coeff dalam bentuk (1, N)
    if dist.ndim == 2 and dist.shape[0] == 5:
        dist = dist.T 

    return mtx, dist

def undistort_image(image_path, mtx, dist):
    # Baca gambar
    img = cv2.imread(image_path)
    
    if img is None:
        print(f"❌ Error: Tidak dapat memuat gambar dari {image_path}")
        return

    h, w = img.shape[:2]

    # Hitung matriks kamera baru (new camera matrix) dan ROI
    # alpha=1.0 akan menjaga semua piksel dari gambar asli, bahkan jika itu berarti 
    # memiliki piksel hitam di sudut-sudut gambar. alpha=0.0 akan memotong gambar 
    # hanya menyisakan area yang valid.
    new_mtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))

    # Buat peta transformasi (ini lebih cepat daripada cv2.undistort langsung)
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (w, h), 5)
    
    # Terapkan transformasi (remapping)
    dst = cv2.remap(img, mapx, mapy, cv2.INTER_LINEAR)

    # Memotong (Crop) area hitam yang mungkin muncul karena alpha=1.0
    x, y, w, h = roi
    dst = dst[y:y+h, x:x+w]

    return dst

# --- 3. Eksekusi ---
if __name__ == '__main__':
    # Ganti path ini sesuai lokasi file YAML Anda
    calibration_file = r'D:\Azqya Old Code 2\PY and NumPy\30 Day Plylist\Calibrate Foto\calibration_Matrix.yaml' 
    
    target_image_path = r'D:\Azqya Old Code 2\PY and NumPy\30 Day Plylist\Calibrate Foto\Data Foto Papan Catur\Azqya3.jpg' 

    try:
        mtx, dist = load_calibration_data(calibration_file)
        
        print(f"✅ Parameter kalibrasi dimuat.")
        
        undistorted_img = undistort_image(target_image_path, mtx, dist)
        
        if undistorted_img is not None:
            cv2.imshow("Original Image", cv2.imread(target_image_path))
            cv2.imshow("Undistorted Image", undistorted_img)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
            
            cv2.imwrite("undistorted_result.jpg", undistorted_img)
            print("✅ Gambar dikoreksi dan disimpan sebagai 'undistorted_result.jpg'.")

    except FileNotFoundError:
        print(f"❌ Error: File {calibration_file} tidak ditemukan. Pastikan ia berada di direktori yang sama.")
    except Exception as e:
        print(f"❌ Terjadi kesalahan: {e}")