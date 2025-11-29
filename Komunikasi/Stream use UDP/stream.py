import cv2
import socket
from ultralytics import YOLO
import numpy as np
import yaml
from collections import deque
import time
import sys
import traceback
import threading
import queue
import zmq
import msgpack

model_path = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Komunikasi\Stream use UDP\best.pt'
yml_File = r'D:\Azqya Old Code 2\BANDAYUDHA\PROJECTBANDHA\Komunikasi\Stream use UDP\Calibration_Matrix copy.yaml'

PORT = 6000
REQ_W, REQ_H = 360, 400
YOLO_W, YOLO_H = 480, 640
JPEG_QUALITY_SEND = 50

SEND_EVERY_N_FRAMES = 2
SENDER_QUEUE_MAX = 2
YOLO_EVERY_N_FRAMES = 2
YOLO_CONF_THRESHOLD = 0.35
SENDER_THREAD_JOIN_TIMEOUT = 1.0
SHOW_PREVIEW = True
SHOW_EVERY_N_FRAMES = 2
FPS_LOG_INTERVAL = 5.0

margin = 100
bufferConf = deque(maxlen=5)
CONF_THRESHOLD = 0.6
BRIGHTNESS_FACTOR = 1.5

DEBUG = True
USE_UNDISTORT = False

android_ip = None
android_ip_lock = threading.Lock()

model = YOLO(model_path)

try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except Exception:
    DEVICE = "cpu"

print(f"[INFO] Using device: {DEVICE}")

# UDP Socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
sock.settimeout(1.0)

# ZMQ Context
zmq_context = zmq.Context()
zmq_socket = zmq_context.socket(zmq.PULL)
zmq_socket.bind(f"tcp://*:{PORT}")
print(f"[ZMQ] Listening for commands on port {PORT}")

# Camera
Camera = cv2.VideoCapture(0)
Camera.set(cv2.CAP_PROP_FRAME_WIDTH, REQ_W)
Camera.set(cv2.CAP_PROP_FRAME_HEIGHT, REQ_H)
Camera.set(cv2.CAP_PROP_FPS, 30)
Camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not Camera.isOpened():
    print("Kamera tidak bisa dibuka!")
    sys.exit(1)

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

