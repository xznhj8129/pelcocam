# -*- coding: utf-8 -*-
#https://gist.github.com/jn0/cc5c78f4a0f447a6fb2e45a5d9efa13d

'''The Pelco-D Protocol

Standard Number                                                     TF-0002
Version         2       Revision    1       Release Date    August 15, 2003

Transmitters will format a single character and receivers will be able to
decipher a single character as: 1 start bit, 8 data bits, 1 stop bit,
and no parity.

Intended use:

    import serial
    import pelco_d

    CAM = 1

    with serial.Serial(PORT) as com:
        command, parser = pelco_d.get(pelco_d.CameraOn, CAM)
        com.write(command)
        response = com.read()
        print parser(response, command[-1])

THE MESSAGE FORMAT

The format for a message is:

Byte 1      Byte 2  Byte 3      Byte 4      Byte 5  Byte 6  Byte 7
Sync Byte   Address Command 1   Command 2   Data 1  Data 2  Checksum

Note that values in this document prefixed with “0x” are hexadecimal numbers.
The synchronization byte (Sync Byte) is always 0xFF.
The Address is the logical address of the receiver/driver device being controlled.
The Checksum is calculated by performing the 8 bit (modulo 256) sum of the
payload bytes (bytes 2 through 6) in the message.
'''

def get(proc, *args):
    command = proc(*args)
    parser = get_parser_for(proc)
    return command, parser


SYNC = 0xFF

"""
def command(*av):
    assert len(av) == 5, av
    assert len(filter(lambda x: x < 0 or x > 255, l)) == 0, av
    checksum = sum(av) & 255
    return bytearray((SYNC,) + tuple(av) + (checksum,))
"""

def command(*av):
    # Ensure exactly 5 arguments
    assert len(av) == 5, av

    # Ensure each argument is between 0 and 255 (inclusive)
    assert all(0 <= x <= 255 for x in av), av

    # Compute the checksum from the 5 arguments
    checksum = sum(av) & 0xFF

    # Return the 7-byte command: SYNC, 5 bytes, checksum
    return bytearray((SYNC,) + av + (checksum,))

__doc__ += '''
STANDARD COMMANDS

Command 1 and 2 are represented as follows:
          Bit 7 Bit 6   Bit 5   Bit 4   Bit 3   Bit 2   Bit 1   Bit 0
Command 1 Sense Rsrvd   Rsrvd   Auto/   Camera  Iris    Iris    Focus
                                Manual  On      Close   Open    Near
                                Scan    Off
Command 2 Focus Zoom    Zoom    Down    Up      Left    Righ    Always 0
          Far   Wide    Tele

A value of ‘1’ entered in the bit location for the function desired will enable
that function. A value of ‘0’ entered in the same bit location will disable or
‘stop’ the function.

The sense bit (command 1 bit 7) indicates the meaning of bits 4 and 3.
If the sense bit is on (value of ‘1’), and bits 4 and 3 are on,
the command will enable auto-scan and turn the camera on.
If the sense bit is off (value of ‘0’), and bits 4 and 3 are on the command
will enable manual scan and turn the camera off.
Of course, if either bit 4 or bit 3 are off then no action will be taken for
those features.

The reserved bits (6 and 5) should be set to 0.

Byte 5 contains the pan speed.
Pan speed is in the range of ‘0x00’ to ‘0x3F’ (high speed) and ‘0x40’ for “turbo” speed.
Turbo speed is the maximum speed the device can obtain and is considered
separately because it is not generally a smooth step from high speed to turbo.
That is, going from one speed to the next usually looks smooth and will provide
for smooth motion with the exception of going into and out of turbo speed. A pan
speed value of ‘0x00’ results in very slow motion, not cessation of motion.
To stop pan motion both the Left and Right direction bits must be turned off
– set to ‘0’ – regardless of the value set in the pan speed byte.

Byte 6 contains the tilt speed.
Tilt speed is in the range of ‘0x00’ to ‘0x3F’ (maximum speed).
Turbo speed is not allowed for the tilt axis.
A tilt speed value of ‘0x00’ results in very slow motion, not cessation of motion.
To stop tilt motion both the Down and Up direction bits must be turned off
– set to ‘0’ – regardless of the value set in the tilt speed byte.

Byte 7 is the checksum.
The checksum is the 8 bit (modulo 256) sum of the payload bytes (bytes 2 through
6) in the message.
'''

