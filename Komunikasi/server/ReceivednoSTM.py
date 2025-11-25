import zmq
import time
import threading
from datetime import datetime

class ZMQRobotServer:
    def __init__(self, zmq_port=6000):
        """
        ZMQ Server untuk menerima data dari Android (TANPA STM32)
        Versi testing/debugging
        
        Args:
            zmq_port: Port untuk ZMQ (default 6000)
        """
        self.zmq_port = zmq_port
        
        # ZMQ Setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        
        # PENTING: Bind ke semua interface (0.0.0.0) agar bisa diakses dari HP
        self.socket.bind(f"tcp://0.0.0.0:{zmq_port}")
        
        # Robot State
        self.joystick_x = 0.0
        self.joystick_y = 0.0
        self.gripper1_value = 0.0
        self.gripper2_value = 0.0
        self.is_gripping = False
        self.mode = "MANUAL"
        
        # Statistics
        self.message_count = 0
        self.start_time = time.time()
        
        # Threading
        self.running = False
        self.zmq_thread = None
        
        print("=" * 60)
        print("🤖 ZMQ ROBOT SERVER - TESTING MODE (NO STM32)")
        print("=" * 60)
        print(f"[ZMQ] Server listening on port {zmq_port}")
        print(f"[INFO] Bind address: tcp://0.0.0.0:{zmq_port}")
        print(f"[INFO] Make sure Android connects to: tcp://YOUR_PC_IP:{zmq_port}")
        print("=" * 60)
        self.print_network_info()
        print("=" * 60)
    
    def print_network_info(self):
        """Print informasi network untuk debugging"""
        import socket
        hostname = socket.gethostname()
        
        try:
            # Dapatkan IP address
            local_ip = socket.gethostbyname(hostname)
            print(f"[NETWORK] Hostname: {hostname}")
            print(f"[NETWORK] Local IP: {local_ip}")
            print(f"[TIP] Use this IP in Android app: {local_ip}")
        except:
            print("[NETWORK] Could not determine local IP")
            print("[TIP] Run 'ipconfig' (Windows) or 'ifconfig' (Linux) to find IP")
    
    def parse_android_message(self, message):
        """
        Parse pesan dari Android dan tampilkan ke console
        
        Format dari Android:
        1. "x,y" - Joystick coordinates
        2. "abc,value1,value2" - Slider data  
        3. "PRESET:1" atau "PRESET:2" - Preset command
        4. "GRIPPER:GRIP_ON" atau "GRIPPER:GRIP_OFF" - Gripper toggle
        """
        try:
            msg = message.decode('utf-8').strip()
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.message_count += 1
            
            print(f"\n[{timestamp}] ✅ Message #{self.message_count} received")
            print(f"[RAW] {msg}")
            
            # Parse berdasarkan format
            if msg.startswith("PRESET:"):
                # Preset command
                preset_num = int(msg.split(":")[1])
                self.handle_preset(preset_num)
                
            elif msg.startswith("GRIPPER:"):
                # Gripper toggle
                gripper_state = msg.split(":")[1]
                self.handle_gripper_toggle(gripper_state)
                
            elif msg.startswith("abc,"):
                # Slider data: "abc,value1,value2"
                parts = msg.split(",")
                if len(parts) == 3:
                    gripper1 = float(parts[1])
                    gripper2 = float(parts[2])
                    self.handle_slider_data(gripper1, gripper2)
                    
            else:
                # Joystick coordinates: "x,y"
                parts = msg.split(",")
                if len(parts) == 2:
                    x = float(parts[0])
                    y = float(parts[1])
                    self.handle_joystick(x, y)
            
            # Print statistics
            elapsed = time.time() - self.start_time
            msg_per_sec = self.message_count / elapsed if elapsed > 0 else 0
            print(f"[STATS] Total messages: {self.message_count} | Rate: {msg_per_sec:.1f} msg/s")
            print("-" * 60)
                    
        except Exception as e:
            print(f"[ERROR] Failed to parse message: {e}")
            print(f"[ERROR] Raw bytes: {message}")
    
    def handle_joystick(self, x, y):
        """Handle joystick data"""
        self.joystick_x = x
        self.joystick_y = y
        
        # Visual representation
        direction = self.get_direction(x, y)
        magnitude = (x**2 + y**2)**0.5
        
        print(f"🕹️  JOYSTICK")
        print(f"   X: {x:+.3f} | Y: {y:+.3f}")
        print(f"   Direction: {direction}")
        print(f"   Magnitude: {magnitude:.3f}")
        
        # Simulate motor control
        left_speed = y + x
        right_speed = y - x
        max_val = max(abs(left_speed), abs(right_speed))
        if max_val > 1.0:
            left_speed /= max_val
            right_speed /= max_val
        
        print(f"   🔧 Motor L: {left_speed:+.3f} | R: {right_speed:+.3f}")
    
    def handle_slider_data(self, gripper1, gripper2):
        """Handle slider/gripper data"""
        self.gripper1_value = gripper1
        self.gripper2_value = gripper2
        
        # Visual bar
        bar1 = "█" * int(gripper1 / 10) + "░" * (10 - int(gripper1 / 10))
        bar2 = "█" * int(gripper2 / 10) + "░" * (10 - int(gripper2 / 10))
        
        print(f"🎚️  SLIDERS")
        print(f"   Gripper 1: {gripper1:6.2f} [{bar1}]")
        print(f"   Gripper 2: {gripper2:6.2f} [{bar2}]")
    
    def handle_preset(self, preset_number):
        """Handle preset command"""
        print(f"⚡ PRESET ACTIVATED")
        print(f"   Preset Number: {preset_number}")
        
        if preset_number == 1:
            print(f"   Action: Moving to HOME position")
        elif preset_number == 2:
            print(f"   Action: Moving to GRAB position")
        else:
            print(f"   Action: Unknown preset")
    
    def handle_gripper_toggle(self, state):
        """Handle gripper toggle ON/OFF"""
        self.is_gripping = (state == "GRIP_ON")
        
        status_icon = "🟢" if self.is_gripping else "🔴"
        status_text = "GRIPPING" if self.is_gripping else "RELEASED"
        
        print(f"✋ GRIPPER {status_icon}")
        print(f"   State: {status_text}")
    
    def get_direction(self, x, y):
        """Get text direction from joystick"""
        if abs(x) < 0.1 and abs(y) < 0.1:
            return "CENTER ●"
        
        import math
        angle = math.atan2(y, x) * 180 / math.pi
        
        if -22.5 <= angle < 22.5:
            return "RIGHT →"
        elif 22.5 <= angle < 67.5:
            return "UP-RIGHT ↗"
        elif 67.5 <= angle < 112.5:
            return "UP ↑"
        elif 112.5 <= angle < 157.5:
            return "UP-LEFT ↖"
        elif angle >= 157.5 or angle < -157.5:
            return "LEFT ←"
        elif -157.5 <= angle < -112.5:
            return "DOWN-LEFT ↙"
        elif -112.5 <= angle < -67.5:
            return "DOWN ↓"
        else:
            return "DOWN-RIGHT ↘"
    
    def zmq_receive_loop(self):
        """Loop utama untuk menerima data dari ZMQ"""
        print("\n[ZMQ] 👂 Listening for messages from Android...")
        print("[ZMQ] Waiting for connection...")
        print()
        
        while self.running:
            try:
                # Terima message (blocking)
                message = self.socket.recv()
                self.parse_android_message(message)
                
            except zmq.Again:
                continue
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[ZMQ] ❌ Error: {e}")
                time.sleep(0.1)
    
    def start(self):
        """Start server"""
        self.running = True
        self.start_time = time.time()
        
        # Start ZMQ receive thread
        self.zmq_thread = threading.Thread(target=self.zmq_receive_loop, daemon=True)
        self.zmq_thread.start()
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n\n[SERVER] 🛑 Stopping...")
            self.stop()
    
    def stop(self):
        """Stop server"""
        self.running = False
        
        if self.zmq_thread:
            self.zmq_thread.join(timeout=2)
        
        # Cleanup
        self.socket.close()
        self.context.term()
        
        print("\n" + "=" * 60)
        print("📊 SESSION SUMMARY")
        print("=" * 60)
        print(f"Total messages received: {self.message_count}")
        elapsed = time.time() - self.start_time
        print(f"Session duration: {elapsed:.1f} seconds")
        if self.message_count > 0:
            print(f"Average rate: {self.message_count / elapsed:.1f} msg/s")
        print("=" * 60)
        print("✅ Server stopped successfully")


# ============= MAIN PROGRAM =============
if __name__ == "__main__":
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║         ZMQ ROBOT SERVER - ANDROID TESTING MODE            ║")
    print("║                   (No STM32 Required)                      ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    
    # Konfigurasi
    ZMQ_PORT = 6000  # Port yang sama dengan Android
    
    print("⚙️  CONFIGURATION")
    print(f"   ZMQ Port: {ZMQ_PORT}")
    print()
    
    # Buat server
    server = ZMQRobotServer(zmq_port=ZMQ_PORT)
    
    print("\n💡 INSTRUCTIONS:")
    print("   1. Note your PC's IP address above")
    print("   2. Open Android app")
    print("   3. Tap Settings button (⚙️)")
    print("   4. Enter IP address and port 6000")
    print("   5. Tap CONNECT")
    print("   6. Move joystick or press buttons!")
    print()
    print("📝 Press Ctrl+C to stop server")
    print()
    
    # Start server
    try:
        server.start()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        server.stop()