"""
Serial port helper functions.
"""

import serial.tools.list_ports


# ============================================================
# SERIAL PORT DEBUG
# ============================================================

def list_serial_ports():
    print("===================================================")
    print(" Available Serial Ports")
    print("===================================================")

    ports = list(serial.tools.list_ports.comports())

    if not ports:
        print("[WARN] No serial ports found.")
        return

    for port in ports:
        print(f"{port.device} | {port.description}")

    print("===================================================")
