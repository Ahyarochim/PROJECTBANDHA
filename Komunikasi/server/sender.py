import zmq
import time

def main():
    context = zmq.Context()
    
    # Socket to send messages to
    sender = context.socket(zmq.PUSH)
    sender.connect("tcp://localhost:5555")
    
    print("Sender started. Sending messages...")
    
    for i in range(10):
        msg = f"Message {i+1}"
        print(f"Sending: {msg}")
        sender.send_string(msg)
        time.sleep(1)
        
    print("Finished sending.")

if __name__ == "__main__":
    main()
