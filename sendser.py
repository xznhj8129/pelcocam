#!/usr/bin/python2
import serial
import time
import os
from time import localtime, strftime

def timestamp():
    return strftime("%d %b %Y %H:%M:%S", localtime())

serialdevice = "/dev/ttyUSB1"

ser = serial.Serial(
port=serialdevice,\
baudrate=9600,\
parity=serial.PARITY_NONE,\
stopbits=serial.STOPBITS_ONE,\
bytesize=serial.EIGHTBITS,\
timeout=0)
line = []

msg = b'\xff\x01\x00Q\x00\x00R'
ser.write(msg+b'\n')
for c in ser.read():
    print(c)
    if c != b'\n':
        line.append(c)
    if c== b'\n':
        strline=''
        for i in line:
            strline=strline+i
        print(strline)


ser.close()
