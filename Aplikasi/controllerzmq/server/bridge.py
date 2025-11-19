import zmq
import json
import serial
import time


# -------------------------
# SAFE SERIAL WRITE WRAPPER
# -------------------------
def safe_write(ser, packet):
    if ser is None:
        print("[DEBUG] Serial OFF →", packet)
        return

    try:
        ser.write(packet.encode())
    except Exception as e:
        print("[SERIAL ERROR]", e)


# -------------------------
# HANDLERS
# -------------------------
def handle_vision(data, ser):
    obj = data.get("object", "unknown")
    x = data.get("x", 0)
    y = data.get("y", 0)
    conf = data.get("conf", 0)

    packet = f"<VISION;OBJ:{obj};X:{x};Y:{y};CONF:{conf}>"
    print("To STM:", packet)
    safe_write(ser, packet)


def handle_control(data, ser):
    cmd = data.get("command", "NONE")
    vx = data.get("vx", 0)
    vy = data.get("vy", 0)
    rot = data.get("rotation", 0)

    packet = f"<CONTROL;CMD:{cmd};VX:{vx};VY:{vy};ROT:{rot}>"
    print("To STM:", packet)
    safe_write(ser, packet)


# -------------------------
# TRY OPEN SERIAL
# -------------------------
def try_open_serial(port="COM5", baud=115200):
    try:
        ser = serial.Serial(port, baud, timeout=1)
        time.sleep(2)
        print(f"[SERIAL] Connected → {port}")
        return ser
    except Exception as e:
        print(f"[SERIAL WARNING] Cannot open {port}. Running WITHOUT serial.")
        print("Reason:", e)
        return None


# -------------------------
# MAIN LOOP
# -------------------------
def main():
    # ZMQ init
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    sock.bind("tcp://*:5555")

    print("Bridge running on port 5555...")

    # Try open serial
    ser = try_open_serial("COM5")

    while True:
        try:
            msg = sock.recv_string()
            print("RAW:", msg)

            data = json.loads(msg)
            dtype = data.get("type")

            if dtype == "VISION":
                handle_vision(data, ser)

            elif dtype == "CONTROL":
                handle_control(data, ser)

        except Exception as e:
            print("[ERROR]", e)


if __name__ == "__main__":
    main()
