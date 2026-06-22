import serial, time
try:
    print("Opening port...")
    s = serial.Serial('/dev/ttyUSB0', 115200)
    print("Flushing...")
    s.reset_input_buffer()
    print("Toggling DTR/RTS...")
    s.setDTR(True)
    s.setRTS(True)
    time.sleep(0.5)
    
    # Try different sequence just in case
    s.setRTS(False)
    time.sleep(0.5)
    s.setDTR(False)
    time.sleep(1.5)
    
    print("Sending enter...")
    s.write(b'\n')
    time.sleep(0.5)
    print("Response:")
    print(s.read_all().decode(errors='ignore'))
    s.close()
except Exception as e:
    print(e)
