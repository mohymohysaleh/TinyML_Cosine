#!/usr/bin/env python3
"""
plot_serial_tcp.py

Connects to a serial-over-TCP server (RFC2217) or raw TCP port and plots
incoming numeric data in real time. Designed to work with the ESP32 sketch
that prints two numeric values per line (predicted,actual) but will handle
single-value lines as well.

Usage:
  python plot_serial_tcp.py --host localhost --port 4000 --method rfc2217

Dependencies:
  pip install pyserial matplotlib
"""
import argparse
import collections
import threading
import time
import re
import socket
import sys

from matplotlib import pyplot as plt
from matplotlib.animation import FuncAnimation

try:
    import serial
except Exception:
    serial = None

LINE_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def reader_rfc2217(host, port, baud, stop_event, lines):
    if serial is None:
        print("pyserial is required for rfc2217 mode. Install: pip install pyserial")
        stop_event.set()
        return
    url = f"rfc2217://{host}:{port}"
    while not stop_event.is_set():
        try:
            ser = serial.serial_for_url(url, baudrate=baud, timeout=1)
            try:
                while not stop_event.is_set():
                    b = ser.readline()
                    if not b:
                        continue
                    # serial library may already return decoded strings
                    if isinstance(b, bytes):
                        s = b.decode("utf-8", errors="replace").strip()
                    else:
                        s = str(b).strip()
                    lines.append(s)
            finally:
                try:
                    ser.close()
                except Exception:
                    pass
        except Exception as e:
            print(f"RFC2217 connection failed ({e}); retrying in 1s...")
            time.sleep(1)


def reader_raw_tcp(host, port, stop_event, lines):
    # Connect as a simple TCP client and read newline-separated text lines.
    # Retry until the server appears (useful for Wokwi starting later).
    while not stop_event.is_set():
        try:
            with socket.create_connection((host, port), timeout=5) as sock:
                f = sock.makefile("r")
                print(f"Connected to {host}:{port}")
                while not stop_event.is_set():
                    line = f.readline()
                    if not line:
                        time.sleep(0.01)
                        continue
                    lines.append(line.strip())
        except Exception as e:
            print(f"TCP connection failed ({e}); retrying in 1s...")
            time.sleep(1)


def reader_serial(device, baud, stop_event, lines):
    # Read directly from a local serial device (no TCP)
    if serial is None:
        print("pyserial is required for serial mode. Install: pip install pyserial")
        stop_event.set()
        return
    try:
        ser = serial.Serial(device, baud, timeout=1)
    except Exception as e:
        print(f"Could not open serial port {device}: {e}")
        stop_event.set()
        return
    try:
        while not stop_event.is_set():
            b = ser.readline()
            if not b:
                continue
            if isinstance(b, bytes):
                s = b.decode("utf-8", errors="replace").strip()
            else:
                s = str(b).strip()
            lines.append(s)
    finally:
        try:
            ser.close()
        except Exception:
            pass


def parse_numbers(s):
    return [float(m.group(0)) for m in LINE_RE.finditer(s)]


def main():
    parser = argparse.ArgumentParser(description="Plot serial-over-TCP data (RFC2217 or raw TCP).")
    parser.add_argument("--host", default="localhost", help="server host")
    parser.add_argument("--port", type=int, default=4000, help="server port")
    parser.add_argument("--method", choices=["rfc2217", "raw", "serial"], default="rfc2217")
    parser.add_argument("--maxlen", type=int, default=500, help="points to display")
    parser.add_argument("--device", default=None, help="serial device for --method serial (e.g. COM3 or /dev/ttyUSB0)")
    parser.add_argument("--baud", type=int, default=115200, help="baud rate for --method serial")
    args = parser.parse_args()

    lines = collections.deque()
    series0 = collections.deque(maxlen=args.maxlen)
    series1 = collections.deque(maxlen=args.maxlen)

    stop_event = threading.Event()
    if args.method == "rfc2217":
        t = threading.Thread(target=reader_rfc2217, args=(args.host, args.port, args.baud, stop_event, lines), daemon=True)
    elif args.method == "raw":
        t = threading.Thread(target=reader_raw_tcp, args=(args.host, args.port, stop_event, lines), daemon=True)
    else:
        if not args.device:
            print("--device is required for --method serial")
            return
        t = threading.Thread(target=reader_serial, args=(args.device, args.baud, stop_event, lines), daemon=True)
    t.start()

    fig, ax = plt.subplots()
    ln0, = ax.plot([], [], label="value0")
    ln1, = ax.plot([], [], label="value1")
    ax.legend()
    ax.set_xlabel("samples")
    ax.grid(True)

    def init():
        ln0.set_data([], [])
        ln1.set_data([], [])
        return ln0, ln1

    def update(frame):
        # consume all pending lines
        while lines:
            s = lines.popleft()
            print(f"[DEBUG] Received line: {s}")  # Added for debugging
            nums = parse_numbers(s)
            if not nums:
                continue
            if len(nums) == 1:
                series0.append(nums[0])
                # keep series1 length in sync
                series1.append(float('nan'))
            else:
                series0.append(nums[0])
                series1.append(nums[1])

        x = list(range(len(series0)))
        y0 = list(series0)
        y1 = list(series1)
        if not x:
            return ln0, ln1

        ln0.set_data(x, y0)
        ln1.set_data(x, y1)
        ax.relim()
        ax.autoscale_view()
        return ln0, ln1

    ani = FuncAnimation(fig, update, init_func=init, interval=50, blit=False, cache_frame_data=False)

    try:
        plt.show()
    finally:
        stop_event.set()


if __name__ == '__main__':
    main()
