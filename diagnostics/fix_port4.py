import serial, time
try:
    s = serial.Serial('/dev/ttyUSB0', 115200)
    print("Trying reverse mapping: DTR=SOP2, RTS=NRESET")
    s.dtr = True  # SOP2=0
    s.rts = True  # NRESET=0
    time.sleep(0.25)
    s.rts = False # NRESET=1
    
    print("Waiting for boot banner...")
    banner = b""
    start = time.time()
    while time.time() - start < 4.0:
        if s.in_waiting:
            chunk = s.read(s.in_waiting)
            banner += chunk
            if b"mmwDemo:/>" in chunk:
                break
        time.sleep(0.1)
    print("Banner received:")
    print(banner.decode(errors='ignore'))
    s.close()
except Exception as e:
    print(e)