#         76543210
SENSE = 0b10000000
RSRV6 = 0b01000000
RSRV5 = 0b00100000
SCAN  = 0b00010000
CAMERA= 0b00001000
IRISCL= 0b00000100
IRISOP= 0b00000010
FOCUSN= 0b00000001

FOCUSF= 0b10000000
ZOOMWD= 0b01000000
ZOOMTL= 0b00100000
DOWN  = 0b00010000
UP    = 0b00001000
LEFT  = 0b00000100
RIGHT = 0b00000010
RSRV0 = 0b00000001

FAKE_PAN_SPEED = 0x1200
FAKE_TILT_SPEED = 0x0012

def Standard_Command(addr, cmd1, cmd2, data=0):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= cmd1 <= 255, cmd1
    assert cmd1 & (RSRV6 | RSRV5) == 0, cmd1
    assert 0 <= cmd2 <= 255, cmd2
    assert cmd2 & RSRV0 == 0, cmd2
    assert 0 <= data <= 65535, data1
    d1, d2 = (data >> 8) & 255, data & 255
    return command(addr, cmd1, cmd2, d1, d2)

def Camera_On(addr):
    'General Reponse'
    return Standard_Command(addr, SENSE|CAMERA, 0)
def Camera_Off(addr):
    'General Reponse'
    return Standard_Command(addr, CAMERA, 0)
def Camera(addr, on):
    'General Reponse'
    return Camera_On(addr) if on else Camera_Off(addr)

def Scan_Auto(addr):
    'General Reponse'
    return Standard_Command(addr, SENSE|SCAN, 0)
def Scan_Manual(addr):
    'General Reponse'
    return Standard_Command(addr, SCAN, 0)
def Scan(addr, auto):
    'General Reponse'
    return Scan_Auto(addr) if auto else Scan_Manual(addr)

def Iris_Close(addr):
    'General Reponse'
    return Standard_Command(addr, IRISCL, 0)
def Iris_Open(addr):
    'General Reponse'
    return Standard_Command(addr, IRISOP, 0)
def Iris(addr, open):
    'General Reponse'
    return Iris_Open(addr) if open else Iris_Close(addr)

def Focus_Near(addr):
    'General Reponse'
    return Standard_Command(addr, FOCUSN, 0)
def Focus_Far(addr):
    'General Reponse'
    return Standard_Command(addr, 0, FOCUSF)
def Focus(addr, far):
    'General Reponse'
    return Focus_Far(addr) if far else Focus_Near(addr)

def Zoom_Wide(addr):
    'General Reponse'
    return Standard_Command(addr, 0, ZOOMWD)
def Zoom_Tele(addr):
    'General Reponse'
    return Standard_Command(addr, 0, ZOOMTL)
def Zoom(addr, tele):
    'General Reponse'
    return Zoom_Tele(addr) if tele else Zoom_Wide(addr)

def Pan_Left(addr, speed):
    'General Response'
    assert 0 <= speed <= 0x40, speed
    return Standard_Command(addr, 0, LEFT, speed << 8)

def Pan_Right(addr, speed):
    'General Response'
    assert 0 <= speed <= 0x40, speed
    return Standard_Command(addr, 0, RIGHT, speed << 8)

def Pan_Stop(addr):
    'General Response'
    return Standard_Command(addr, 0, 0, FAKE_PAN_SPEED)

def Pan(addr, speed):
    'General Response'
    if not speed:
        return Pan_Stop(addr)
    elif speed > 0:
        return Pan_Right(addr, speed)
    else:
        return Pan_Left(addr, -speed)

def Tilt_Up(addr, speed):
    'General Response'
    assert 0 <= speed <= 0x3f, speed
    return Standard_Command(addr, 0, UP, speed)

def Tilt_Down(addr, speed):
    assert 0 <= speed <= 0x3f, speed
    return Standard_Command(addr, 0, DOWN, speed)