def draw_box_and_label(img, xy1, xy2, label_text=None, conf=None, color=(255, 0, 0), thickness=2):
    x1, y1 = int(xy1[0]), int(xy1[1])
    x2, y2 = int(xy2[0]), int(xy2[1])
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    if label_text:
        txt = f"{label_text}" + (f" {conf:.2f}" if conf is not None else "")
        (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 6, y1), color, -1)
        cv2.putText(img, txt, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

def zmq_listener():
    global android_ip
    print("[ZMQ] Listener thread started")
    
    while True:
        try:
            if zmq_socket.poll(100):
                message = zmq_socket.recv()
                msg = message.decode('utf-8').strip()
                
                if msg.startswith("CLIENT_IP:"):
                    ip = msg.split(":", 1)[1]
                    with android_ip_lock:
                        old_ip = android_ip
                        android_ip = ip
                    
                    if old_ip != ip:
                        print(f"\n{'='*60}")
                        print(f"[ZMQ] ✅ Client connected: {android_ip}")
                        print(f"[ZMQ] 🎥 Switching to UNICAST mode")
                        print(f"{'='*60}\n")
                        
        except zmq.Again:
            time.sleep(0.05)
        except Exception as e:
            if DEBUG:
                print(f"[ZMQ] Listener error: {e}")
            time.sleep(0.1)

def main():
    global USE_UNDISTORT, android_ip
    
    mtx, dist, pxlPercm = loadCalibration(yml_File)

    mapx = mapy = None
    if USE_UNDISTORT and mtx is not None and dist is not None:
        cam_w = int(Camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        cam_h = int(Camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        new_mtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (cam_w, cam_h), 1, (cam_w, cam_h))
        mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (cam_w, cam_h), cv2.CV_32FC1)
        print("[INFO] Undistort maps ready")
    else:
        USE_UNDISTORT = False
    
    # ZMQ Listener Thread
    zmq_thread = threading.Thread(target=zmq_listener, daemon=True)
    zmq_thread.start()

    # YOLO Worker
    yolo_in_q = queue.Queue(maxsize=1)
    worker_stop = threading.Event()
    cached_boxes = None

    def yolo_worker():
        nonlocal cached_boxes
        while not worker_stop.is_set():
            try:
                small = yolo_in_q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                res = model(small, device=DEVICE, conf=YOLO_CONF_THRESHOLD, verbose=False)
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

    # Sender Worker (UDP frames to Android)
    sender_q = queue.Queue(maxsize=SENDER_QUEUE_MAX)
    sender_stop = threading.Event()
    sent_counter = 0
    dropped_send_counter = 0
    last_sent_size = 0

    def sender_worker():
        nonlocal sent_counter, dropped_send_counter, last_sent_size
        while not sender_stop.is_set():
            try:
                frame_to_send = sender_q.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                ok, buf = cv2.imencode('.jpg', frame_to_send, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY_SEND])
                if not ok:
                    continue
                data = buf.tobytes()
                header = f"{len(data):08d}".encode('ascii')
                try:
                    with android_ip_lock:
                        target_ip = android_ip if android_ip else "255.255.255.255"
                    last_sent_size = len(data)
                    sock.sendto(header + data, (target_ip, PORT))
                    sent_counter += 1
                except Exception as e:
                    if DEBUG:
                        mode = "unicast" if android_ip else "broadcast"
                        print(f"[WARN] {mode} send failed: {e}")
            except Exception as e:
                if DEBUG:
                    print("[WARN] sender_worker error:", e)
            finally:
                try:
                    sender_q.task_done()
                except Exception:
                    pass

    s_thread = threading.Thread(target=sender_worker, daemon=True)
    s_thread.start()

    # Detection ZMQ Worker (Send detection data to Server)
    detection_zmq_q = queue.Queue(maxsize=1)

    def detection_zmq_worker():
        zmq_sender = zmq_context.socket(zmq.PUSH)
        try:
            zmq_sender.connect("tcp://localhost:5555")
            if DEBUG:
                print("[ZMQ-PUSH] Detection sender ready on port 5555 (sending to Server)")
        except Exception as e:
            if DEBUG:
                print(f"[WARN] Detection ZMQ connection failed: {e}")
            return
    
        while not sender_stop.is_set():
            try:
                detection = detection_zmq_q.get(timeout=0.2)
                if detection is not None:
                    try:
                        packed = msgpack.packb(detection, use_bin_type=True)
                        zmq_sender.send(packed, flags=zmq.NOBLOCK)
                    except zmq.Again:
                        pass
                    except Exception as e:
                        if DEBUG:
                            print(f"[WARN] ZMQ detection send error: {e}")
            except queue.Empty:
                pass
            except Exception as e:
                if DEBUG:
                    print(f"[WARN] Detection worker error: {e}")

    dz_thread = threading.Thread(target=detection_zmq_worker, daemon=True)
    dz_thread.start()

    # Main Loop
    frame_counter = 0
    yolo_counter = 0
    fps_frame_count = 0
    last_log_time = time.time()

    try:
        while True:
            ret, frame = Camera.read()
            if not ret:
                continue

            if USE_UNDISTORT and mapx is not None:
                frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)

            rot = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            rot = cv2.convertScaleAbs(rot, alpha=BRIGHTNESS_FACTOR, beta=0)

            rot_h, rot_w = rot.shape[:2]

            # YOLO Processing
            yolo_counter += 1
            if yolo_counter % YOLO_EVERY_N_FRAMES == 0:
                small = cv2.resize(rot, (YOLO_W, YOLO_H), interpolation=cv2.INTER_LINEAR)
                try:
                    yolo_in_q.put_nowait(small)
                except queue.Full:
                    pass

            annotated = rot.copy()
            sx = rot_w / YOLO_W
            sy = rot_h / YOLO_H
            
            boxes = cached_boxes

            detected = False
            in_center = False
            dist_x_cm = 0.0
            dist_y_cm = 0.0
            obj_cx = None
            obj_cy = None
            conf_val = 0.0
            stable_conf = None
            lab = "Unknown"

            center_x = rot_w // 2
            center_y = int(rot_h *0.65) 
            color = (0, 255, 0) if in_center else (0, 0, 255)

            if boxes is not None and len(boxes) > 0:
                # Filter HANYA KFS-Blue dan KFS-Red dengan confidence > 0.7
                filtered_boxes = [b for b in boxes if float(b.conf[0]) > 0.7]
                
                # Pisahkan berdasarkan label
                blue_boxes = []
                red_boxes = []
                
                for b in filtered_boxes:
                    cls = int(b.cls[0])
                    label = model.names[cls] if hasattr(model, "names") else str(cls)
                    
                    if label == "KFS-Blue":
                        blue_boxes.append(b)
                    elif label == "KFS-Red":
                        red_boxes.append(b)
                
                # SISTEM PRIORITAS: Blue > Red
                # 1. Jika ada Blue, ambil Blue dengan confidence tertinggi
                # 2. Jika tidak ada Blue, ambil Red dengan confidence tertinggi
                selected_target = None
                
                if len(blue_boxes) > 0:
                    # Ada Blue - ambil yang confidence tertinggi
                    selected_target = max(blue_boxes, key=lambda b: float(b.conf[0]))
                    lab = "KFS-Blue"
                elif len(red_boxes) > 0:
                    # Tidak ada Blue, ambil Red dengan confidence tertinggi
                    selected_target = max(red_boxes, key=lambda b: float(b.conf[0]))
                    lab = "KFS-Red"
                
                # Gambar SEMUA box yang terfilter (untuk visualisasi)
                for b in filtered_boxes:
                    x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
                    cls = int(b.cls[0])
                    conf = float(b.conf[0])
                    rx1, ry1 = x1 * sx, y1 * sy
                    rx2, ry2 = x2 * sx, y2 * sy
                    label = model.names[cls] if hasattr(model, "names") else str(cls)
                    draw_box_and_label(annotated, (rx1, ry1), (rx2, ry2), label_text=label, conf=conf, color=(225, 0, 0), thickness=3)
                
                # Proses HANYA selected target (priority target)
                if selected_target is not None:
                    x1, y1, x2, y2 = [float(v) for v in selected_target.xyxy[0]]
                    
                    # Hitung ukuran box untuk color indicator
                    scaled_x1 = x1 * sx
                    scaled_y1 = y1 * sy
                    scaled_x2 = x2 * sx
                    scaled_y2 = y2 * sy
                    
                    box_width = scaled_x2 - scaled_x1
                    box_height = scaled_y2 - scaled_y1
                    
                    indicator_size = margin * 2
                    
                    width_diff = abs(box_width - indicator_size) / indicator_size * 100
                    height_diff = abs(box_height - indicator_size) / indicator_size * 100
                    avg_diff = (width_diff + height_diff) / 2
                    
                    # Tentukan warna crosshair berdasarkan ukuran
                    if avg_diff < 35:
                        color = (0, 255, 0)      # Hijau - ukuran pas
                    elif avg_diff < 50:
                        color = (0, 255, 255)    # Kuning - mendekati
                    else:
                        color = (0, 0, 255)      # Merah - terlalu jauh
                    
                    # Hitung center point dari selected target
                    cx_small = (x1 + x2) / 2.0
                    cy_small = (y1 + y2) / 2.0
                    
                    obj_cx = int(cx_small * sx)
                    obj_cy = int(cy_small * sy)
                    conf_val = float(selected_target.conf[0])
                    bufferConf.append(conf_val)
                    
                    if len(bufferConf) == bufferConf.maxlen:
                        stable_conf = sum(bufferConf) / len(bufferConf)
                    
                    # Validasi stable confidence
                    if stable_conf is not None and stable_conf > CONF_THRESHOLD:
                        detected = True
                        offset_x = obj_cx - center_x
                        offset_y = obj_cy - center_y
                        
                        dist_x_cm = offset_x / pxlPercm
                        dist_y_cm = offset_y / pxlPercm
                        in_center = abs(offset_x) <= margin and abs(offset_y) <= margin
                
                # Kirim detection data (untuk monitoring/debugging)
                detection_data = {
                    "timestamp": time.time(),
                    "detected": detected,
                    "in_center": in_center,
                    "class_name": lab if detected else "Unknown",
                    "confidence_now": conf_val,
                    "stable_confidence": stable_conf if stable_conf is not None else 0.0,
                    "center": {"x": obj_cx if obj_cx else 0, "y": obj_cy if obj_cy else 0},
                    "distance": {
                        "x_cm": dist_x_cm,
                        "y_cm": dist_y_cm,
                        "offset_x": int(offset_x) if 'offset_x' in locals() else 0,
                        "offset_y": int(offset_y) if 'offset_y' in locals() else 0
                    },
                    "frame_info": {"width": rot_w, "height": rot_h, "margin": margin},
                    "priority_info": {
                        "blue_detected": len(blue_boxes),
                        "red_detected": len(red_boxes),
                        "selected_class": lab if selected_target else "None"
                    }
                }
                try:
                    detection_zmq_q.put_nowait(detection_data)
                except queue.Full:
                    pass
            else:
                bufferConf.clear()

            cv2.line(annotated, (center_x, 0), (center_x, rot_h), color, 2)
            cv2.line(annotated, (0, center_y), (rot_w, center_y), color, 2)
            cv2.rectangle(annotated, (center_x - margin, center_y - margin), (center_x + margin, center_y + margin), color, 2)

            if detected and obj_cx is not None and (lab == "KFS-Blue" or lab == "KFS-Red"):
                cv2.circle(annotated, (int(obj_cx), int(obj_cy)), 6, (255, 255, 0), -1)

            txt = f"X:{dist_x_cm:.2f}cm | Y:{dist_y_cm:.2f}cm"
            cv2.putText(annotated, txt, (20, rot_h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3, cv2.LINE_AA)
            cv2.putText(annotated, txt, (20, rot_h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 255), 1, cv2.LINE_AA)

            # Send frame to Android
            frame_counter += 1
            should_send = (frame_counter % SEND_EVERY_N_FRAMES == 0)
            if should_send:
                display_frame = cv2.resize(annotated, (int(rot_w * 0.5), int(rot_h * 0.5)), interpolation=cv2.INTER_LINEAR)
                try:
                    sender_q.put_nowait(display_frame)
                except queue.Full:
                    dropped_send_counter += 1
                    if DEBUG and dropped_send_counter % 50 == 0:
                        print(f"[INFO] sender_q full, dropped: {dropped_send_counter}")

            # Metrics logging
            fps_frame_count += 1
            now = time.time()
            if now - last_log_time >= FPS_LOG_INTERVAL:
                elapsed = now - last_log_time
                current_fps = fps_frame_count / elapsed

                with android_ip_lock:
                    target_mode = f"UNICAST ({android_ip})" if android_ip else "BROADCAST"

                print(f"[METRICS] FPS={current_fps:.1f} | sent={sent_counter} | dropped={dropped_send_counter} | "
                      f"sender_q={sender_q.qsize()} | yolo_q={yolo_in_q.qsize()} | "
                      f"data_size={last_sent_size}B | mode={target_mode}")
                
                fps_frame_count = 0
                last_log_time = now

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
        try:
            dz_thread.join(timeout=1.0)
        except Exception:
            pass
        Camera.release()
        sock.close()
        zmq_socket.close()
        zmq_context.term()
        cv2.destroyAllWindows()
        if DEBUG:
            print(f"[INFO] Final stats - sent={sent_counter}, dropped={dropped_send_counter}")
            with android_ip_lock:
                if android_ip:
                    print(f"[INFO] Final target: UNICAST to {android_ip}")
                else:
                    print(f"[INFO] Final target: BROADCAST")

if __name__ == "__main__":
    main()