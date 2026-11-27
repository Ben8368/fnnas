#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Append the Umi USB console to a host log across USB disconnects."""
import argparse
from datetime import datetime
from pathlib import Path
import sys
import threading
import time


def classify_port(port):
    identity = port.vid, port.pid, (port.serial_number or "").lower()
    if identity == (0x1D6B, 0x0104, "umi-acm"):
        return port.device, True  # older serial-login image
    if identity in {(0x1D6B, 0x0103, "umi-log"), (0x1D6B, 0x0104, "umi-log")}:
        return port.device, False  # diagnostics only
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="raw receive log; USB events go to OUTPUT.events")
    parser.add_argument("--interactive", action="store_true", help="accept console input; Ctrl+] exits")
    args = parser.parse_args()
    if args.interactive and not (sys.stdin.isatty() and sys.stdout.isatty()):
        parser.error("interactive mode requires a terminal")
    try:
        import serial
        from serial.tools import list_ports
        from serial.tools.miniterm import Console
    except ImportError:
        parser.exit(1, "Install pyserial with python -m pip install pyserial\n")

    def find_ports():
        return list(filter(None, map(classify_port, list_ports.comports())))

    console = Console() if args.interactive else None
    stop = threading.Event()
    connection_lock = threading.Lock()
    connection = None
    last_event = None

    def read_keys():
        while not stop.is_set():
            key = console.getkey()
            if key == "\x1d":
                stop.set()
                return
            if not key:
                continue
            with connection_lock:
                if connection is not None:
                    try:
                        connection.write(("\r" if key == "\n" else key).encode("utf-8", "replace"))
                    except serial.SerialException as error:
                        print(f"\nUSB input failed: {error}", file=sys.stderr, flush=True)

    with args.output.open("ab", buffering=0) as raw, Path(f"{args.output}.events").open(
        "a", encoding="utf-8", buffering=1
    ) as events:
        def event(message):
            nonlocal last_event
            if message == last_event:
                return
            last_event = message
            line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {message}"
            events.write(line + "\n")
            if console is not None:
                console.write(f"\r\n[{line}]\r\n")

        if console is not None:
            console.setup()
            threading.Thread(target=read_keys, daemon=True).start()
        try:
            event("Listening for Umi USB ACM (115200 8N1)")
            while not stop.is_set():
                ports = find_ports()
                if len(ports) != 1:
                    event("Waiting for Umi USB ACM" if not ports else "Multiple Umi ports present; waiting")
                    stop.wait(0.5)
                    continue
                (port, accepts_input), = ports
                try:
                    link = serial.Serial(baudrate=115200, timeout=0.25, write_timeout=0.5)
                    link.port = port
                    link.dtr = link.rts = False
                    link.open()
                except serial.SerialException as error:
                    event(f"Cannot open {port}: {error}")
                    stop.wait(0.5)
                    continue
                with connection_lock:
                    connection = link if accepts_input else None
                event(f"Connected {port}" + (" (read-only boot diagnostics)" if not accepts_input else ""))
                try:
                    check_port_at = time.monotonic() + 1
                    while not stop.is_set():
                        try:
                            data = link.read(4096)
                        except serial.SerialException as error:
                            event(f"Disconnected {port}: {error}")
                            break
                        if data:
                            raw.write(data)
                            if console is not None:
                                console.write_bytes(data)
                        if time.monotonic() >= check_port_at:
                            if (port, accepts_input) not in find_ports():
                                event(f"Disconnected {port}")
                                break
                            check_port_at = time.monotonic() + 1
                finally:
                    with connection_lock:
                        connection = None
                        link.close()
                stop.wait(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            event("Capture stopped")
            if console is not None:
                console.cleanup()


if __name__ == "__main__":
    main()
