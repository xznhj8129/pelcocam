import serial
import serial.rs485

import time
from libpelco import *

# Open the serial port (replace '/dev/ttyUSB0' with your actual serial port)
ser = serial.Serial('/dev/ttyUSB0',
                    baudrate=9600, 
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    bytesize=serial.EIGHTBITS,
                    timeout=3)
while 1:
    response = ser.read(100)
    time.sleep(0.1)
    if response!=b'':
        print(response)
        input("!")