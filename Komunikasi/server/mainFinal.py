"""
mainFinal.py - Integrated Robot Server
Combines ReceivedFix.py (ZMQ Control Server) and stream.py (Vision & Video Streaming)
"""

import zmq
import time
import serial
import threading
import struct
from enum import Enum
import cv2
import socket
from ultralytics import YOLO
import numpy as np
import yaml
from collections import deque
import sys
import traceback
import queue
import msgpack

# ========================
# CONFIGURATION
# ========================
class RobotMode(Enum):
    MANUAL = 1
    AUTONOMOUS = 2

# Serial Config
SERIAL_PORT = '/dev/ttyACM0'  # Sesuaikan: Linux: '/dev/ttyACM0', Windows: 'COM3'
BAUD_RATE = 115200

# ZMQ Config
ZMQ_PORT = 6000

# Vision Config
model_path = r'best.pt'
yml_File = r'Calibration_Matrix copy.yaml'

# Camera Config
REQ_W, REQ_H = 360, 400
YOLO_W, YOLO_H = 480, 640
JPEG_QUALITY_SEND = 50
FPS = 30

# Processing Config
SEND_EVERY_N_FRAMES = 2
SENDER_QUEUE_MAX = 2
YOLO_EVERY_N_FRAMES = 2
YOLO_CONF_THRESHOLD = 0.35
SHOW_PREVIEW = True
SHOW_EVERY_N_FRAMES = 2
FPS_LOG_INTERVAL = 5.0

# Detection Config
margin = 100
CONF_THRESHOLD = 0.6
BRIGHTNESS_FACTOR = 1.5

DEBUG = True
USE_UNDISTORT = False

