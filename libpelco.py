import serial
import sys
from functools import reduce

def angle_to_bytes(angle):
    if not 0 <= angle <= 360:
        raise ValueError("Angle must be between 0 and 360 degrees inclusive.")

    centidegrees = int(angle * 100)
    msb = (centidegrees >> 8) & 0xFF
    lsb = centidegrees & 0xFF

    return msb, lsb

pelcod_frame = {
    'synch_byte': b'\xFF',
    'address': b'\x00',
    'command1': b'\x00',
    'command2': b'\x00',
    'data1': b'\x00',
    'data2': b'\x00',
    'checksum': b'\x00'
}

pelcod_function_code = {
    'DOWN':             b'\x10',
    'UP':               b'\x08',    
    'LEFT':             b'\x04',
    'RIGHT':            b'\x02',
    'UP-RIGHT':         b'\x0A',
    'DOWN-RIGHT':       b'\x12',
    'UP-LEFT':          b'\x0C',
    'DOWN-LEFT':        b'\x14',
    'STOP':             b'\x00',
    'ZOOM-IN':          b'\x20',
    'ZOOM-OUT':         b'\x40',
    'FOCUS-FAR':        b'\x80',
    'FOCUS-NEAR':       b'\x81',
    'SET-PRESET':       b'\x03',
    'CLEAR-PRESET':     b'\x05',
    'CALL-PRESET':      b'\x07',
    'QUERY-PAN':        b'\x51',
    'QUERY-TILT':       b'\x53',
    'QUERY-ZOOM':       b'\x55',
    'SET-PAN':          b'\x4B',
    'SET-TILT':         b'\x4D',
    'SET-ZOOM':         b'\x4F',
    'SET-FOCUS':        b'\x5F',
    'AUTO-FOCUS':       b'\x2B',
    'CLEAR-PRESET':     b'\x05',
    'OK':               b'\xA7',
    'ECHO-MODE':        b'\x65',
    'QUERY-DIAG':       b'\x6F',
    'TEST':             b'\x00',
}

pelcod_response_type = {
    89: 'QUERY-PAN', #0x59
    91: 'QUERY-TILT' #0x5B

}

def decode_pelco_d_response(response: bytes) -> dict:
    """
    Packet layout:
        Byte 0: 0xFF (start byte)
        Byte 1: Address (e.g., 0x01)
        Byte 2: 0x00 (command1)
        Byte 3: Response type (0x59 -> query-pan, 0x5B -> query-tilt)
        Byte 4: MSB
        Byte 5: LSB
        Byte 6: Checksum
    """
    if len(response) != 7:
        raise ValueError(f"Invalid response length: expected 7, got {len(response)}")

    # 1) Check start byte
    if response[0] != 0xFF:
        return None

    # 2) Extract fields
    address       = response[1]
    command1      = response[2]
    qwert = response[3]
    response_type = pelcod_response_type[qwert & 0xFF]
    msb           = response[4]
    lsb           = response[5]
    checksum_rx   = response[6]

    # Optional: You can validate address or command1 if you expect them fixed
    #if command1 != 0x00:
    #    raise ValueError(f"Unexpected command1 byte: 0x{command1:02X}")

    # 3) Check the response type

    # 4) Verify checksum
    # The checksum is the low 8 bits of the sum of bytes 1..5 (i.e. address + command1 + response_type + msb + lsb).
    payload_sum = (address + command1 + qwert + msb + lsb) & 0xFF
    if payload_sum != checksum_rx:
        return None

    # 5) Decode angle (reverse of angle_to_bytes)
    val = (msb << 8) | lsb
    #angle = centidegrees / 100.0
    return (response_type,val)

class PelcoFunctions:
    def __init__(self):
        self.function_code = pelcod_function_code

    def _construct_cmd(self, _command2, _data1, _data2, _address=b'\x01', _command1=b'\x00'):
        # DEBUG
        #print(f"DEBUG _construct_cmd: {_command2} {_data1} {_data2}\n")
        self.frame = pelcod_frame

        # Sync Byte
        self.frame['synch_byte'] = self.frame['synch_byte']

        # Address
        self.frame['address'] = _address

        # Command1
        self.frame['command1'] = _command1

        # Command2
        if _command2 not in self.function_code:
            #print(f"{_command2} not in commands_struct._function_code\n")
            return False
        else:
            self.frame['command2'] = self.function_code[_command2]
            #print(f"_command2 is: {self.frame['command2'].hex()}\n")

        # Data1: Pan Speed
        #print(f"_data1 is: {_data1}\n")
        _hex_data1 = f"{_data1:02x}"
        self.frame['data1'] = bytes.fromhex(_hex_data1)

        # Data2: Tilt Speed
        #print(f"_data2 is: {_data2}\n")
        _hex_data2 = f"{_data2:02x}"
        self.frame['data2'] = bytes.fromhex(_hex_data2)

        # Checksum
        _payload_bytes = self.frame['address'] + self.frame['command1'] + \
                         self.frame['command2'] + \
                         self.frame['data1'] + self.frame['data2']

        _checksum = f"{self.checksum256(_payload_bytes):02x}"
        self.frame['checksum'] = bytes.fromhex(_checksum)

        #print(f"_checksum is: {self.frame['checksum'].hex()}\n")

        # Assemble command
        _cmd = self.frame['synch_byte'] + _payload_bytes + self.frame['checksum']

        #print("Final _cmd: \n")
        #for key, value in self.frame.items():
        #    print(f"{key} : {value.hex()}")
        #print("\n")

        return _cmd

    def checksum256(self, data):
        return sum(data) % 256


# Example usage
if __name__ == "__main__":
    pelco = PelcoFunctions()
    cmd, _ = pelco._construct_cmd('QUERY-PAN', 0x00, 0x00)
    print(f"Constructed Command: {cmd.hex()}")

