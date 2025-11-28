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
import threading
import queue
import zmq  # ZMQ for receiving Android IP

# -------------------------
# CONFIG (sesuaikan jika perlu)
# -------------------------
model_path = r'best.pt'
yml_File = r'Calibration_Matrix copy.yaml'

SERIAL_PORT = "COM3"
BAUDRATE = 115200
FPS = 30

# UDP Video Stream Config
BROADCAST_IP = "255.255.255.255"  # Fallback jika IP Android belum diterima
UDP_VIDEO_PORT = 6000

# ZMQ Config (untuk terima command dari Android, termasuk IP address)
ZMQ_COMMAND_PORT = 6000  # HARUS SAMA dengan Android app!

# Android IP (akan di-update dari ZMQ)
android_ip = None  # None = belum terima, akan fallback ke broadcast
android_ip_lock = threading.Lock()  # Thread-safe update

# Kamera request (hint)
REQ_W, REQ_H = 360, 400   

YOLO_W, YOLO_H = 480, 640  

# JPEG quality untuk broadcast
JPEG_QUALITY = 50          # preview / local quality (high quality for local preview)
JPEG_QUALITY_SEND = 30   # network stream quality (balance: kualitas vs bandwidth)

# worker/send tuning
SEND_EVERY_N_FRAMES = 2        # how often to enqueue a frame for sending (1 = every frame)
SENDER_QUEUE_MAX = 2           # small queue for frames to send (drop when full)
YOLO_EVERY_N_FRAMES = 2        # run YOLO every N frames (main thread enqueues)
YOLO_CONF_THRESHOLD = 0.35
SENDER_THREAD_JOIN_TIMEOUT = 1.0
SHOW_PREVIEW = True            # set False on device to reduce overhead
SHOW_EVERY_N_FRAMES = 2        # preview refresh throttle

# ===== METRICS/LOGGING =====
FPS_LOG_INTERVAL = 5.0  # log stats every 5 seconds

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

# UDP SOCKET (untuk kirim video)
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # Tetap enable broadcast untuk fallback
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
sock.settimeout(1.0)

