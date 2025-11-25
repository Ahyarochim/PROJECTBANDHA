import zmq
import time
import serial
import threading
import struct
from enum import Enum

class RobotMode(Enum):
    MANUAL = 1
    AUTONOMOUS = 2

class ZMQRobotServer:
    def __init__(self, zmq_port=6000, serial_port='COM3', baud_rate=115200):
        """
        Inisialisasi ZMQ Server untuk menerima data dari Android
        dan meneruskan ke STM32
        
        Args:
            zmq_port: Port untuk ZMQ (default 6000)
            serial_port: Port serial STM32 (sesuaikan dengan sistem Anda)
            baud_rate: Baud rate komunikasi serial
        """
        self.zmq_port = zmq_port
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        
        # ZMQ Setup
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PULL)
        self.socket.bind(f"tcp://*:{zmq_port}")
        
        # Serial Setup untuk STM32
        self.ser = None
        self.serial_connected = False
        
        # Robot State
        self.mode = RobotMode.MANUAL
        self.joystick_x = 0.0
        self.joystick_y = 0.0
        self.gripper1_value = 0.0
        self.gripper2_value = 0.0
        self.is_gripping = False
        
        # Threading
        self.running = False
        self.zmq_thread = None
        
        print(f"[ZMQ] Server initialized on port {zmq_port}")
    
    def connect_serial(self):
        """Koneksi ke STM32 via Serial"""
        try:
            self.ser = serial.Serial(
                port=self.serial_port,
                baudrate=self.baud_rate,
                timeout=1,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            self.serial_connected = True
            print(f"[SERIAL] Connected to STM32 on {self.serial_port}")
            time.sleep(2)  # Tunggu STM32 ready
            return True
        except serial.SerialException as e:
            print(f"[SERIAL] Error: {e}")
            self.serial_connected = False
            return False
    
    def disconnect_serial(self):
        """Disconnect dari STM32"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.serial_connected = False
            print("[SERIAL] Disconnected")
    
    def send_to_stm(self, data):
        """
        Kirim data ke STM32 via Serial
        
        Format Protocol:
        - Start Byte: 0xFF
        - Command Type: 1 byte
        - Data Length: 1 byte
        - Data: variable bytes
        - Checksum: 1 byte
        - End Byte: 0xFE
        """
        if not self.serial_connected or not self.ser:
            print("[SERIAL] Not connected to STM32")
            return False
        
        try:
            # Buat packet dengan protokol
            packet = self.create_packet(data)
            self.ser.write(packet)
            print(f"[SERIAL] Sent to STM32: {packet.hex()}")
            return True
        except Exception as e:
            print(f"[SERIAL] Send error: {e}")
            return False
    
    def create_packet(self, data):
        """
        Membuat packet dengan format protokol
        
        Command Types:
        0x01: Joystick data (x, y)
        0x02: Gripper slider data (value1, value2)
        0x03: Preset command
        0x04: Gripper toggle (ON/OFF)
        0x05: Mode change
        """
        START_BYTE = 0xFF
        END_BYTE = 0xFE
        
        cmd_type = data['type']
        
        if cmd_type == 'joystick':
            # Format: type(1) + x(4 float) + y(4 float)
            cmd = 0x01
            payload = struct.pack('<Bff', cmd, data['x'], data['y'])
            
        elif cmd_type == 'slider':
            # Format: type(1) + gripper1(4 float) + gripper2(4 float)
            cmd = 0x02
            payload = struct.pack('<Bff', cmd, data['gripper1'], data['gripper2'])
            
        elif cmd_type == 'preset':
            # Format: type(1) + preset_number(1)
            cmd = 0x03
            payload = struct.pack('<BB', cmd, data['preset'])
            
        elif cmd_type == 'gripper_toggle':
            # Format: type(1) + state(1) [0=OFF, 1=ON]
            cmd = 0x04
            state = 1 if data['state'] == 'ON' else 0
            payload = struct.pack('<BB', cmd, state)
            
        elif cmd_type == 'mode':
            # Format: type(1) + mode(1) [1=MANUAL, 2=AUTO]
            cmd = 0x05
            mode_val = 1 if data['mode'] == 'MANUAL' else 2
            payload = struct.pack('<BB', cmd, mode_val)
        else:
            return b''
        
        # Hitung checksum (XOR semua byte)
        checksum = 0
        for byte in payload:
            checksum ^= byte
        
        # Buat packet lengkap
        packet = bytes([START_BYTE]) + payload + bytes([checksum, END_BYTE])
        return packet
    
    def parse_android_message(self, message):
        """
        Parse pesan dari Android dan kirim ke STM32
        
        Format dari Android:
        1. "x,y" - Joystick coordinates
        2. "abc,value1,value2" - Slider data
        3. "PRESET:1" atau "PRESET:2" - Preset command
        4. "GRIPPER:GRIP_ON" atau "GRIPPER:GRIP_OFF" - Gripper toggle
        """
        try:
            msg = message.decode('utf-8').strip()
            print(f"[ZMQ] Received: {msg}")
            
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
                    
        except Exception as e:
            print(f"[PARSE] Error parsing message: {e}")
    
    def handle_joystick(self, x, y):
        """Handle joystick data"""
        self.joystick_x = x
        self.joystick_y = y
        print(f"[JOYSTICK] X: {x:.2f}, Y: {y:.2f}")
        
        # Kirim ke STM32
        data = {
            'type': 'joystick',
            'x': x,
            'y': y
        }
        self.send_to_stm(data)
    
    def handle_slider_data(self, gripper1, gripper2):
        """Handle slider/gripper data"""
        self.gripper1_value = gripper1
        self.gripper2_value = gripper2
        print(f"[SLIDER] Gripper1: {gripper1:.2f}, Gripper2: {gripper2:.2f}")
        
        # Kirim ke STM32
        data = {
            'type': 'slider',
            'gripper1': gripper1,
            'gripper2': gripper2
        }
        self.send_to_stm(data)
    
    def handle_preset(self, preset_number):
        """Handle preset command"""
        print(f"[PRESET] Preset {preset_number} activated")
        
        # Kirim ke STM32
        data = {
            'type': 'preset',
            'preset': preset_number
        }
        self.send_to_stm(data)
    
    def handle_gripper_toggle(self, state):
        """Handle gripper toggle ON/OFF"""
        self.is_gripping = (state == "GRIP_ON")
        print(f"[GRIPPER] State: {state}")
        
        # Kirim ke STM32
        data = {
            'type': 'gripper_toggle',
            'state': 'ON' if self.is_gripping else 'OFF'
        }
        self.send_to_stm(data)
    
    def zmq_receive_loop(self):
        """Loop utama untuk menerima data dari ZMQ"""
        print("[ZMQ] Listening for messages...")
        
        while self.running:
            try:
                # Terima message dengan timeout
                if self.socket.poll(timeout=100):  # 100ms timeout
                    message = self.socket.recv()
                    self.parse_android_message(message)
            except zmq.Again:
                continue
            except Exception as e:
                print(f"[ZMQ] Error: {e}")
                time.sleep(0.1)
    
    def start(self):
        """Start server"""
        self.running = True
        
        # Connect ke STM32
        if not self.connect_serial():
            print("[WARNING] Could not connect to STM32, running in simulation mode")
        
        # Start ZMQ receive thread
        self.zmq_thread = threading.Thread(target=self.zmq_receive_loop, daemon=True)
        self.zmq_thread.start()
        
        print("[SERVER] Running... Press Ctrl+C to stop")
        
        try:
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n[SERVER] Stopping...")
            self.stop()
    
    def stop(self):
        """Stop server"""
        self.running = False
        
        if self.zmq_thread:
            self.zmq_thread.join(timeout=2)
        
        # Cleanup
        self.disconnect_serial()
        self.socket.close()
        self.context.term()
        print("[SERVER] Stopped")
    
    def get_status(self):
        """Get current robot status"""
        return {
            'mode': self.mode.name,
            'joystick': {'x': self.joystick_x, 'y': self.joystick_y},
            'grippers': {'gripper1': self.gripper1_value, 'gripper2': self.gripper2_value},
            'is_gripping': self.is_gripping,
            'serial_connected': self.serial_connected
        }


# ============= MAIN PROGRAM =============
if __name__ == "__main__":
    # Konfigurasi
    ZMQ_PORT = 6000  # Port yang sama dengan Android
    SERIAL_PORT = 'COM3'  # Sesuaikan dengan port STM32 Anda
    # Linux: '/dev/ttyUSB0' atau '/dev/ttyACM0'
    # Windows: 'COM3', 'COM4', dll
    BAUD_RATE = 115200
    
    # Buat server
    server = ZMQRobotServer(
        zmq_port=ZMQ_PORT,
        serial_port=SERIAL_PORT,
        baud_rate=BAUD_RATE
    )
    
    # Start server
    server.start()