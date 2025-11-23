import cv2

print("=== PROGRAM BUKA KAMERA MANUAL + SET RESOLUSI ===")
print("Contoh input kamera:")
print("  • 0 / 1 / 2  (index kamera)")
print("  • /dev/video2 (Linux)")
print("  • rtsp://xxx (IP camera)")
print("===================================")

# Input kamera
device = input("Masukkan input kamera: ")

# Jika angka → jadikan integer
try:
    device = int(device)
except:
    pass

# Buka kamera
cap = cv2.VideoCapture(device)

if not cap.isOpened():
    print("❌ Kamera gagal dibuka. Coba input lain.")
    exit()

# Input resolusi manual
print("\n=== INPUT RESOLUSI MANUAL ===")
width = int(input("Masukkan FRAME_WIDTH: "))
height = int(input("Masukkan FRAME_HEIGHT: "))

cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

print("\nTekan 'q' untuk keluar...")
print("Resolusi diterapkan, cek ukuran frame realtime di title window.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("❌ Frame tidak dapat dibaca.")
        break

    h, w = frame.shape[:2]
    window_title = f"Kamera: {device} | {w} x {h}"
    cv2.imshow(window_title, frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
