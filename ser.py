import serial
import serial.rs485

import time
from libpelco import *

pelco = PelcoFunctions()

def angle_to_bytes(angle):
    if not 0 <= angle <= 360:
        raise ValueError("Angle must be between 0 and 360 degrees inclusive.")

    centidegrees = int(angle * 100)
    msb = (centidegrees >> 8) & 0xFF
    lsb = centidegrees & 0xFF

    return msb, lsb



# Function to send data
def send_data(data):
    ser.write(data)

def set_tilt(ang):
    msb, lsb = angle_to_bytes(ang)
    cmd = pelco._construct_cmd('SET-TILT', msb, lsb)
    ser.write(data)

def set_pan(ang):
    msb, lsb = angle_to_bytes(ang)
    cmd = pelco._construct_cmd('SET-PAN', msb, lsb)
    ser.write(data)

def set_zoom(z):
    
    (data)

# Open the serial port (replace '/dev/ttyUSB0' with your actual serial port)
PORT = '/dev/ttyUSB0'
ser = serial.Serial(
    port=PORT,
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    rtscts=False,
    dsrdtr=False,
    timeout=1
)

"""ser2 = serial.rs485.RS485(
    port=PORT,
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    timeout=1
)

# Configure RS485 mode
ser2.rs485_mode = serial.rs485.RS485Settings(
    rts_level_for_tx=True,   # RTS is driven high during transmit
    rts_level_for_rx=False,  # RTS is driven low during receive
    loopback=True,
    delay_before_tx=0.01,       # Can be helpful if your adapter needs time
    delay_before_rx=0.01        # to switch between send/receive
)"""

# Send data
cmd = pelco._construct_cmd('SET-PAN', 0x02, 0x02)
print(f"Constructed Command: {cmd}")

#ser.setRTS(True)
ser.write(cmd)
response = ser.read(100)
print(response)

cmd = pelco._construct_cmd('QUERY-PAN', 0x01, 0x01)
print(f"Constructed Command: {cmd}")
#ser.setRTS(True)
ser.write(cmd)
response = ser.read(100)
print(response)
#time.sleep(10)
#msb, lsb = angle_to_bytes(20)
#cmd = pelco._construct_cmd('SET-TILT', msb, lsb)
#print(f"Constructed Command: {cmd}")
#send_data(cmd)


#ser.close()
