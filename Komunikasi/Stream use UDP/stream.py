# full_stream_yolo_center_fixed.py
import cv2
import socket
from ultralytics import YOLO
import numpy as np
import yaml
from collections import deque
import time
import serial
import sys
import traceback

# -------------------------
# CONFIG (sesuaikan jika perlu)
# -------------------------
model_path = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Komunikasi\Stream use UDP\best.pt'
yml_File = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Komunikasi\Stream use UDP\Calibration_Matrix copy.yaml'

SERIAL_PORT = "COM3"
BAUDRATE = 115200

BROADCAST_IP = "255.255.255.255"
Port = 6000

# Kamera request (hint)
REQ_W, REQ_H = 360, 400   # hint ke driver (landscape before rotate)
FPS = 20

# ukuran kecil yang dipakai YOLO (portrait orientation)
# gunakan ukuran cukup besar untuk kualitas, tetapi masih ringan
YOLO_W, YOLO_H = 480, 640  # small image for speed (portrait: width x height)

# JPEG quality untuk broadcast
JPEG_QUALITY = 90

# center / detection params
margin = 100
bufferConf = deque(maxlen=5)
CONF_THRESHOLD = 0.6

DEBUG = True
USE_UNDISTORT = False   # toggle undistort (False = lebih ringan)

# -------------------------
# INIT
# -------------------------
# load model
model = YOLO(model_path)

# choose device: cuda if available, else cpu
try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except Exception:
    DEVICE = "cpu"

print(f"[INFO] Using device: {DEVICE}")

# SOCKET
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
sock.settimeout(1.0)

# CAMERA
Camera = cv2.VideoCapture(0)
Camera.set(cv2.CAP_PROP_FRAME_WIDTH, REQ_W)
Camera.set(cv2.CAP_PROP_FRAME_HEIGHT, REQ_H)
Camera.set(cv2.CAP_PROP_FPS, FPS)
Camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not Camera.isOpened():
    print("Kamera tidak bisa dibuka!")
    sys.exit(1)

# -------------------------
# HELPERS
# -------------------------
def loadCalibration(path):
    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        mtx = np.array(data["CameraMatrix"], dtype=np.float64)
        dist = np.array(data["dist_coeff"], dtype=np.float64).reshape(1, -1)
        pxlPercm = float(data.get("PIXEL_PER_CM", 10.0))
        return mtx, dist, pxlPercm
    except Exception as e:
        print("[WARN] Load calibration failed:", e)
        return None, None, 10.0

def init_serial():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
        time.sleep(2)
        print("[OK] STM32 Connected")
        return ser
    except Exception as e:
        print("[WARN] Serial gagal dibuka:", e)
        return None

# -------------------------
# DRAW helper (manual drawing to keep quality)
# -------------------------
def draw_box_and_label(img, xy1, xy2, label_text=None, conf=None, color=(255,0,0), thickness=2):
    x1,y1 = int(xy1[0]), int(xy1[1])
    x2,y2 = int(xy2[0]), int(xy2[1])
    cv2.rectangle(img, (x1,y1), (x2,y2), color, thickness)
    if label_text:
        txt = f"{label_text}" + (f" {conf:.2f}" if conf is not None else "")
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        # background rectangle
        cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 6, y1), color, -1)
        cv2.putText(img, txt, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1, cv2.LINE_AA)

