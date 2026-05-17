"""serial_to_tcp.py

Simple serial -> TCP bridge. Forwards lines read from the serial device to
all connected TCP clients. Use this when you want localhost:4000 to expose
your ESP32 USB serial output to tools that expect a TCP socket.

Example:
  python serial_to_tcp.py --device COM3 --baud 115200 --port 4000
"""

import argparse
import socket
import serial
import threading
import time


clients = set()
clients_lock = threading.Lock()


def serial_broadcaster(ser, stop_event):
    while not stop_event.is_set():
        try:
            b = ser.readline()
            if not b:
                continue
            with clients_lock:
                for c in list(clients):
                    try:
                        c.sendall(b)
                    except Exception:
                        try:
                            c.close()
                        except Exception:
                            pass
                        clients.discard(c)
        except Exception as e:
            print("Serial read error:", e)
            time.sleep(0.1)


def acceptor(srv, stop_event):
    while not stop_event.is_set():
        try:
            conn, addr = srv.accept()
            with clients_lock:
                clients.add(conn)
            print("Client connected:", addr)
        except Exception as e:
            if stop_event.is_set():
                break
            print("Accept error:", e)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", required=True)   # e.g. COM3 or /dev/ttyUSB0
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--port", type=int, default=4000)
    args = p.parse_args()

    ser = serial.Serial(args.device, args.baud, timeout=1)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(5)
    print(f"Listening on :{args.port}, forwarding from {args.device}@{args.baud}")

    stop_event = threading.Event()
    t_accept = threading.Thread(target=acceptor, args=(srv, stop_event), daemon=True)
    t_serial = threading.Thread(target=serial_broadcaster, args=(ser, stop_event), daemon=True)
    t_accept.start()
    t_serial.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        stop_event.set()
        # close client sockets
        with clients_lock:
            for c in list(clients):
                try:
                    c.close()
                except Exception:
                    pass
            clients.clear()
        try:
            srv.close()
        except Exception:
            pass
        try:
            ser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()