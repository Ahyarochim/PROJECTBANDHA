import sys
import zmq
import socket
import serial
import threading
import time


SERIAL_PORT = "COM4"       # Ubah sesuai port STM32 kamu
BAUDRATE = 115200
ZMQ_PORT = 5555
RUNNING = True


# =====================================================
# 🔹 Fungsi IP Detection
# =====================================================
def get_primary_ip() -> str:
    """Cari IP utama (bukan 127.x)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = socket.gethostbyname(socket.gethostname())
    finally:
        s.close()
    return ip


def list_ips():
    """List semua IP IPv4 non-localhost."""
    ips = {get_primary_ip()}
    try:
        import netifaces
        for iface in netifaces.interfaces():
            for a in netifaces.ifaddresses(iface).get(netifaces.AF_INET, []):
                ip = a.get("addr")
                if ip and not ip.startswith(("127.", "169.254.")):
                    ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


# =====================================================
# 🔹 Serial Initialization
# =====================================================
def init_serial():
    """Buka koneksi serial ke STM32."""
    try:
        ser = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=0.1)
        time.sleep(2)
        print(f"[OK] Connected to STM32 at {SERIAL_PORT} ({BAUDRATE} baud)")
        return ser
    except Exception as e:
        print(f"[ERROR] Cannot open serial port: {e}")
        sys.exit(1)


# =====================================================
# 🔹 Thread untuk baca data dari STM32
# =====================================================
def read_from_stm32(ser: serial.Serial):
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
        except Exception as e:
            if RUNNING:
                print(f"[ERROR] Serial read error: {e}")
        time.sleep(0.01)


# =====================================================
# 🔹 ZeroMQ Server — Terima data & kirim ke STM32
# =====================================================
def zmq_server(ser: serial.Serial):
    global RUNNING

    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    bind_addr = f"tcp://10.105.96.203:{ZMQ_PORT}"  # Ganti IP sesuai PC kamu
    sock.bind(bind_addr)
    sock.setsockopt(zmq.RCVTIMEO, 1000)

    print("\n===============================================")
    print("📡 ZeroMQ PULL server berjalan")
    print(f"Bind address: {bind_addr}")
    print("Akses dari perangkat lain:")
    for ip in list_ips():
        print(f"  → tcp://{ip}:{ZMQ_PORT}")
    print("===============================================\n")

    while RUNNING:
        try:
            msg = sock.recv_string().strip()
            print(f"[ZMQ] Received: {msg}")

            # --- 🔹 Parsing koordinat ---
            try:
                parts = [p.strip() for p in msg.split(",")]
                if len(parts) == 4:
                    x, y, z, g = parts
                    print(f"  → Parsed → X={x}, Y={y}, Z={z}, G={g}")
                else:
                    print("[WARN] Invalid data format (expected 4 comma-separated values)")
                    continue
            except Exception as e:
                print(f"[ERROR] Parsing error: {e}")
                continue

            # --- 🔹 Kirim ke STM32 ---
            if ser and ser.is_open:
                # Format string untuk dikirim ke STM32
                out_str = f"{x},{y},{z},{g}\n"
                print("[→ STM32] Sending", repr(out_str))
                ser.write(out_str.encode())
                print(f"[→ STM32] Sent: {out_str.strip()}")

        except zmq.Again:
            continue
        except Exception as e:
            print(f"[ERROR] ZMQ error: {e}")
            break

    sock.close()
    ctx.term()
    print("[ZMQ] Server stopped")


# =====================================================
# 🔹 Main Program
# =====================================================
def main():
    global RUNNING
    ser = init_serial()

    t_serial = threading.Thread(target=read_from_stm32, args=(ser,), daemon=True)
    t_serial.start()

    try:
        zmq_server(ser)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping...")
    finally:
        RUNNING = False
        time.sleep(0.2)
        if ser.is_open:
            ser.close()
        print("[OK] Serial port closed")
        print("[EXIT] Program stopped")


if __name__ == "__main__":
    main()
