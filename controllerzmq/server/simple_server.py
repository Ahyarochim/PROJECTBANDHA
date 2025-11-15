import zmq
import time

def simple_server():
    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    
    try:
        socket.bind("tcp://*:5555")
        print("Server started on port 5555")
        print("Waiting for messages...")
        
        while True:
            try:
                # Wait for message with timeout
                message = socket.recv_string(zmq.NOBLOCK)
                print(f"Received: {message}")
            except zmq.Again:
                # No message received, continue
                time.sleep(0.1)
                continue
                
    except KeyboardInterrupt:
        print("\nServer stopped by user")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    simple_server()