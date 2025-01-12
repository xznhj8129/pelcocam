import serial
import pelco_d

CAM = 1
PORT = '/dev/ttyUSB0'
ser = serial.Serial(
    port=PORT,
    baudrate=9600,
    parity=serial.PARITY_NONE,
    stopbits=serial.STOPBITS_ONE,
    bytesize=serial.EIGHTBITS,
    rtscts=False,
    dsrdtr=False,
    timeout=0.1
)
command, parser = pelco_d.get(pelco_d.Zoom_Tele, CAM)
print(command)
ser.write(command)
response = ser.read(100)
print(parser(response, command[-1]))