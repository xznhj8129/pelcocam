import pygame
import serial
import serial.rs485
import time
from libpelco import *

def angle_to_bytes(angle):
    if not 0 <= angle <= 360:
        raise ValueError("Angle must be between 0 and 360 degrees inclusive.")
    centidegrees = int(angle * 100)
    msb = (centidegrees >> 8) & 0xFF
    lsb = centidegrees & 0xFF
    return msb, lsb

def set_tilt(ang):
    msb, lsb = angle_to_bytes(ang)
    cmd = pelco._construct_cmd('SET-TILT', msb, lsb)
    ser.write(data)

def set_pan(ang):
    msb, lsb = angle_to_bytes(ang)
    cmd = pelco._construct_cmd('SET-PAN', msb, lsb)
    ser.write(data)
    
def set_zoom(zoom_value):
    zoom_value = max(0, min(1, zoom_value))
    zoom_level = int(zoom_value * 2000)#65535)
    msb = (zoom_level >> 8) & 0xFF
    lsb = zoom_level & 0xFF
    return msb, lsb

def get_joystick(joystick):
    # roll, pitch, throt, yaw, SE, SB, SF, SE; Down/Left= -1
    #Far LT     6
    #Near LT    4
    #Far RT     7
    #Near RT    5
    #A1         0
    #B          1
    #C          2
    #D          3
    # SELECT    8
    # START     9
    #JSCLICK L 10
    #JSCLICK R  11
    # Down = positive direction
    #L JOY DOWN 2
    #L JOY RIGHT 1
    #R JOY DOWN  3
    #R JOY RIGHT 4
    axisdata = [[0]*12, [0]*12]
    axes = [0] * 12
    buttons = [0] * 12
    for i in range(joystick.get_numaxes()):
        axis = joystick.get_axis(i)
        #if axis!=0:
        #    print('axis',i, axis)
        axes[i] = axis
    for i in range(joystick.get_numbuttons()):
        btt = joystick.get_button(i)
        #if btt!=0:
        #    print('button',i, btt)
        buttons[i] = btt
    return axes, buttons


def map_speed(value):
    """Map joystick input from -1.0 - 1.0 to 0x00 - 0x3F"""
    return int(abs(value) * 0x3F)


def send_data(command2, b1, b2, command1=0x00):
    #print(command2, b1, b2)
    cmd = pelco._construct_cmd(command2, b1, b2)
    ser.write(cmd)
    response = ser.read(100)
    #if len(response)>0: print(response)
    return response


pelco = PelcoFunctions()
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
    timeout=0.1
)

    
# Initialize pygame and the joystick
pygame.init()
pygame.joystick.init()

# Check if there is at least one joystick connected
if pygame.joystick.get_count() == 0:
    print("No joystick connected.")
    pygame.quit()
    exit()

# Use the first joystick
joystick = pygame.joystick.Joystick(0)
joystick.init()

print("Joystick initialized.")
import math
last = ""
command="1"
zoom = 0
zoomlvl = 0
focus = 0
setfocus = 0
autofocus = False
buttondebounce = [False] * 12
setautofocus = True
nv = False

#input('...')
#for i in range(255):
    #x = i & 0xFF
    #print(i,x)
    #send_data('CLEAR-PRESET', 0x00, x)
    #time.sleep(0.1)
    #send_data('UP', map_speed(1), map_speed(1))
    #time.sleep(0.5)
    #send_data('STOP', 0x00, 0x00)
    #time.sleep(0.1)
    #send_data('RIGHT', map_speed(1), map_speed(1))
    #time.sleep(0.1)

stopped = False
try:
    while True:
        panmove = None
        tiltmove = None
        zoommove = False
        focusmove = False
        # Process pygame events
        pygame.event.pump()
        
        axis,buttons = get_joystick(joystick)
        # Get axis values (assuming axis 0 is left/right and axis 1 is up/down)
        pan = round(axis[0], 2)  # Horizontal axis
        tilt = round(axis[1] *-1, 2)  # Vertical axis

        focus+= (buttons[5] - buttons[7])/100.0
        zoom+= (buttons[6] - buttons[4])/100.0
        if zoom < 0: zoom = 0
        #zoom = (round(joystick.get_axis(2), 1) - 1) / -2
        #print(1, round(joystick.get_axis(0)))
        #print(2, round(joystick.get_axis(1)))
        #print(3, round(joystick.get_axis(2)))
        #print(4, round(joystick.get_axis(3)))
        
        # Convert axis values to speed
        pan_speed = map_speed(pan)
        tilt_speed = map_speed(tilt)

        if zoom!=zoomlvl:
            zoommove = True
            zoomlvl = zoom
            msb, lsb = set_zoom(zoom)
            send_data('SET-ZOOM', msb, lsb)
            
        if focus!=setfocus :
            focusmove = True
            setfocus = focus
            msb, lsb = set_zoom(focus)
            send_data('SET-FOCUS', msb, lsb)

        if pan < -0.1:
            panmove = 'LEFT'
        elif pan > 0.1:
            panmove = 'RIGHT'
        else:
            panmove = None

        if tilt < -0.1:
            tiltmove = 'UP'
        elif tilt > 0.1:
            tiltmove = 'DOWN'
        else:
            tiltmove = None

        if tiltmove and panmove:
            send_data(f'{tiltmove}-{panmove}', pan_speed, tilt_speed)
            stopped = False
            
        elif panmove:
            send_data(panmove, pan_speed, pan_speed)
            stopped = False
            
        elif tiltmove:
            send_data(tiltmove, tilt_speed, tilt_speed)
            stopped = False

        if buttons[9] == 1 and (buttons[9] != buttondebounce[0]):
            send_data('SET-PRESET', 0x00, 0x5F, command1=0x00) #BINGO! MENU!

        if buttons[3] == 1 and (buttons[3] != buttondebounce[0]):
            nv = not nv
            if nv:
                msb = (888 >> 8) & 0xFF
                lsb = 888 & 0xFF
                send_data('SET-PRESET', msb, lsb, command1=0x00)
            else:
                msb = (999 >> 8) & 0xFF
                lsb = 999 & 0xFF
                send_data('SET-PRESET', msb, lsb, command1=0x00) 


        if buttons[0] == 1 and (buttons[0] != buttondebounce[0]):
            setautofocus = not setautofocus
            print(setautofocus)
            s = 0x00 if setautofocus==True else 0x01
            send_data('AUTO-FOCUS', 0x00, s)

        buttondebounce = buttons

        if not stopped and not zoommove and not panmove and not tiltmove and not focusmove:
            send_data('STOP', 0x00, 0x00)
            stopped = True

        pandata = decode_pelco_d_response(send_data('QUERY-PAN', 0x00, 0x00))[1] / 100.0
        tiltdata = decode_pelco_d_response(send_data('QUERY-TILT', 0x00, 0x00))[1] / 100.0
        print(pandata,tiltdata)

        #time.sleep(0.1)

except KeyboardInterrupt:
    print("Exiting...")
finally:
    pygame.quit()
