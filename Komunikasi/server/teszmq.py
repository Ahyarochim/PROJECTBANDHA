import zmq

def main():
    # Membuat konteks ZMQ
    context = zmq.Context()

    # Membuat socket tipe PULL
    socket = context.socket(zmq.PULL)
    socket.bind("tcp://*:5560")   # menerima dari port 5560

    print("Receiver siap, menunggu data...")

    while True:
        message = socket.recv_string()
        print(f"Data diterima: {message}")

if __name__ == "__main__":
    main()
