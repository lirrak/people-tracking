import serial, time
try:
    print("Opening port...")
    s = serial.Serial('/dev/ttyUSB0', 115200, timeout=1, dsrdtr=False, rtscts=False)
    print("Toggling DTR/RTS...")
    s.dtr = True
    s.rts = True
    time.sleep(0.5)
    s.rts = False
    time.sleep(1.0)
    s.dtr = False
    time.sleep(1.0)
    print("Sending enter...")
    s.write(b'\n')
    time.sleep(0.5)
    print("Response:")
    print(s.read_all().decode(errors='ignore'))
    s.close()
except Exception as e:
    print(e)
