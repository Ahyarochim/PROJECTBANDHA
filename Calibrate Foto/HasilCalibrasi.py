import cv2
import numpy as np
import yaml
import os

# Nama file kalibrasi
CALIBRATION_FILE = 'calibration_Matrix.yaml' 
# ID kamera (0 biasanya adalah webcam default)
CAMERA_ID = 0 

def load_calibration_data(yaml_file):
    """Memuat matriks kamera (mtx) dan koefisien distorsi (dist) dari file YAML."""
    try:
        with open(yaml_file, 'r') as f:
            data = yaml.safe_load(f)
        
        mtx = np.array(data['CameraMatrix'])
        dist = np.array(data['dist_coeff'])
        
        # Mengubah bentuk dist_coeff agar sesuai dengan format OpenCV (1, N)
        if dist.ndim == 2 and dist.shape[0] == 5:
            dist = dist.T 
            
        print("✅ Parameter kalibrasi dimuat.")
        return mtx, dist
        
    except FileNotFoundError:
        print(f"❌ ERROR: File '{yaml_file}' tidak ditemukan. Pastikan file ada.")
        return None, None
    except Exception as e:
        print(f"❌ ERROR saat memuat data YAML: {e}")
        return None, None

def undistort_live_stream():
    mtx, dist = load_calibration_data(CALIBRATION_FILE)

    if mtx is None or dist is None:
        return

    # Inisialisasi kamera
    cap = cv2.VideoCapture(CAMERA_ID)
    if not cap.isOpened():
        print(f"❌ ERROR: Tidak dapat membuka kamera dengan ID {CAMERA_ID}.")
        return

    # Dapatkan ukuran frame (perlu untuk perhitungan getOptimalNewCameraMatrix)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Hitung matriks kamera baru dan peta transformasi di awal (efisien!)
    # alpha=1.0 menjaga semua piksel. alpha=0.0 akan memotong tepi hitam.
    new_mtx, roi = cv2.getOptimalNewCameraMatrix(mtx, dist, (w, h), 1, (w, h))
    mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (w, h), 5)
    
    print(f"▶️ Mulai streaming dari kamera ({w}x{h}). Tekan 'q' untuk keluar.")
    
    while True:
        # Baca frame dari kamera
        ret, frame = cap.read()
        
        if not ret:
            print("❌ Gagal menerima frame dari kamera. Keluar...")
            break

        # --- Terapkan Undistortion ke Frame ---
        # 1. Terapkan pemetaan transformasi pada frame
        undistorted_frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)

        # 2. Opsional: Potong area hitam jika ada (berdasarkan ROI)
        # x, y, w_roi, h_roi = roi
        # undistorted_frame = undistorted_frame[y:y+h_roi, x:x+w_roi]
        
        # Tampilkan frame asli dan yang sudah dikoreksi (undistorted)
        cv2.imshow('Original Frame (Distorted)', frame)
        cv2.imshow('Undistorted Frame (Corrected)', undistorted_frame)

        # Keluar jika tombol 'q' ditekan
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Bersihkan
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    undistort_live_stream()