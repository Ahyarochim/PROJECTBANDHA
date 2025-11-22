import sys
import zmq
import socket
import serial
import threading
import time

SERIAL_PORT = "/dev/ttyACM0"
BAUDRATE = 115200
ZMQ_PORT = 5555
RUNNING = True

# ========================================================================
# IP detection
# ========================================================================
def get_primary_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = socket.gethostbyname(socket.gethostname())
    finally:
        s.close()
    return ip


# ========================================================================
# Serial init
# ========================================================================
def init_serial():
    try:
        ser = serial.Serial(
            port=SERIAL_PORT,
            baudrate=BAUDRATE,
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
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        print(f"[OK] Connected to STM32 at {SERIAL_PORT} ({BAUDRATE} baud)")
        return ser
    except Exception as e:
        print(f"[ERROR] Cannot open serial port: {e}")
        sys.exit(1)


# ========================================================================
# Safe serial write with error handling
# ========================================================================
def safe_serial_write(ser, data_str):
    """Safely write to serial port with error handling and retry"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            ser.reset_output_buffer()
            ser.write(data_str.encode())
            ser.flush()
            return True
        except serial.SerialTimeoutException:
            print(f"[WARN] Write timeout (attempt {attempt + 1}/{max_retries})")
            time.sleep(0.1)
        except Exception as e:
            print(f"[ERROR] Write failed (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(0.1)
    return False


# ========================================================================
# Read thread
# ========================================================================
def read_from_stm32(ser):
    global RUNNING
    buffer = ""
    while RUNNING:
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                message = data.decode("utf-8", errors="ignore")
                for char in message:
                    if char in ("\n", "\r"):
                        if buffer.strip():
                            print(f"[STM32] {buffer.strip()}")
                        buffer = ""
                    else:
                        buffer += char
        except:
            pass
        time.sleep(0.01)


# ========================================================================
# MANUAL INPUT THREAD
# ========================================================================
def manual_input_sender(ser):
    global RUNNING
    while RUNNING:
        try:
            user = input("[INPUT] Masukkan Vx,Vy,W,motor1,motor2,servo: ").strip()
            if not user:
                continue

            parts = user.split(",")
            if len(parts) != 6:
                print("[WARN] Format harus: Vx,Vy,W,motor1,motor2,servo (6 nilai)")
                continue

            out_str = user + "\n"
            print("[→ STM32] Sending", repr(out_str))
            if not safe_serial_write(ser, out_str):
                print("[ERROR] Failed to send data after retries")

        except Exception as e:
            print("[ERROR] manual input:", e)
            break


# ========================================================================
# ZeroMQ server
# ========================================================================
def zmq_server(ser):
    global RUNNING

    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    bind_addr = f"tcp://10.106.19.63:{ZMQ_PORT}"
    sock.bind(bind_addr)
    sock.setsockopt(zmq.RCVTIMEO, 1000)

    print("\n📡 ZMQ Server listening at:", bind_addr, "\n")

    while RUNNING:
        try:
            msg = sock.recv_string().strip()
            print(f"[ZMQ] Received: {msg}")

            parts = msg.split(",")
            if len(parts) != 6:
                print("[WARN] Format salah (harus Vx,Vy,W,motor1,motor2,servo)")
                continue

            out_str = msg + "\n"
            print("[→ STM32] Sending", repr(out_str))
            if not safe_serial_write(ser, out_str):
                print("[ERROR] Failed to send data after retries")

        except zmq.Again:
            continue
        except Exception as e:
            print("[ERROR] ZMQ:", e)
            break

    sock.close()
    ctx.term()


# ========================================================================
# MAIN
# ========================================================================
def main():
    global RUNNING
    ser = init_serial()

    # Read thread
    threading.Thread(target=read_from_stm32, args=(ser,), daemon=True).start()

    # Manual input thread
    threading.Thread(target=manual_input_sender, args=(ser,), daemon=True).start()

    # ZMQ server thread
    try:
        zmq_server(ser)
    except KeyboardInterrupt:
        print("[INFO] Stop…")
    finally:
        RUNNING = False
        time.sleep(0.2)
        if ser.is_open:
            ser.close()

        print("[EXIT] Done.")


if __name__ == "__main__":
    main()