# ========================
# INTEGRATED SERVER CLASS
# ========================
class IntegratedRobotServer:
    def __init__(self):
        """Integrated server: ZMQ control + Vision + Video streaming"""
        
        # ==== Serial STM32 ====
        self.ser = None
        self.serial_connected = False
        self.serial_port = SERIAL_PORT
        self.baud_rate = BAUD_RATE
        
        # ==== ZMQ Setup ====
        self.zmq_context = zmq.Context()
        
        # ZMQ PULL socket (terima dari Android)
        self.zmq_socket = self.zmq_context.socket(zmq.PULL)
        self.zmq_socket.bind(f"tcp://0.0.0.0:{ZMQ_PORT}")
        
        # ZMQ PUSH socket (kirim detection data)
        self.zmq_detection_socket = self.zmq_context.socket(zmq.PUSH)
        try:
            self.zmq_detection_socket.connect("tcp://localhost:5555")
        except:
            pass
        
        # ==== UDP Socket (video stream) ====
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
        self.udp_socket.settimeout(1.0)
        
        # ==== Robot State ====
        self.mode = RobotMode.MANUAL
        self.android_ip = None
        self.android_ip_lock = threading.Lock()
        
        # Command state
        self.last_command_type = None
        self.joystick_x = 0.0
        self.joystick_y = 0.0
        self.gripper1 = 0.0
        self.gripper2 = 0.0
        self.preset_num = 0
        self.gripper_state = "OFF"
        self.mode_value = "MANUAL"
        self.rotate_value = 0
        self.motor1_value = 0.0
        
        # ==== Vision / YOLO ====
        self.yolo_model = YOLO(model_path)
        try:
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        except:
            self.device = "cpu"
        
        # Camera
        self.camera = cv2.VideoCapture(0)
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, REQ_W)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, REQ_H)
        self.camera.set(cv2.CAP_PROP_FPS, FPS)
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not self.camera.isOpened():
            print("[ERROR] Kamera tidak bisa dibuka!")
            sys.exit(1)
        
        # Detection buffer
        self.buffer_conf = deque(maxlen=5)
        
        # Threading control
        self.running = False
        
        print(f"[INIT] Integrated Robot Server initialized")
        print(f"[INIT] ZMQ Port: {ZMQ_PORT}")
        print(f"[INIT] Serial: {SERIAL_PORT}")
        print(f"[INIT] YOLO Device: {self.device}")
    
    # ========================
    # SERIAL COMMUNICATION
    # ========================
    def connect_serial(self):
        """Connect to STM32 via Serial"""
        try:
            self.ser = serial.Serial(
                port=self.serial_port,
                baudrate=self.baud_rate,
                timeout=0.1,
                write_timeout=2,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            time.sleep(2)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            self.serial_connected = True
            print(f"[SERIAL] Connected to STM32 on {self.serial_port}")
            return True
        except serial.SerialException as e:
            print(f"[SERIAL] Error: {e}")
            self.serial_connected = False
            return False
    
    def disconnect_serial(self):
        """Disconnect from STM32"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.serial_connected = False
            print("[SERIAL] Disconnected")
    
    def send_to_stm(self):
        """Send data to STM32"""
        if not self.serial_connected or not self.ser:
            if DEBUG:
                print("[SERIAL] Not connected to STM32")
            return False
        
        try:
            # Format berdasarkan tipe command
            if self.last_command_type == 'joystick':
                data_str = f"JOY,{self.joystick_x:.2f},{self.joystick_y:.2f}\n"
            elif self.last_command_type == 'slider':
                data_str = f"SLD,{self.gripper1:.2f},{self.gripper2:.2f}\n"
            elif self.last_command_type == 'preset':
                data_str = f"PRE,{self.preset_num}\n"
            elif self.last_command_type == 'gripper_toggle':
                data_str = f"GRP,{self.gripper_state}\n"
            elif self.last_command_type == 'mode':
                data_str = f"MOD,{self.mode_value}\n"
            elif self.last_command_type == 'rotate':
                data_str = f"ROT,{self.rotate_value}\n"
            else:
                data_str = f"{self.motor1_value:.2f}\n"
            
            self.ser.write(data_str.encode())
            self.ser.flush()
            if DEBUG:
                print(f"[SERIAL] Sent: {repr(data_str.strip())}")
            return True
        except Exception as e:
            print(f"[SERIAL] Send error: {e}")
            return False
    
    # ========================
    # ZMQ MESSAGE HANDLING
    # ========================
    def parse_android_message(self, message):
        """Parse message from Android"""
        try:
            msg = message.decode('utf-8').strip()
            if DEBUG:
                print(f"[ZMQ] Received: {msg}")
            
            # CLIENT_IP handling
            if msg.startswith("CLIENT_IP:"):
                ip = msg.split(":", 1)[1]
                with self.android_ip_lock:
                    old_ip = self.android_ip
                    self.android_ip = ip
                
                if old_ip != ip:
                    print(f"\n{'='*60}")
                    print(f"[ZMQ] ✅ Client connected: {self.android_ip}")
                    print(f"[ZMQ] 🎥 Switching to UNICAST mode")
                    print(f"{'='*60}\n")
                return
            
            # Command parsing
            if msg.startswith("PRESET:"):
                self.last_command_type = 'preset'
                self.preset_num = int(msg.split(":")[1])
                print(f"[PRESET] Num: {self.preset_num}")
                self.send_to_stm()
            
            elif msg.startswith("GRIPPER:"):
                self.last_command_type = 'gripper_toggle'
                state = msg.split(":")[1]
                self.gripper_state = "ON" if state == "GRIP_ON" else "OFF"
                print(f"[GRIPPER] State: {self.gripper_state}")
                self.send_to_stm()
            
            elif msg.startswith("MODE:"):
                self.last_command_type = 'mode'
                self.mode_value = msg.split(":")[1]
                print(f"[MODE] Value: {self.mode_value}")
                self.send_to_stm()
            
            elif msg.startswith("SLIDER:"):
                self.last_command_type = 'slider'
                data_part = msg.split(":", 1)[1]
                parts = data_part.split(",")
                if len(parts) == 2:
                    self.gripper1 = float(parts[0])
                    self.gripper2 = float(parts[1])
                    print(f"[SLIDER] G1: {self.gripper1:.2f}, G2: {self.gripper2:.2f}")
                    self.send_to_stm()
            
            elif msg.startswith("ROTATE:"):
                self.last_command_type = 'rotate'
                self.rotate_value = int(msg.split(":")[1])
                print(f"[ROTATE] Value: {self.rotate_value}")
                self.send_to_stm()
            
            else:
                # Numeric data
                parts = msg.split(",")
                
                if len(parts) == 2:
                    # Joystick
                    self.last_command_type = 'joystick'
                    self.joystick_x = float(parts[0])
                    self.joystick_y = float(parts[1])
                    print(f"[JOYSTICK] X: {self.joystick_x:.2f}, Y: {self.joystick_y:.2f}")
                    self.send_to_stm()
                
                elif len(parts) == 1:
                    # Motor1 only
                    self.last_command_type = None
                    self.motor1_value = float(parts[0])
                    print(f"[MOTOR1] Value: {self.motor1_value:.2f}")
                    self.send_to_stm()
        
        except Exception as e:
            print(f"[PARSE] Error: {e}")
    
    def zmq_receive_loop(self):
        """ZMQ receive loop"""
        print("[ZMQ] Listening for messages...")
        
        while self.running:
            try:
                if self.zmq_socket.poll(timeout=100):
                    message = self.zmq_socket.recv()
                    self.parse_android_message(message)
            except zmq.Again:
                continue
            except Exception as e:
                if DEBUG:
                    print(f"[ZMQ] Error: {e}")
                time.sleep(0.1)
    
    # ========================
    # VISION PROCESSING
    # ========================
    def load_calibration(self, path):
        """Load camera calibration"""
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
            mtx = np.array(data["CameraMatrix"], dtype=np.float64)
            dist = np.array(data["dist_coeff"], dtype=np.float64).reshape(1, -1)
            pxlPercm = float(data.get("PIXEL_PER_CM", 10.0))
            return mtx, dist, pxlPercm
        except Exception as e:
            print(f"[WARN] Load calibration failed: {e}")
            return None, None, 10.0
    
    def draw_box_and_label(self, img, xy1, xy2, label_text=None, conf=None, color=(255, 0, 0), thickness=2):
        """Draw bounding box with label"""
        x1, y1 = int(xy1[0]), int(xy1[1])
        x2, y2 = int(xy2[0]), int(xy2[1])
        cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
        if label_text:
            txt = f"{label_text}" + (f" {conf:.2f}" if conf is not None else "")
            (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
            cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 6, y1), color, -1)
            cv2.putText(img, txt, (x1 + 3, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
    
    def vision_loop(self):
        """Main vision processing loop"""
        mtx, dist, pxlPercm = self.load_calibration(yml_File)
        
        # Undistort maps
        mapx = mapy = None
        if USE_UNDISTORT and mtx is not None:
            cam_w = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
            cam_h = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
            new_mtx, _ = cv2.getOptimalNewCameraMatrix(mtx, dist, (cam_w, cam_h), 1, (cam_w, cam_h))
            mapx, mapy = cv2.initUndistortRectifyMap(mtx, dist, None, new_mtx, (cam_w, cam_h), cv2.CV_32FC1)
            print("[INFO] Undistort maps ready")
        
        # YOLO worker
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
                    res = self.yolo_model(small, device=self.device, conf=YOLO_CONF_THRESHOLD, verbose=False)
                    cached_boxes = res[0].boxes if res and len(res) > 0 else None
                except Exception as e:
                    if DEBUG:
                        print(f"[WARN] YOLO error: {e}")
                finally:
                    try:
                        yolo_in_q.task_done()
                    except:
                        pass
        
        yw_thread = threading.Thread(target=yolo_worker, daemon=True)
        yw_thread.start()
        
        # Sender worker
        sender_q = queue.Queue(maxsize=SENDER_QUEUE_MAX)
        sender_stop = threading.Event()
        sent_counter = 0
        dropped_counter = 0
        last_sent_size = 0
        
        def sender_worker():
            nonlocal sent_counter, dropped_counter, last_sent_size
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
                    
                    with self.android_ip_lock:
                        target_ip = self.android_ip if self.android_ip else "255.255.255.255"
                    
                    last_sent_size = len(data)
                    self.udp_socket.sendto(header + data, (target_ip, ZMQ_PORT))
                    sent_counter += 1
                except Exception as e:
                    if DEBUG:
                        print(f"[WARN] Send error: {e}")
                finally:
                    try:
                        sender_q.task_done()
                    except:
                        pass
        
        s_thread = threading.Thread(target=sender_worker, daemon=True)
        s_thread.start()
        
        # Main vision loop
        frame_counter = 0
        yolo_counter = 0
        fps_frame_count = 0
        last_log_time = time.time()
        
        try:
            while self.running:
                ret, frame = self.camera.read()
                if not ret:
                    continue
                
                if USE_UNDISTORT and mapx is not None:
                    frame = cv2.remap(frame, mapx, mapy, cv2.INTER_LINEAR)
                
                rot = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                rot = cv2.convertScaleAbs(rot, alpha=BRIGHTNESS_FACTOR, beta=0)
                
                rot_h, rot_w = rot.shape[:2]
                
                # YOLO processing
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
                center_y = int(rot_h * 0.65)
                color = (0, 255, 0) if in_center else (0, 0, 255)
                
                if boxes is not None and len(boxes) > 0:
                    # Filter boxes
                    filtered_boxes = [b for b in boxes if float(b.conf[0]) > 0.7]
                    
                    blue_boxes = []
                    red_boxes = []
                    
                    for b in filtered_boxes:
                        cls = int(b.cls[0])
                        label = self.yolo_model.names[cls] if hasattr(self.yolo_model, "names") else str(cls)
                        
                        if label == "KFS-Blue":
                            blue_boxes.append(b)
                        elif label == "KFS-Red":
                            red_boxes.append(b)
                    
                    # Priority: Blue > Red
                    selected_target = None
                    
                    if len(blue_boxes) > 0:
                        selected_target = max(blue_boxes, key=lambda b: float(b.conf[0]))
                        lab = "KFS-Blue"
                    elif len(red_boxes) > 0:
                        selected_target = max(red_boxes, key=lambda b: float(b.conf[0]))
                        lab = "KFS-Red"
                    
                    # Draw all boxes
                    for b in filtered_boxes:
                        x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
                        cls = int(b.cls[0])
                        conf = float(b.conf[0])
                        rx1, ry1 = x1 * sx, y1 * sy
                        rx2, ry2 = x2 * sx, y2 * sy
                        label = self.yolo_model.names[cls] if hasattr(self.yolo_model, "names") else str(cls)
                        self.draw_box_and_label(annotated, (rx1, ry1), (rx2, ry2), label_text=label, conf=conf, color=(225, 0, 0), thickness=3)
                    
                    # Process selected target
                    if selected_target is not None:
                        x1, y1, x2, y2 = [float(v) for v in selected_target.xyxy[0]]
                        
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
                        
                        if avg_diff < 35:
                            color = (0, 255, 0)
                        elif avg_diff < 50:
                            color = (0, 255, 255)
                        else:
                            color = (0, 0, 255)
                        
                        cx_small = (x1 + x2) / 2.0
                        cy_small = (y1 + y2) / 2.0
                        
                        obj_cx = int(cx_small * sx)
                        obj_cy = int(cy_small * sy)
                        conf_val = float(selected_target.conf[0])
                        self.buffer_conf.append(conf_val)
                        
                        if len(self.buffer_conf) == self.buffer_conf.maxlen:
                            stable_conf = sum(self.buffer_conf) / len(self.buffer_conf)
                        
                        if stable_conf is not None and stable_conf > CONF_THRESHOLD:
                            detected = True
                            offset_x = obj_cx - center_x
                            offset_y = obj_cy - center_y
                            
                            dist_x_cm = offset_x / pxlPercm
                            dist_y_cm = offset_y / pxlPercm
                            in_center = abs(offset_x) <= margin and abs(offset_y) <= margin
                else:
                    self.buffer_conf.clear()
                
                # Draw crosshair
                cv2.line(annotated, (center_x, 0), (center_x, rot_h), color, 2)
                cv2.line(annotated, (0, center_y), (rot_w, center_y), color, 2)
                cv2.rectangle(annotated, (center_x - margin, center_y - margin), (center_x + margin, center_y + margin), color, 2)
                
                # Draw center circle
                if detected and obj_cx is not None and (lab == "KFS-Blue" or lab == "KFS-Red"):
                    cv2.circle(annotated, (int(obj_cx), int(obj_cy)), 6, (255, 255, 0), -1)
                
                # Draw text
                txt = f"X:{dist_x_cm:.2f}cm | Y:{dist_y_cm:.2f}cm"
                cv2.putText(annotated, txt, (20, rot_h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 3, cv2.LINE_AA)
                cv2.putText(annotated, txt, (20, rot_h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 255), 1, cv2.LINE_AA)
                
                # Send frame
                frame_counter += 1
                if frame_counter % SEND_EVERY_N_FRAMES == 0:
                    display_frame = cv2.resize(annotated, (int(rot_w * 0.5), int(rot_h * 0.5)), interpolation=cv2.INTER_LINEAR)
                    try:
                        sender_q.put_nowait(display_frame)
                    except queue.Full:
                        dropped_counter += 1
                
                # Metrics logging
                fps_frame_count += 1
                now = time.time()
                if now - last_log_time >= FPS_LOG_INTERVAL:
                    elapsed = now - last_log_time
                    current_fps = fps_frame_count / elapsed
                    
                    with self.android_ip_lock:
                        target_mode = f"UNICAST ({self.android_ip})" if self.android_ip else "BROADCAST"
                    
                    print(f"[METRICS] FPS={current_fps:.1f} | sent={sent_counter} | dropped={dropped_counter} | mode={target_mode}")
                    
                    fps_frame_count = 0
                    last_log_time = now
                
                # Preview
                if DEBUG and SHOW_PREVIEW and (frame_counter % SHOW_EVERY_N_FRAMES == 0):
                    cv2.imshow("Annotated", annotated)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
        
        except KeyboardInterrupt:
            print("[INFO] Vision loop terminated by user")
        except Exception as e:
            print(f"[ERROR] Vision loop exception: {e}")
            traceback.print_exc()
        finally:
            worker_stop.set()
            sender_stop.set()
            try:
                yw_thread.join(timeout=1.0)
                s_thread.join(timeout=1.0)
            except:
                pass
            self.camera.release()
            cv2.destroyAllWindows()
    
    # ========================
    # SERVER CONTROL
    # ========================
    def start(self):
        """Start integrated server"""
        self.running = True
        
        # Connect to STM32
        if not self.connect_serial():
            print("[WARNING] Could not connect to STM32, running without serial")
        
        # Start ZMQ listener thread
        zmq_thread = threading.Thread(target=self.zmq_receive_loop, daemon=True)
        zmq_thread.start()
        
        # Start vision loop thread
        vision_thread = threading.Thread(target=self.vision_loop, daemon=True)
        vision_thread.start()
        
        print("[SERVER] Integrated Robot Server Running...")
        print("[SERVER] Press Ctrl+C to stop")
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[SERVER] Stopping...")
            self.stop()
    
    def stop(self):
        """Stop server"""
        self.running = False
        
        # Cleanup
        self.disconnect_serial()
        self.udp_socket.close()
        self.zmq_socket.close()
        self.zmq_detection_socket.close()
        self.zmq_context.term()
        
        print("[SERVER] Stopped")

# ========================
# MAIN
# ========================
if __name__ == "__main__":
    print("="*60)
    print("INTEGRATED ROBOT SERVER")
    print("="*60)
    print("Features:")
    print("  - ZMQ Command Receiver (Manual Control)")
    print("  - YOLO Vision Processing (Detection)")
    print("  - UDP Video Streaming (to Android)")
    print("  - Serial Communication (to STM32)")
    print("="*60)
    print()
    
    server = IntegratedRobotServer()
    server.start()
