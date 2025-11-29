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
    def __init__(self, zmq_port=5555, serial_port='/dev/ttyACM0', baud_rate=115200):
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
        self.socket.bind(f"tcp://0.0.0.0:{zmq_port}")
        
        # Serial Setup untuk STM32
        self.ser = None
        self.serial_connected = False
        
        # Robot State
        self.mode = RobotMode.MANUAL
        self.motor1_value = 0.0

        # Command data
        self.last_command_type = None
        self.joystick_x = 0.0
        self.joystick_y = 0.0
        self.gripper1 = 0.0
        self.gripper2 = 0.0
        self.preset_num = 0
        self.gripper_state = "OFF"
        self.mode_value = "MANUAL"
        self.rotate_value = 0  # TAMBAHAN: untuk menyimpan nilai rotate
        
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
                timeout=0.1,
                write_timeout=2,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            time.sleep(2)  # Tunggu STM32 ready
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
        """Disconnect dari STM32"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.serial_connected = False
            print("[SERIAL] Disconnected")
    
    def send_to_stm(self):
        """Kirim data ke STM32 dalam format yang sesuai tipe command"""
        if not self.serial_connected or not self.ser:
            print("[SERIAL] Not connected to STM32")
            return False

        try:
            # Format berdasarkan tipe command terakhir yang diterima
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
            elif self.last_command_type == 'rotate':  # TAMBAHAN: handle rotate command
                data_str = f"ROT,{self.rotate_value}\n"
            else:
                # Default: motor1 value only
                data_str = f"{self.motor1_value:.2f}\n"

            self.ser.write(data_str.encode())
            self.ser.flush()
            print(f"[SERIAL] Sent: {repr(data_str.strip())}")
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
            
        # TAMBAHAN: Handle rotate command
        elif cmd_type == 'rotate':
            # Format: type(1) + rotate_value(1 signed byte) [-5, 0, +5]
            cmd = 0x06
            payload = struct.pack('<Bb', cmd, data['rotate'])
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
        1. "x,y" - Joystick (JOY,x,y)
        2. "SLIDER:g1,g2" - Slider (SLD,g1,g2)
        3. "PRESET:1" - Preset (PRE,1)
        4. "GRIPPER:GRIP_ON" - Gripper (GRP,ON/OFF)
        5. "MODE:MANUAL" - Mode (MOD,MANUAL/AUTO)
        6. "100.5" - Motor1 value only
        """
        try:
            msg = message.decode('utf-8').strip()
            print(f"[ZMQ] Received: {msg}")

            # Parse berdasarkan format
            if msg.startswith("PRESET:"):
                # PRESET:1 atau PRESET:2
                self.last_command_type = 'preset'
                self.preset_num = int(msg.split(":")[1])
                print(f"[PRESET] Num: {self.preset_num}")
                self.send_to_stm()

            elif msg.startswith("GRIPPER:"):
                # GRIPPER:GRIP_ON atau GRIPPER:GRIP_OFF
                self.last_command_type = 'gripper_toggle'
                state = msg.split(":")[1]
                self.gripper_state = "ON" if state == "GRIP_ON" else "OFF"
                print(f"[GRIPPER] State: {self.gripper_state}")
                self.send_to_stm()

            elif msg.startswith("MODE:"):
                # MODE:MANUAL atau MODE:AUTO
                self.last_command_type = 'mode'
                self.mode_value = msg.split(":")[1]
                print(f"[MODE] Value: {self.mode_value}")
                self.send_to_stm()

            elif msg.startswith("SLIDER:"):
                # SLIDER:g1,g2
                self.last_command_type = 'slider'
                data_part = msg.split(":", 1)[1]
                parts = data_part.split(",")
                if len(parts) == 2:
                    self.gripper1 = float(parts[0])
                    self.gripper2 = float(parts[1])
                    print(f"[SLIDER] G1: {self.gripper1:.2f}, G2: {self.gripper2:.2f}")
                    self.send_to_stm()
                    
            # TAMBAHAN: Handle ROTATE command
            elif msg.startswith("ROTATE:"):
                # ROTATE:-5 atau ROTATE:0 atau ROTATE:5
                self.last_command_type = 'rotate'
                self.rotate_value = int(msg.split(":")[1])
                print(f"[ROTATE] Value: {self.rotate_value}")
                self.send_to_stm()

            else:
                # Numeric data (CSV atau single value)
                parts = msg.split(",")

                if len(parts) == 2:
                    # Joystick: x,y
                    self.last_command_type = 'joystick'
                    self.joystick_x = float(parts[0])
                    self.joystick_y = float(parts[1])
                    print(f"[JOYSTICK] X: {self.joystick_x:.2f}, Y: {self.joystick_y:.2f}")
                    self.send_to_stm()

                elif len(parts) == 1:
                    # Motor1 value only
                    self.last_command_type = None
                    self.motor1_value = float(parts[0])
                    print(f"[MOTOR1] Value: {self.motor1_value:.2f}")
                    self.send_to_stm()
                else:
                    print(f"[WARN] Invalid format (got {len(parts)} values)")

        except ValueError as e:
            print(f"[ERROR] Parsing error: {e}")
        except Exception as e:
            print(f"[PARSE] Error parsing message: {e}")
    
    
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
            'motor1': self.motor1_value,
            'serial_connected': self.serial_connected,
            'rotate': self.rotate_value  # TAMBAHAN
        }


# ============= MAIN PROGRAM =============
if __name__ == "__main__":
    # Konfigurasi
    ZMQ_PORT = 6000  # Port yang sama dengan Android
    SERIAL_PORT = 'COM14'  # Sesuaikan dengan port STM32 Anda
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