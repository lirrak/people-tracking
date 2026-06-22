import serial, time
try:
    s = serial.Serial('/dev/ttyUSB0', 115200, timeout=1)
    s.write(b'\n')
    time.sleep(0.1)
    print(s.read_all().decode(errors='ignore'))
    s.close()
except Exception as e:
    print(e)