def Tilt_Stop(addr):
    'General Response'
    return Standard_Command(addr, 0, 0, FAKE_TILT_SPEED)

def Tilt(addr, speed):
    'General Response'
    if not speed:
        return Tilt_Stop(addr)
    elif speed > 0:
        return Tilt_Up(addr, speed)
    else:
        return Tilt_Down(addr, -speed)

__doc__ += '''
Set Preset (0x03)
Clear Preset (0x05)
Go To Preset (0x07)

The parameter in byte 6 of these commands is the ID of the preset to be acted on.
Valid preset IDs begin at 1.
Most devices support at least 32 presets.
Refer to the manual of the device under use for information about
what range of presets are valid for that equipment.
'''

AUTO, ON, OFF = 0, 1, 2

def Set_Preset(addr, presetId):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 1 <= presetId <= 255, presetId
    return command(addr, 0, 0x03, 0, presetId)

def Clear_Preset(addr, presetId):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 1 <= presetId <= 255, presetId
    return command(addr, 0, 0x05, 0, presetId)

def Go_To_Preset(addr, presetId):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 1 <= presetId <= 255, presetId
    return command(addr, 0, 0x07, 0, presetId)

def Flip_180_about(addr):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x07, 0, 0x21)

def Go_To_Zero_Pan(addr):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x07, 0, 0x22)