# ZMQ SOCKET (untuk terima command dari Android)
zmq_context = zmq.Context()
zmq_socket = zmq_context.socket(zmq.PULL)  # PULL socket untuk terima dari Android
zmq_socket.bind(f"tcp://*:{ZMQ_COMMAND_PORT}")
print(f"[ZMQ] Listening for commands on port {ZMQ_COMMAND_PORT}")

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
# ZMQ LISTENER (untuk terima IP dari Android)
# -------------------------
def zmq_listener():
    """Thread untuk menerima command dari Android (termasuk IP address)"""
    global android_ip
    print("[ZMQ] Listener thread started")
    
    while True:
        try:
            # Poll dengan timeout (non-blocking)
            if zmq_socket.poll(100):  # 100ms timeout
                message = zmq_socket.recv()
                msg = message.decode('utf-8').strip()
                
                # Parse CLIENT_IP command (dari Android saat connect)
                if msg.startswith("CLIENT_IP:"):
                    ip = msg.split(":", 1)[1]
                    with android_ip_lock:
                        old_ip = android_ip
                        android_ip = ip
                    
                    if old_ip != ip:
                        print(f"\n{'='*60}")
                        print(f"[ZMQ] ✅ Client connected from IP: {android_ip}")
                        print(f"[ZMQ] 🎥 Switching to UNICAST mode (target: {android_ip})")
                        print(f"{'='*60}\n")
                
                # Handle other commands (optional, bisa ditambahkan nanti)
                elif msg.startswith("MODE:"):
                    mode = msg.split(":", 1)[1]
                    if DEBUG:
                        print(f"[ZMQ] Mode changed to: {mode}")
                        
                elif msg.startswith("ROTATE:"):
                    rotate_val = msg.split(":", 1)[1]
                    if DEBUG:
                        print(f"[ZMQ] Rotate command: {rotate_val}")
                
                # Ignore joystick, slider, dll (sudah di-handle di ReceivedFix.py)
                    
        except zmq.Again:
            # No message available, continue
            time.sleep(0.05)
        except Exception as e:
            if DEBUG:
                print(f"[ZMQ] Listener error: {e}")
            time.sleep(0.1)

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
    
    # Start ZMQ listener thread
    zmq_thread = threading.Thread(target=zmq_listener, daemon=True)
    zmq_thread.start()
    print("[ZMQ] Listener thread started for receiving Android IP")

    # ---- workers setup ----
    # YOLO worker: process only latest small frame (queue size=1)
    yolo_in_q = queue.Queue(maxsize=1)
    worker_stop = threading.Event()
    cached_results = None
    cached_boxes = None

    def yolo_worker():
        nonlocal cached_results, cached_boxes
        while not worker_stop.is_set():
            try:
                small = yolo_in_q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                res = model(small, device=DEVICE, conf=YOLO_CONF_THRESHOLD, verbose=False)
                cached_results = res
                cached_boxes = res[0].boxes if res and len(res) > 0 else None
            except Exception as e:
                if DEBUG:
                    print("[WARN] YOLO worker error:", e)
            finally:
                try:
                    yolo_in_q.task_done()
                except Exception:
                    pass

    yw_thread = threading.Thread(target=yolo_worker, daemon=True)
    yw_thread.start()

    # Sender worker: encode & send off main thread
    sender_q = queue.Queue(maxsize=SENDER_QUEUE_MAX)
    sender_stop = threading.Event()
    sent_counter = 0
    dropped_send_counter = 0

    def sender_worker():
        nonlocal sent_counter, dropped_send_counter
        while not sender_stop.is_set():
            try:
                frame_to_send = sender_q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                ok, buf = cv2.imencode('.jpg', frame_to_send, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY_SEND])
                if not ok:
                    if DEBUG:
                        print("[WARN] encode failed in sender")
                    continue
                data = buf.tobytes()
                header = f"{len(data):08d}".encode('ascii')
                try:
                    # Tentukan target IP (unicast atau broadcast)
                    with android_ip_lock:
                        target_ip = android_ip if android_ip else BROADCAST_IP
                    
                    # track data size for diagnostics
                    nonlocal last_sent_size
                    last_sent_size = len(data)
                    
                    # Kirim ke target (unicast jika IP sudah diterima, broadcast jika belum)
                    sock.sendto(header + data, (target_ip, UDP_VIDEO_PORT))
                    sent_counter += 1
                except Exception as e:
                    # log every error (not just every 100) to catch issues
                    if DEBUG:
                        mode = "unicast" if android_ip else "broadcast"
                        print(f"[WARN] {mode} send failed:", e)
            except Exception as e:
                if DEBUG:
                    print("[WARN] sender_worker exception:", e)
            finally:
                try:
                    sender_q.task_done()
                except Exception:
                    pass

    s_thread = threading.Thread(target=sender_worker, daemon=True)
    s_thread.start()

    data_sent = False
    frame_counter = 0
    yolo_counter = 0
    fps_start_time = time.time()
    fps_frame_count = 0
    last_log_time = time.time()
    last_sent_size = 0
    
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

            # YOLO: enqueue small image to worker (non-blocking) every YOLO_EVERY_N_FRAMES
            yolo_counter += 1
            should_run_yolo = (yolo_counter % YOLO_EVERY_N_FRAMES == 0)
            small = None
            if should_run_yolo:
                small = cv2.resize(rot, (YOLO_W, YOLO_H), interpolation=cv2.INTER_LINEAR)
                try:
                    yolo_in_q.put_nowait(small)
                except queue.Full:
                    # worker busy: reuse cached results for this frame
                    if DEBUG:
                        pass

            # results will be read from cached_results / cached_boxes (updated by worker)
            results = cached_results

            # We will draw on a copy of the original rot to keep quality (no blur)
            annotated = rot.copy()

            # scale factors to map small -> rot
            sx = rot_w / YOLO_W
            sy = rot_h / YOLO_H

            # detection boxes from results (coordinates in small image space)
            # Guard against cached_results being None or empty
            boxes = None
            if results:
                try:
                    if len(results) > 0 and hasattr(results[0], "boxes"):
                        boxes = results[0].boxes
                except Exception as e:
                    if DEBUG:
                        print("[WARN] reading cached_results failed:", e)

            # fallback to last known boxes from worker (if any)
            if boxes is None and cached_boxes is not None:
                boxes = cached_boxes

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
                    if lab == "Fake":   # keep your logic
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

            # Send frame: enqueue a smaller display frame to sender worker (non-blocking)
            frame_counter += 1
            should_send = (frame_counter % SEND_EVERY_N_FRAMES == 0)
            if should_send:
                display_frame = cv2.resize(annotated, (int(rot_w*0.5), int(rot_h*0.5)), interpolation=cv2.INTER_LINEAR)
                try:
                    sender_q.put_nowait(display_frame)
                except queue.Full:
                    dropped_send_counter += 1
                    if DEBUG and dropped_send_counter % 50 == 0:
                        print(f"[INFO] sender_q full, dropped frames: {dropped_send_counter}")
            # ===== METRICS LOGGING =====
            fps_frame_count += 1
            now = time.time()
            if now - last_log_time >= FPS_LOG_INTERVAL:
                elapsed = now - last_log_time
                current_fps = fps_frame_count / elapsed
                sender_q_size = sender_q.qsize()
                yolo_q_size = yolo_in_q.qsize()
                
                # Get current target mode
                with android_ip_lock:
                    target_mode = f"UNICAST ({android_ip})" if android_ip else "BROADCAST"
                
                print(f"[METRICS] "
                      f"FPS={current_fps:.1f} | "
                      f"sent={sent_counter} | "
                      f"dropped={dropped_send_counter} | "
                      f"sender_q={sender_q_size} | "
                      f"yolo_q={yolo_q_size} | "
                      f"last_data_size={last_sent_size} bytes | "
                      f"mode={target_mode}")
                
                fps_frame_count = 0
                last_log_time = now
                
                # warn if queue is filling up (sign of bottleneck)
                if sender_q_size == SENDER_QUEUE_MAX:
                    print("[WARN] sender_q at MAX capacity (bottleneck detected)")
                if yolo_q_size == yolo_in_q.maxsize:
                    print("[WARN] yolo_q at MAX capacity")
             # preview for debug (high quality) - throttle to reduce UI overhead
            if DEBUG and SHOW_PREVIEW and (frame_counter % SHOW_EVERY_N_FRAMES == 0):
                 cv2.imshow("Annotated (high quality)", annotated)
                 if cv2.waitKey(1) & 0xFF == ord('q'):
                     break

    except KeyboardInterrupt:
        print("[INFO] Terminated by user")
    except Exception as e:
        print("[ERROR] exception:", e)
        traceback.print_exc()
    finally:
        # stop workers and join cleanly
        worker_stop.set()
        sender_stop.set()
        try:
            yw_thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            s_thread.join(timeout=SENDER_THREAD_JOIN_TIMEOUT)
        except Exception:
            pass
        # best-effort drain sender queue
        try:
            while not sender_q.empty():
                time.sleep(0.01)
        except Exception:
            pass
        Camera.release()
        sock.close()
        zmq_socket.close()
        zmq_context.term()
        if ser and hasattr(ser, "is_open") and ser.is_open:
            ser.close()
        cv2.destroyAllWindows()
        if DEBUG:
            print(f"[INFO] sent={sent_counter}, dropped_send={dropped_send_counter}")
            with android_ip_lock:
                if android_ip:
                    print(f"[INFO] Final target: UNICAST to {android_ip}")
                else:
                    print(f"[INFO] Final target: BROADCAST (no Android IP received)")

if __name__ == "__main__":
    UndistortFrame()
