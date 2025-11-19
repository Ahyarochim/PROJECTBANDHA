#!/usr/bin/env python3
import zmq
import time

def test_connection():
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    
    try:
        # Connect ke server
        socket.connect("tcp://127.0.0.1:5555")
        print("Connected to server at tcp://127.0.0.1:5555")
        
        # Tunggu sebentar untuk koneksi establish
        time.sleep(0.5)
        
        # Kirim test message
        message = "Test message from Python client"
        socket.send_string(message)
        print(f"Sent: {message}")
        
        # Tunggu sebentar sebelum tutup
        time.sleep(1)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        socket.close()
        context.term()
        print("Client closed")

if __name__ == "__main__":
    test_connection()