# -------------------------
# MAIN
# -------------------------
def UndistortFrame():
    global USE_UNDISTORT, mapx, mapy

    ser = init_serial()
    mtx, dist, pxlPercm = loadCalibration(yml_File)

    # prepare undistort maps if enabled
    mapx = mapy = None
    if USE_UNDISTORT and mtx is not None and dist is not None:
        cam_w = int(Camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        cam_h = int(Camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        new_mtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (cam_w, cam_h), 1, (cam_w, cam_h))
        mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (cam_w, cam_h), cv2.CV_32FC1)
        print("[INFO] Undistort maps ready")
    else:
        if USE_UNDISTORT:
            print("[WARN] Undistort requested but calibration missing. Skipping undistort.")
        USE_UNDISTORT = False

    data_sent = False

    try:
        while True:
            ret, frame = Camera.read()
            if not ret:
                continue

            # undistort if enabled
            if USE_UNDISTORT and mapx is not None:
                frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)

            # rotate to portrait (so UI expects portrait)
            rot = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            # original rot size (keep for annotation quality)
            rot_h, rot_w = rot.shape[:2]

            # prepare small image for YOLO (keep portrait orientation)
            # maintain aspect: we resize to YOLO_W x YOLO_H (portrait)
            small = cv2.resize(rot, (YOLO_W, YOLO_H), interpolation=cv2.INTER_LINEAR)

            # run YOLO on small image (device selected)
            results = model(small, device=DEVICE)

            # We will draw on a copy of the original rot to keep quality (no blur)
            annotated = rot.copy()

            # scale factors to map small -> rot
            sx = rot_w / YOLO_W
            sy = rot_h / YOLO_H

            # detection boxes from results (coordinates in small image space)
            boxes = results[0].boxes
            if boxes is not None and len(boxes) > 0:
                # iterate all boxes (or take first) — we'll draw all
                for b in boxes:
                    x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
                    cls = int(b.cls[0])
                    conf = float(b.conf[0])

                    # map back to rot coords
                    rx1 = x1 * sx
                    ry1 = y1 * sy
                    rx2 = x2 * sx
                    ry2 = y2 * sy

                    label = model.names[cls] if hasattr(model, "names") else str(cls)

                    # draw box and label on high-res annotated
                    draw_box_and_label(annotated, (rx1, ry1), (rx2, ry2), label_text=label, conf=conf, color=(0,165,255), thickness=2)

                    # compute center of first/highest conf object for logic (you can choose first only)
                # choose first box as primary
                primary = boxes[0]
                x1, y1, x2, y2 = [float(v) for v in primary.xyxy[0]]
                cx_small = (x1 + x2) / 2.0
                cy_small = (y1 + y2) / 2.0
                # map to rot coords
                obj_cx = int(cx_small * sx)
                obj_cy = int(cy_small * sy)
                # compute stable confidence buffer
                conf_val = float(primary.conf[0])
                bufferConf.append(conf_val)

                stable_conf = None
                if len(bufferConf) == bufferConf.maxlen:
                    stable_conf = sum(bufferConf) / len(bufferConf)

                # default values
                detected = False
                in_center = False
                dist_x_cm = 0.0
                dist_y_cm = 0.0

                if stable_conf is not None and stable_conf > CONF_THRESHOLD:
                    # choose label
                    lab = model.names[int(primary.cls[0])]
                    if lab == "Azqya":   # keep your logic
                        detected = True
                        # offset (pixels)
                        center_x = rot_w // 2
                        center_y = rot_h // 2
                        offset_x = obj_cx - center_x
                        offset_y = obj_cy - center_y
                        # convert to cm if you have pxlPercm
                        dist_x_cm = offset_x / pxlPercm
                        dist_y_cm = offset_y / pxlPercm
                        in_center = abs(offset_x) <= margin and abs(offset_y) <= margin

                        # send serial once when in center
                        if in_center and not data_sent and ser:
                            try:
                                msg = f"X:{dist_x_cm:.2f},Y:{dist_y_cm:.2f}\n"
                                ser.write(msg.encode())
                                data_sent = True
                            except Exception as e:
                                print("[WARN] serial send failed:", e)
                        elif not in_center:
                            data_sent = False
            else:
                # no boxes
                bufferConf.clear()
                obj_cx = None
                obj_cy = None
                detected = False
                in_center = False
                dist_x_cm = dist_y_cm = 0.0
                center_x = rot_w // 2
                center_y = rot_h // 2

            # draw crosshair & center box (on annotated high-res)
            center_x = rot_w // 2
            center_y = rot_h // 2
            color = (0,255,0) if (locals().get("in_center", False)) else (0,0,255)
            cv2.line(annotated, (center_x, 0), (center_x, rot_h), color, 2)
            cv2.line(annotated, (0, center_y), (rot_w, center_y), color, 2)
            cv2.rectangle(annotated, (center_x - margin, center_y - margin), (center_x + margin, center_y + margin), color, 2)

            # draw center dot and text
            if 'obj_cx' in locals() and obj_cx is not None:
                cv2.circle(annotated, (int(obj_cx), int(obj_cy)), 6, (255,255,0), -1)

            # write X Y text at bottom
            txt = f"X: {dist_x_cm:.2f} cm | Y: {dist_y_cm:.2f} cm"
            cv2.putText(annotated, txt, (20, rot_h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,0), 3, cv2.LINE_AA)
            cv2.putText(annotated, txt, (20, rot_h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255,255,255), 1, cv2.LINE_AA)

            # Encode & broadcast
            ok, buffer = cv2.imencode('.jpg', annotated, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                data = buffer.tobytes()
                header = f"{len(data):08d}".encode('ascii')
                try:
                    sock.sendto(header + data, (BROADCAST_IP, Port))
                except Exception as e:
                    # ignore network errors quietly
                    if DEBUG:
                        print("[WARN] broadcast failed:", e)

            # preview for debug (high quality)
            if DEBUG:
                cv2.imshow("Annotated (high quality)", annotated)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        print("[INFO] Terminated by user")
    except Exception as e:
        print("[ERROR] exception:", e)
        traceback.print_exc()
    finally:
        Camera.release()
        sock.close()
        if ser and hasattr(ser, "is_open") and ser.is_open:
            ser.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    UndistortFrame()
