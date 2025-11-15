# zmq_server_simple.py
import sys
import zmq
import socket

def get_primary_ip() -> str:
    """IP yang dipakai keluar jaringan (bukan 127.x)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # tidak benar-benar mengirim paket
        ip = s.getsockname()[0]
    except Exception:
        ip = socket.gethostbyname(socket.gethostname())
    finally:
        s.close()
    return ip

def list_ips():
    """Kembalikan daftar IP IPv4 non-localhost yang terdeteksi."""
    ips = set()
    # IP utama via metode UDP
    ips.add(get_primary_ip())
    # Coba kumpulkan dari netifaces jika ada
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

def main():
    port = 5555
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
            assert 1 <= port <= 65535
        except Exception:
            print("Port tidak valid. Gunakan default 5555.")
            port = 5555

    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    bind_addr = f"tcp://0.0.0.0:{port}"
    sock.bind(bind_addr)
    sock.setsockopt(zmq.RCVTIMEO, 1000)  # timeout receive 1 detik

    # Tampilkan IP yan\g bisa dipakai klien
    print("ZeroMQ PULL server berjalan.")
    print(f"Bind   : {bind_addr}")
    print("Akses dari perangkat lain gunakan salah satu IP berikut:")
    for ip in list_ips():
        print(f" - {ip}:{port}")
    print(f" - 127.0.0.1:{port} (localhost)")
    print("Menunggu pesan. Tekan Ctrl+C untuk berhenti.")

    try:
        while True:
            try:
                msg = sock.recv_string()  # blocking hingga timeout
                print(msg)
            except zmq.Again:
                continue
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        ctx.term()
        print("Server berhenti.")

if __name__ == "__main__":
    main()