def Set_Auxiliary(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 1 <= value <= 8, value
    return command(addr, 0, 0x09, 0, value)

def Clear_Auxiliary(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 1 <= value <= 8, value
    return command(addr, 0, 0x0b, 0, value)

def Remote_Reset(addr):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x0f, 0, 0)

def Set_Zone_Start(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 1 <= value <= 8, value
    return command(addr, 0, 0x11, 0, value)

def Set_Zone_End(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 1 <= value <= 8, value
    return command(addr, 0, 0x13, 0, value)

__doc__ += '''
Write Character To Screen (0x15)
The parameter in byte 5 of this command indicates the column to write to.
This parameter is interpreted as follows:
- Columns 0-19 are used to receive zone labels.
- Columns 20-39 are used to receive preset labels.
'''

def Write_Character_to_Screen(addr, column, char):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= column <= 39, column
    assert 0 <= char <= 255, char
    return command(addr, 0, 0x15, column, char)

def Write_Zone_Label(addr, column, char):
    'General Response'
    assert 0 <= column <= 19, column
    return Write_Character_to_Screen(addr, column, char)

def Write_Preset_Lebel(addr, column, char):
    'General Response'
    assert 0 <= column <= 19, column
    return Write_Character_to_Screen(addr, 20 + column, char)


def Clear_Screen(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x17, 0, 0)

def Alarm_Acknowledge(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 1 <= value <= 8, value
    return command(addr, 0, 0x19, 0, value)

def Zone_Scan_On(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x1b, 0, 0)

def Zone_Scan_Off(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x1d, 0, 0)

__doc__ += '''
Set Pattern Start (0x1F)
Run Pattern (0x23)

The parameter in byte 6 of these commands indicates the pattern to be set/run.

Platform dependent.
'''

def Set_Pattern_Start(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 255, value
    return command(addr, 0, 0x1f, 0, value)

def Set_Pattern_Stop(addr):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x21, 0, 0)

def Run_Pattern(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 255, value
    return command(addr, 0, 0x23, 0, value)

def Set_Zoom_Speed(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 3, value
    return command(addr, 0, 0x25, 0, value)

def Set_Focus_Speed(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 3, value
    return command(addr, 0, 0x27, 0, value)

def Reset_Camera_to_defaults(addr):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x29, 0, 0)

def Auto_focus(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert value in (AUTO, ON, OFF), value
    return command(addr, 0, 0x2b, 0, value)

def Auto_Iris(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert value in (AUTO, ON, OFF), value
    return command(addr, 0, 0x2d, 0, value)

def AGC(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert value in (AUTO, ON, OFF), value
    return command(addr, 0, 0x2f, 0, value)

def Backlight_compensation(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert value in (ON, OFF), value
    return command(addr, 0, 0x31, 0, value)

def Auto_white_balance(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert value in (ON, OFF), value
    return command(addr, 0, 0x33, 0, value)

def Enable_device_phase_delay_mode(addr):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x35, 0, 0)

def Set_shutter_speed(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x37, d1, d2)

def Adjust_line_lock_phase_delay_0(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x39, d1, d2)

def Adjust_line_lock_phase_delay_1(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 1, 0x39, d1, d2)

def Adjust_white_balance_RB0(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x3b, d1, d2)

def Adjust_white_balance_RB1(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 1, 0x3b, d1, d2)

def Adjust_white_balance_MG0(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x3d, d1, d2)

def Adjust_white_balance_MG1(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 1, 0x3d, d1, d2)

def Adjust_gain_0(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x3f, d1, d2)

def Adjust_gain_1(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 1, 0x3f, d1, d2)

def Adjust_auto_iris_level_0(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x41, d1, d2)

def Adjust_auto_iris_level_1(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 1, 0x41, d1, d2)

def Adjust_auto_iris_peak_0(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x43, d1, d2)

def Adjust_auto_iris_peak_1(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 1, 0x43, d1, d2)

def Query(addr, value):
    '''This command can only be used in a point to point application.
    A device being queried will respond to any address.
    If more than one device hears this command,
    multiple devices will transmit at the same time.

    Query45 Response'''

    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x45, d1, d2)

def Reserved_Opcode(addr, value):
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 255, addr
    return command(addr, 0, value, 0, 0)

def Reserved_Opcode_47(addr): return Reserved_Opcode(addr, 0x47)

__doc__ += '''
Set Zero Position (0x49)

This command is used to set the pan position that the unit uses as a zero
reference point for the azimuth on-screen display.
The unit’s current pan position when this command is received becomes the zero
reference point.
This command performs the same function as the “Set Azimuth Zero” menu item.
'''

def Set_Zero_Position(addr):
    'General Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x49, 0, 0)

__doc__ += '''
Set Pan Position (0x4B)

This command is used to set the pan position of the device.
The position is given in hundredths of a degree and has a range from 0 to 35999
(decimal).
Example: the value to use to set the pan position to 45 degrees is 4500.

Note that the value used here is always the “absolute” pan position.
It does not take into account any adjustment to the screen display that may
have been made by using the “Set Zero Position”, opcode (0x49) command or
the “Set Azimuth Zero” menu item.
'''

def Set_Pan_Position(addr, degrees):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= degrees <= 35999, degrees
    d1, d2 = (degrees >> 8) & 255, degrees & 255
    return command(addr, 0, 0x4b, d1, d2)

__doc__ += '''
Set Tilt Position (0x4D)

This command is used to set the tilt position of the device.
The position is given in hundredths of a degree and has a range from 0 to 35999
(decimal). Generally these values are interpreted as follows:
- Zero degrees indicates that the device is pointed horizontally (at the horizon).
- Ninety degrees indicates that the device is pointed straight down.
Examples:
1) the value used to set the tilt position to 45 degrees below the horizon, is 4500.
2) the value used to set the tilt position 30 degrees above the horizon, is 33000.

Note that different equipment will have different ranges of motion.
To determine the abilities of a specific piece of equipment,
refer to that device’s operation manual.
'''

TILT_NONE = TITL_HORIZON = 0
TILT_DOWN = 9000
TILT_UP = 27000

def Set_Tilt_Position(addr, degrees):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= degrees <= 35999, degrees
    d1, d2 = (degrees >> 8) & 255, degrees & 255
    return command(addr, 0, 0x4d, d1, d2)

__doc__ += '''
Set Zoom Position (0x4F)

This command is used to set the zoom position of the device.
The position is given as a ratio based on the device’s Zoom Limit setting.
The position is calculated as follows:

    Position = (desired_zoom_position / zoom_limit) * 65535

Where desired_zoom_position and zoom_limit are given in units of magnification.

Example:
    Given that the zoom limit of the device’s camera is X184,
    calculate the value needed to set the zoom position to X5:

    Position = (5 / 184) * 65535 = approximately 1781
'''

def Set_Zoom_Position(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x4f, d1, d2)

__doc__ += '''
Query Pan Position (0x51)

This command is used to query the current pan position of the device.
The response to this command uses opcode 0x59.
See the description of opcode 0x59 for more information.
'''

def Query_Pan_Position(addr):
    'Extended Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x51, 0, 0)

__doc__ += '''
Query Tilt Position (0x53)

This command is used to query the current tilt position of the device.
The response to this command uses opcode 0x5B.
See the description of opcode 0x5B for more information.
'''

def Query_Tilt_Position(addr):
    'Extended Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x53, 0, 0)

__doc__ += '''
Query Zoom Position (0x55)

This command is used to query the current zoom position of the device.
The response to this command uses opcode 0x5D.
See the description of opcode 0x5D for more information.
'''

def Query_Zoom_Position(addr):
    'Extended Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x55, 0, 0)

def Reserved_Opcode_57(addr): return Reserved_Opcode(addr, 0x57)

__doc__ += '''
Query Pan Position Response (0x59)

The position is given in hundredths of a degree and has a range from 0 to 35999 (decimal).

Example: a position value of 4500 indicates 45 degrees.

Note that the value returned is always the “absolute” pan position.
It does not take into account any adjustment to the screen display that may
have been made by using the “Set Zero Position”, opcode (0x49) command or
the “Set Azimuth Zero” menu item.
'''

def Query_Pan_Response(addr, value):
    'Extended Response' # ??? XXX
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x59, d1, d2)

__doc__ += '''
Query Tilt Position Response (0x5B)

The position is given in hundredths of a degree and has a range from 0 to 35999 (decimal).
Refer to examples listed in description of the “Set Tilt Position”, opcode 0x4D command.
'''

def Query_Tilt_Response(addr, value):
    'Extended Response' # ??? XXX
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x5b, d1, d2)

__doc__ += '''
Query Zoom Position Response (0x5D)

The position is given as a ratio based on the device’s Zoom Limit setting.
This value can be converted into units of magnification by using the following formula:

    current_magnification = (position / 65535) * zoom_limit

Where current_zoom_position and zoom_limit are given in units of magnification.

Example:
    Given that the zoom limit of the device’s camera is X184,
    position value is 1781, calculate the current magnification:

    Current magnification = (1781 / 65535) * 184 = approximately X5.

Note: This message is sent in response to the Query Zoom Position (0x55) command.
'''

def Query_Zoom_Response(addr, value):
    'Extended Response' # ??? XXX
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x5d, d1, d2)

__doc__ += '''
Set Magnification (0x5F)

This command is used to set the zoom position of the device.
The position is given in hundredths of units of magnification.
Example: a value of 500 means X5.
'''

def Set_Magnification(addr, value):
    'General Response'
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x5f, d1, d2)

__doc__ += '''
Query Magnification (0x61)

This command is used to query the current zoom position of the device.
The response to this command uses opcode 0x63.
See the description of opcode 0x63 for more information.
'''

def Query_Magnification(addr):
    'Extended Response'
    assert 0 <= addr <= 255, addr
    return command(addr, 0, 0x61, 0, 0)

__doc__ += '''
Query Magnification Response (0x63)

The value returned is given in hundredths of units of magnification.
Example: a value of 500 means X5.
'''

def Query_Magnification_Response(addr, value):
    assert 0 <= addr <= 255, addr
    assert 0 <= value <= 65535, value
    d1, d2 = (value >> 8) & 255, value & 255
    return command(addr, 0, 0x63, d1, d2)

def Reserved_Opcode_65(addr): return Reserved_Opcode(addr, 0x65)
def Reserved_Opcode_67(addr): return Reserved_Opcode(addr, 0x67)
def Reserved_Opcode_69(addr): return Reserved_Opcode(addr, 0x69)
def Reserved_Opcode_6b(addr): return Reserved_Opcode(addr, 0x6b)
def Reserved_Opcode_6d(addr): return Reserved_Opcode(addr, 0x6d)
def Reserved_Opcode_6f(addr): return Reserved_Opcode(addr, 0x6f)
def Reserved_Opcode_71(addr): return Reserved_Opcode(addr, 0x71)

__doc__ += '''
The General Response

The General Response has the following format.
Note that each block represents 1 byte.

Byte 1 Byte 2   Byte 3              Byte 4
Sync   Address  Alarm Information   Checksum

The alarm information is formatted as follows:
Bit 7   Bit 6   Bit 5   Bit 4   Bit 3   Bit 2   Bit 1   Bit 0
None    Alarm 7 Alarm 6 Alarm 5 Alarm 4 Alarm 3 Alarm 2 Alarm 1

If the bit is on (1) then the alarm is active. If the bit is off (0)
then the alarm is inactive.
The checksum is the sum of the transmitted command’s checksum and the alarm
information.
'''

#          76543210
ALARM1 = 0b00000001
ALARM2 = 0b00000010
ALARM3 = 0b00000100
ALARM4 = 0b00001000
ALARM5 = 0b00010000
ALARM6 = 0b00100000
ALARM7 = 0b01000000
ALARMX = 0b10000000

def Parse_General_Response(resp, sent_cs=None):
    assert len(resp) == 4, resp
    assert resp[0] == SYNC, resp
    addr = resp[1]
    info = resp[2] & ~ALARMX
    assert 0 <= info <= 127, info
    if sent_cs is not None:
        assert 0 <= sent_cs <= 255, sent_cs
        csum = resp[3]
        assert csum == ((sent_cs + info) & 255), resp
    res = set()
    if info & ALARM1: res.add(ALARM1)
    if info & ALARM2: res.add(ALARM2)
    if info & ALARM3: res.add(ALARM3)
    if info & ALARM4: res.add(ALARM4)
    if info & ALARM5: res.add(ALARM5)
    if info & ALARM6: res.add(ALARM6)
    if info & ALARM7: res.add(ALARM7)
    return addr, res

__doc__ += '''
The Query (0x45) Response

The response to the Query command is:
Byte 1          Byte 2              Bytes 3 to 17           Byte 18
Sync (1 byte)   Address (1 byte)    Part Number (15 bytes)  Checksum (1 byte)

The address is the address of the device responding to the query.
The content of the part number field is dependent on the type and version of
the device being programmed, please refer to the table that follows.
The checksum is the 8 bit (modulo 256) sum of the transmitted query command’s
checksum, the address of the response, and the 15-byte part number.
'''

def Parse_Query45_Response(resp, sent_cs=None):
    assert len(resp) == 18, resp
    assert resp[0] == SYNC, resp
    addr = resp[1]
    pnum = resp[2:-1]
    if sent_cs is not None:
        assert 0 <= sent_cs <= 255, sent_cs
        csum = resp[-1]
        xsum = sum(pnum) & 255
        assert csum == ((sent_cs + addr + xsum) & 255), resp
    return addr, str(pnum)

__doc__ += '''
The Extended Response

The Extended Response has the following format.
Note that each block represents 1 byte

Byte 1  Byte 2  Byte 3      Byte 4      Byte 5  Byte 6  Byte 7
Sync    Address Future Use  “opcode”    Data1   Data2   Checksum

The address is the address of the device that is responding.
The Future Use byte should always be set to 0.
Opcode, Data1 and Data2 are dependent on the type of response.
See the opcode description section of this document for the details of a particular response.

The checksum is the 8 bit (modulo 256) sum of all the bytes excluding the Sync byte.
'''

def Parse_Extended_Response(resp, _=None, _op=None):
    assert len(resp) == 7, resp
    assert resp[0] == SYNC, resp
    addr = resp[1]
    rezerved = resp[2]
    assert rezerved == 0, resp
    opcode = resp[3]
    if _op is not None:
        assert opcode == _op, resp
    data1 = resp[4]
    data2 = resp[5]
    csum = resp[-1]
    xsum = sum(resp[1:-1]) & 255
    assert csum == xsum, resp
    return addr, (opcode, data1, data2)

def get_parser_for(func):
    docstr = func.__doc__.strip()
    if 'Response' in docstr:
        for l in docstr.splitlines():
            if l.endswith('Response'):
                if ',' in l:
                    l, op = l.split(',', 1) # `op` is unused now
                parser_name = 'Parse_' + '_'.join(l.split())
                if parser_name in globals():
                    return globals()[parser_name]

# vim: ai et ts=4 sts=4 sw=4 ft=python