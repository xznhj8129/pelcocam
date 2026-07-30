"""Pelco-D framing, commands, response decoding, and serial transport."""

from dataclasses import dataclass
from enum import IntEnum, IntFlag
import time

import serial


SYNC = 0xFF
FRAME_LENGTH = 7
MAX_PAN_SPEED = 0x3F
MAX_TILT_SPEED = 0x3F


class Command1(IntFlag):
    FOCUS_NEAR = 0x01
    IRIS_OPEN = 0x02
    IRIS_CLOSE = 0x04
    CAMERA = 0x08
    AUTO_SCAN = 0x10
    SENSE = 0x80


class Command2(IntFlag):
    RIGHT = 0x02
    LEFT = 0x04
    UP = 0x08
    DOWN = 0x10
    ZOOM_TELE = 0x20
    ZOOM_WIDE = 0x40
    FOCUS_FAR = 0x80


class Opcode(IntEnum):
    SET_PRESET = 0x03
    CLEAR_PRESET = 0x05
    GOTO_PRESET = 0x07
    SET_AUXILIARY = 0x09
    CLEAR_AUXILIARY = 0x0B
    REMOTE_RESET = 0x0F
    SET_ZONE_START = 0x11
    SET_ZONE_END = 0x13
    WRITE_CHARACTER = 0x15
    CLEAR_SCREEN = 0x17
    ALARM_ACKNOWLEDGE = 0x19
    ZONE_SCAN_ON = 0x1B
    ZONE_SCAN_OFF = 0x1D
    SET_PATTERN_START = 0x1F
    SET_PATTERN_STOP = 0x21
    RUN_PATTERN = 0x23
    SET_ZOOM_SPEED = 0x25
    SET_FOCUS_SPEED = 0x27
    RESET_CAMERA = 0x29
    AUTO_FOCUS = 0x2B
    AUTO_IRIS = 0x2D
    AUTO_GAIN_CONTROL = 0x2F
    BACKLIGHT_COMPENSATION = 0x31
    AUTO_WHITE_BALANCE = 0x33
    ENABLE_PHASE_DELAY_MODE = 0x35
    SET_SHUTTER_SPEED = 0x37
    ADJUST_LINE_LOCK_PHASE_DELAY = 0x39
    ADJUST_WHITE_BALANCE_RB = 0x3B
    ADJUST_WHITE_BALANCE_MG = 0x3D
    ADJUST_GAIN = 0x3F
    ADJUST_AUTO_IRIS_LEVEL = 0x41
    ADJUST_AUTO_IRIS_PEAK = 0x43
    QUERY_DEVICE = 0x45
    RESERVED_47 = 0x47
    SET_ZERO_POSITION = 0x49
    SET_PAN_POSITION = 0x4B
    SET_TILT_POSITION = 0x4D
    SET_ZOOM_POSITION = 0x4F
    QUERY_PAN_POSITION = 0x51
    QUERY_TILT_POSITION = 0x53
    QUERY_ZOOM_POSITION = 0x55
    RESERVED_57 = 0x57
    PAN_POSITION_RESPONSE = 0x59
    TILT_POSITION_RESPONSE = 0x5B
    ZOOM_POSITION_RESPONSE = 0x5D
    SET_MAGNIFICATION = 0x5F
    SET_FOCUS_POSITION = 0x5F
    QUERY_MAGNIFICATION = 0x61
    QUERY_FOCUS_POSITION = 0x61
    MAGNIFICATION_RESPONSE = 0x63
    FOCUS_POSITION_RESPONSE = 0x63
    RESERVED_65 = 0x65
    ECHO_MODE = 0x65
    RESERVED_67 = 0x67
    RESERVED_69 = 0x69
    RESERVED_6B = 0x6B
    RESERVED_6D = 0x6D
    RESERVED_6F = 0x6F
    QUERY_DIAGNOSTICS = 0x6F
    RESERVED_71 = 0x71


class AutoMode(IntEnum):
    AUTO = 0
    ON = 1
    OFF = 2


class SwitchMode(IntEnum):
    ON = 1
    OFF = 2


POSITION_RESPONSES = {
    Opcode.PAN_POSITION_RESPONSE: ("pan_deg", 0.01),
    Opcode.TILT_POSITION_RESPONSE: ("tilt_deg", 0.01),
    Opcode.ZOOM_POSITION_RESPONSE: ("zoom_position", 1),
}

ALARM_COUNT = 7
GENERAL_RESPONSE_LENGTH = 4
DEVICE_QUERY_RESPONSE_LENGTH = 18


class PelcoTimeoutError(TimeoutError):
    pass


@dataclass(frozen=True)
class Frame:
    address: int
    command1: int
    command2: int
    data1: int
    data2: int

    def __post_init__(self) -> None:
        for name in ("address", "command1", "command2", "data1", "data2"):
            value = getattr(self, name)
            if not 0 <= value <= 0xFF:
                raise ValueError(f"{name}={value} expected=0..255")

    @property
    def value(self) -> int:
        return self.data1 << 8 | self.data2

    def to_bytes(self) -> bytes:
        payload = bytes(
            (
                self.address,
                self.command1,
                self.command2,
                self.data1,
                self.data2,
            )
        )
        return bytes((SYNC,)) + payload + bytes((sum(payload) & 0xFF,))

    @classmethod
    def from_bytes(cls, packet: bytes):
        if len(packet) != FRAME_LENGTH:
            raise ValueError(
                f"frame_length={len(packet)} expected={FRAME_LENGTH}"
            )
        if packet[0] != SYNC:
            raise ValueError(f"frame_sync=0x{packet[0]:02x} expected=0xff")
        calculated_checksum = sum(packet[1:6]) & 0xFF
        if packet[6] != calculated_checksum:
            raise ValueError(
                f"frame_checksum=0x{packet[6]:02x} "
                f"expected=0x{calculated_checksum:02x}"
            )
        return cls(*packet[1:6])


@dataclass(frozen=True)
class GeneralResponse:
    address: int
    active_alarms: frozenset[int]


@dataclass(frozen=True)
class DeviceQueryResponse:
    address: int
    part_number: bytes


def make_frame(
    address: int,
    command2: int,
    data1: int = 0,
    data2: int = 0,
    command1: int = 0,
) -> Frame:
    return Frame(address, command1, command2, data1, data2)


def stop(address: int) -> Frame:
    return make_frame(address, 0)


def standard_command(
    address: int,
    command1: int = 0,
    command2: int = 0,
    data: int = 0,
) -> Frame:
    if not 0 <= data <= 0xFFFF:
        raise ValueError(f"data={data} expected=0..65535")
    return make_frame(
        address,
        command2,
        data >> 8,
        data & 0xFF,
        command1,
    )


def standard_control(
    address: int,
    pan: float = 0.0,
    tilt: float = 0.0,
    zoom: int = 0,
    focus: int = 0,
    iris: int = 0,
    deadband: float = 0.05,
) -> Frame:
    pan = max(-1.0, min(1.0, float(pan)))
    tilt = max(-1.0, min(1.0, float(tilt)))
    command1 = 0
    command2 = 0

    if pan < -deadband:
        command2 |= Command2.LEFT
    elif pan > deadband:
        command2 |= Command2.RIGHT

    if tilt < -deadband:
        command2 |= Command2.UP
    elif tilt > deadband:
        command2 |= Command2.DOWN

    if zoom < 0:
        command2 |= Command2.ZOOM_WIDE
    elif zoom > 0:
        command2 |= Command2.ZOOM_TELE

    if focus < 0:
        command1 |= Command1.FOCUS_NEAR
    elif focus > 0:
        command2 |= Command2.FOCUS_FAR

    if iris < 0:
        command1 |= Command1.IRIS_CLOSE
    elif iris > 0:
        command1 |= Command1.IRIS_OPEN

    pan_speed = (
        round(abs(pan) * MAX_PAN_SPEED)
        if command2 & (Command2.LEFT | Command2.RIGHT)
        else 0
    )
    tilt_speed = (
        round(abs(tilt) * MAX_TILT_SPEED)
        if command2 & (Command2.UP | Command2.DOWN)
        else 0
    )
    return make_frame(
        address,
        command2,
        pan_speed,
        tilt_speed,
        command1,
    )


def camera_on(address: int) -> Frame:
    return standard_command(
        address,
        command1=Command1.SENSE | Command1.CAMERA,
    )


def camera_off(address: int) -> Frame:
    return standard_command(address, command1=Command1.CAMERA)


def set_auto_scan(address: int, enabled: bool) -> Frame:
    command1 = Command1.AUTO_SCAN
    if enabled:
        command1 |= Command1.SENSE
    return standard_command(address, command1=command1)


def iris_open(address: int) -> Frame:
    return standard_command(address, command1=Command1.IRIS_OPEN)


def iris_close(address: int) -> Frame:
    return standard_command(address, command1=Command1.IRIS_CLOSE)


def focus_near(address: int) -> Frame:
    return standard_command(address, command1=Command1.FOCUS_NEAR)


def focus_far(address: int) -> Frame:
    return standard_command(address, command2=Command2.FOCUS_FAR)


def zoom_wide(address: int) -> Frame:
    return standard_command(address, command2=Command2.ZOOM_WIDE)


def zoom_tele(address: int) -> Frame:
    return standard_command(address, command2=Command2.ZOOM_TELE)


def pan_left(address: int, speed: int) -> Frame:
    if not 0 <= speed <= 0x40:
        raise ValueError(f"pan_speed={speed} expected=0..64")
    return standard_command(
        address,
        command2=Command2.LEFT,
        data=speed << 8,
    )


def pan_right(address: int, speed: int) -> Frame:
    if not 0 <= speed <= 0x40:
        raise ValueError(f"pan_speed={speed} expected=0..64")
    return standard_command(
        address,
        command2=Command2.RIGHT,
        data=speed << 8,
    )


def pan(address: int, speed: int) -> Frame:
    if speed < 0:
        return pan_left(address, -speed)
    if speed > 0:
        return pan_right(address, speed)
    return stop(address)


def tilt_up(address: int, speed: int) -> Frame:
    if not 0 <= speed <= MAX_TILT_SPEED:
        raise ValueError(f"tilt_speed={speed} expected=0..63")
    return standard_command(address, command2=Command2.UP, data=speed)


def tilt_down(address: int, speed: int) -> Frame:
    if not 0 <= speed <= MAX_TILT_SPEED:
        raise ValueError(f"tilt_speed={speed} expected=0..63")
    return standard_command(address, command2=Command2.DOWN, data=speed)


def tilt(address: int, speed: int) -> Frame:
    if speed < 0:
        return tilt_down(address, -speed)
    if speed > 0:
        return tilt_up(address, speed)
    return stop(address)


def _opcode_value_frame(
    address: int,
    opcode: Opcode,
    value: int = 0,
    command1: int = 0,
) -> Frame:
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"value={value} expected=0..65535")
    return make_frame(
        address,
        opcode,
        value >> 8,
        value & 0xFF,
        command1,
    )


def _opcode_data2_frame(
    address: int,
    opcode: Opcode,
    value: int = 0,
) -> Frame:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"value={value} expected=0..255")
    return make_frame(address, opcode, 0, value)


def set_preset(address: int, preset: int) -> Frame:
    if not 1 <= preset <= 0xFF:
        raise ValueError(f"preset={preset} expected=1..255")
    return _opcode_data2_frame(address, Opcode.SET_PRESET, preset)


def set_extended_preset(address: int, value: int) -> Frame:
    """Send a device-specific 16-bit value with the SET PRESET opcode."""
    return _opcode_value_frame(address, Opcode.SET_PRESET, value)


def clear_preset(address: int, preset: int) -> Frame:
    if not 1 <= preset <= 0xFF:
        raise ValueError(f"preset={preset} expected=1..255")
    return _opcode_data2_frame(address, Opcode.CLEAR_PRESET, preset)


def goto_preset(address: int, preset: int) -> Frame:
    if not 1 <= preset <= 0xFF:
        raise ValueError(f"preset={preset} expected=1..255")
    return _opcode_data2_frame(address, Opcode.GOTO_PRESET, preset)


def flip_180(address: int) -> Frame:
    return _opcode_data2_frame(address, Opcode.GOTO_PRESET, 0x21)


def goto_zero_pan(address: int) -> Frame:
    return _opcode_data2_frame(address, Opcode.GOTO_PRESET, 0x22)


def set_auxiliary(address: int, auxiliary: int) -> Frame:
    if not 1 <= auxiliary <= 8:
        raise ValueError(f"auxiliary={auxiliary} expected=1..8")
    return _opcode_data2_frame(address, Opcode.SET_AUXILIARY, auxiliary)


def clear_auxiliary(address: int, auxiliary: int) -> Frame:
    if not 1 <= auxiliary <= 8:
        raise ValueError(f"auxiliary={auxiliary} expected=1..8")
    return _opcode_data2_frame(address, Opcode.CLEAR_AUXILIARY, auxiliary)


def remote_reset(address: int) -> Frame:
    return make_frame(address, Opcode.REMOTE_RESET)


def set_zone_start(address: int, zone: int) -> Frame:
    if not 1 <= zone <= 8:
        raise ValueError(f"zone={zone} expected=1..8")
    return _opcode_data2_frame(address, Opcode.SET_ZONE_START, zone)


def set_zone_end(address: int, zone: int) -> Frame:
    if not 1 <= zone <= 8:
        raise ValueError(f"zone={zone} expected=1..8")
    return _opcode_data2_frame(address, Opcode.SET_ZONE_END, zone)


def write_character(address: int, column: int, character: int) -> Frame:
    if not 0 <= column <= 39:
        raise ValueError(f"column={column} expected=0..39")
    if not 0 <= character <= 0xFF:
        raise ValueError(f"character={character} expected=0..255")
    return make_frame(address, Opcode.WRITE_CHARACTER, column, character)


def write_zone_label(address: int, column: int, character: int) -> Frame:
    if not 0 <= column <= 19:
        raise ValueError(f"zone_column={column} expected=0..19")
    return write_character(address, column, character)


def write_preset_label(address: int, column: int, character: int) -> Frame:
    if not 0 <= column <= 19:
        raise ValueError(f"preset_column={column} expected=0..19")
    return write_character(address, 20 + column, character)


def clear_screen(address: int) -> Frame:
    return make_frame(address, Opcode.CLEAR_SCREEN)


def acknowledge_alarm(address: int, alarm: int) -> Frame:
    if not 1 <= alarm <= 8:
        raise ValueError(f"alarm={alarm} expected=1..8")
    return _opcode_data2_frame(address, Opcode.ALARM_ACKNOWLEDGE, alarm)


def set_zone_scan(address: int, enabled: bool) -> Frame:
    opcode = Opcode.ZONE_SCAN_ON if enabled else Opcode.ZONE_SCAN_OFF
    return make_frame(address, opcode)


def set_pattern_start(address: int, pattern: int) -> Frame:
    return _opcode_data2_frame(address, Opcode.SET_PATTERN_START, pattern)


def set_pattern_stop(address: int) -> Frame:
    return make_frame(address, Opcode.SET_PATTERN_STOP)


def run_pattern(address: int, pattern: int) -> Frame:
    return _opcode_data2_frame(address, Opcode.RUN_PATTERN, pattern)


def set_zoom_speed(address: int, speed: int) -> Frame:
    if not 0 <= speed <= 3:
        raise ValueError(f"zoom_speed={speed} expected=0..3")
    return _opcode_data2_frame(address, Opcode.SET_ZOOM_SPEED, speed)


def set_focus_speed(address: int, speed: int) -> Frame:
    if not 0 <= speed <= 3:
        raise ValueError(f"focus_speed={speed} expected=0..3")
    return _opcode_data2_frame(address, Opcode.SET_FOCUS_SPEED, speed)


def reset_camera(address: int) -> Frame:
    return make_frame(address, Opcode.RESET_CAMERA)


def set_focus_mode(address: int, mode: AutoMode) -> Frame:
    return _opcode_data2_frame(address, Opcode.AUTO_FOCUS, AutoMode(mode))


def set_auto_focus(address: int, enabled: bool) -> Frame:
    return set_focus_mode(
        address,
        AutoMode.AUTO if enabled else AutoMode.OFF,
    )


def set_iris_mode(address: int, mode: AutoMode) -> Frame:
    return _opcode_data2_frame(address, Opcode.AUTO_IRIS, AutoMode(mode))


def set_auto_iris(address: int, enabled: bool) -> Frame:
    return set_iris_mode(
        address,
        AutoMode.AUTO if enabled else AutoMode.OFF,
    )


def set_gain_control_mode(address: int, mode: AutoMode) -> Frame:
    return _opcode_data2_frame(
        address,
        Opcode.AUTO_GAIN_CONTROL,
        AutoMode(mode),
    )


def set_backlight_compensation(
    address: int,
    mode: SwitchMode,
) -> Frame:
    return _opcode_data2_frame(
        address,
        Opcode.BACKLIGHT_COMPENSATION,
        SwitchMode(mode),
    )


def set_auto_white_balance(address: int, mode: SwitchMode) -> Frame:
    return _opcode_data2_frame(
        address,
        Opcode.AUTO_WHITE_BALANCE,
        SwitchMode(mode),
    )


def enable_phase_delay_mode(address: int) -> Frame:
    return make_frame(address, Opcode.ENABLE_PHASE_DELAY_MODE)


def set_shutter_speed(address: int, value: int) -> Frame:
    return _opcode_value_frame(address, Opcode.SET_SHUTTER_SPEED, value)


def adjust_line_lock_phase_delay(
    address: int,
    value: int,
    bank: int = 0,
) -> Frame:
    return _adjustment_frame(
        address,
        Opcode.ADJUST_LINE_LOCK_PHASE_DELAY,
        value,
        bank,
    )


def adjust_white_balance_rb(
    address: int,
    value: int,
    bank: int = 0,
) -> Frame:
    return _adjustment_frame(
        address,
        Opcode.ADJUST_WHITE_BALANCE_RB,
        value,
        bank,
    )


def adjust_white_balance_mg(
    address: int,
    value: int,
    bank: int = 0,
) -> Frame:
    return _adjustment_frame(
        address,
        Opcode.ADJUST_WHITE_BALANCE_MG,
        value,
        bank,
    )


def adjust_gain(address: int, value: int, bank: int = 0) -> Frame:
    return _adjustment_frame(
        address,
        Opcode.ADJUST_GAIN,
        value,
        bank,
    )


def adjust_auto_iris_level(
    address: int,
    value: int,
    bank: int = 0,
) -> Frame:
    return _adjustment_frame(
        address,
        Opcode.ADJUST_AUTO_IRIS_LEVEL,
        value,
        bank,
    )


def adjust_auto_iris_peak(
    address: int,
    value: int,
    bank: int = 0,
) -> Frame:
    return _adjustment_frame(
        address,
        Opcode.ADJUST_AUTO_IRIS_PEAK,
        value,
        bank,
    )


def _adjustment_frame(
    address: int,
    opcode: Opcode,
    value: int,
    bank: int,
) -> Frame:
    if bank not in (0, 1):
        raise ValueError(f"bank={bank} expected=0 or 1")
    return _opcode_value_frame(address, opcode, value, command1=bank)


def query_device(address: int, value: int = 0) -> Frame:
    return _opcode_value_frame(address, Opcode.QUERY_DEVICE, value)


def reserved_opcode(address: int, opcode: int) -> Frame:
    if opcode not in (0x47, 0x57, 0x65, 0x67, 0x69, 0x6B, 0x6D, 0x6F, 0x71):
        raise ValueError(f"reserved_opcode=0x{opcode:02x} is not defined")
    return make_frame(address, opcode)


def set_zero_position(address: int) -> Frame:
    return make_frame(address, Opcode.SET_ZERO_POSITION)


def set_pan_position(address: int, degrees: float) -> Frame:
    value = round(degrees * 100)
    if not 0 <= value <= 35999:
        raise ValueError(f"pan_degrees={degrees} expected=0..359.99")
    return _opcode_value_frame(address, Opcode.SET_PAN_POSITION, value)


def set_tilt_position(address: int, degrees: float) -> Frame:
    value = round(degrees * 100)
    if not 0 <= value <= 35999:
        raise ValueError(f"tilt_degrees={degrees} expected=0..359.99")
    return _opcode_value_frame(address, Opcode.SET_TILT_POSITION, value)


def set_zoom_position(address: int, position: int) -> Frame:
    return _opcode_value_frame(address, Opcode.SET_ZOOM_POSITION, position)


def query_pan_position(address: int) -> Frame:
    return make_frame(address, Opcode.QUERY_PAN_POSITION)


def query_tilt_position(address: int) -> Frame:
    return make_frame(address, Opcode.QUERY_TILT_POSITION)


def query_zoom_position(address: int) -> Frame:
    return make_frame(address, Opcode.QUERY_ZOOM_POSITION)


def set_magnification(address: int, magnification: float) -> Frame:
    value = round(magnification * 100)
    return _opcode_value_frame(address, Opcode.SET_MAGNIFICATION, value)


def query_magnification(address: int) -> Frame:
    return make_frame(address, Opcode.QUERY_MAGNIFICATION)


def set_focus_position(address: int, position: int) -> Frame:
    """Set focus position on devices that assign opcode 0x5F to focus."""
    return _opcode_value_frame(address, Opcode.SET_FOCUS_POSITION, position)


def query_focus_position(address: int) -> Frame:
    """Query focus position on devices that assign opcode 0x61 to focus."""
    return make_frame(address, Opcode.QUERY_FOCUS_POSITION)


def decode_position_response(frame: Frame) -> tuple[str, int | float]:
    opcode = Opcode(frame.command2)
    name, scale = POSITION_RESPONSES[opcode]
    value = frame.value * scale
    return name, value


def decode_magnification_response(frame: Frame) -> float:
    if frame.command2 != Opcode.MAGNIFICATION_RESPONSE:
        raise ValueError(
            f"response_opcode=0x{frame.command2:02x} "
            f"expected=0x{Opcode.MAGNIFICATION_RESPONSE:02x}"
        )
    return frame.value / 100


def decode_focus_position_response(frame: Frame) -> int:
    if frame.command2 != Opcode.FOCUS_POSITION_RESPONSE:
        raise ValueError(
            f"response_opcode=0x{frame.command2:02x} "
            f"expected=0x{Opcode.FOCUS_POSITION_RESPONSE:02x}"
        )
    return frame.value


def decode_general_response(
    packet: bytes,
    sent_checksum: int | None = None,
) -> GeneralResponse:
    if len(packet) != GENERAL_RESPONSE_LENGTH:
        raise ValueError(
            f"general_response_length={len(packet)} "
            f"expected={GENERAL_RESPONSE_LENGTH}"
        )
    if packet[0] != SYNC:
        raise ValueError(
            f"general_response_sync=0x{packet[0]:02x} expected=0xff"
        )
    alarm_bits = packet[2] & 0x7F
    if sent_checksum is not None:
        expected_checksum = (sent_checksum + alarm_bits) & 0xFF
        if packet[3] != expected_checksum:
            raise ValueError(
                f"general_response_checksum=0x{packet[3]:02x} "
                f"expected=0x{expected_checksum:02x}"
            )
    active_alarms = frozenset(
        alarm
        for alarm in range(1, ALARM_COUNT + 1)
        if alarm_bits & (1 << (alarm - 1))
    )
    return GeneralResponse(packet[1], active_alarms)


def decode_device_query_response(
    packet: bytes,
    sent_checksum: int | None = None,
) -> DeviceQueryResponse:
    if len(packet) != DEVICE_QUERY_RESPONSE_LENGTH:
        raise ValueError(
            f"device_query_response_length={len(packet)} "
            f"expected={DEVICE_QUERY_RESPONSE_LENGTH}"
        )
    if packet[0] != SYNC:
        raise ValueError(
            f"device_query_response_sync=0x{packet[0]:02x} expected=0xff"
        )
    address = packet[1]
    part_number = packet[2:17]
    if sent_checksum is not None:
        expected_checksum = (
            sent_checksum + address + sum(part_number)
        ) & 0xFF
        if packet[17] != expected_checksum:
            raise ValueError(
                f"device_query_response_checksum=0x{packet[17]:02x} "
                f"expected=0x{expected_checksum:02x}"
            )
    return DeviceQueryResponse(address, part_number)


class PelcoCamera:
    def __init__(
        self,
        serial_port,
        address: int = 1,
        response_timeout: float = 0.1,
    ) -> None:
        self.serial = serial_port
        self.address = address
        self.response_timeout = response_timeout

    @classmethod
    def open(
        cls,
        port: str,
        baud: int = 9600,
        address: int = 1,
        response_timeout: float = 0.1,
    ):
        serial_port = serial.Serial()
        serial_port.port = port
        serial_port.baudrate = baud
        serial_port.bytesize = serial.EIGHTBITS
        serial_port.parity = serial.PARITY_NONE
        serial_port.stopbits = serial.STOPBITS_ONE
        serial_port.timeout = 0
        serial_port.write_timeout = response_timeout
        serial_port.xonxoff = False
        serial_port.rtscts = False
        serial_port.dsrdtr = False
        serial_port.rts = False
        serial_port.dtr = False
        serial_port.open()
        serial_port.reset_input_buffer()
        serial_port.reset_output_buffer()
        return cls(serial_port, address, response_timeout)

    def close(self) -> None:
        self.serial.close()

    def send(self, frame: Frame) -> None:
        packet = frame.to_bytes()
        written = self.serial.write(packet)
        if written != len(packet):
            raise IOError(
                f"serial_write={written} expected={len(packet)} "
                f"packet={packet.hex()}"
            )
        self.serial.flush()

    def send_with_general_response(self, frame: Frame) -> GeneralResponse:
        packet = frame.to_bytes()
        self.serial.reset_input_buffer()
        self.send(frame)
        deadline = time.monotonic() + self.response_timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            waiting = self.serial.in_waiting
            chunk = self.serial.read(waiting if waiting > 0 else 1)
            if chunk:
                buffer.extend(chunk)
            while len(buffer) >= GENERAL_RESPONSE_LENGTH:
                sync_index = buffer.find(bytes((SYNC,)))
                if sync_index < 0:
                    buffer.clear()
                    break
                if sync_index:
                    del buffer[:sync_index]
                if len(buffer) < GENERAL_RESPONSE_LENGTH:
                    break
                candidate = bytes(buffer[:GENERAL_RESPONSE_LENGTH])
                try:
                    response = decode_general_response(
                        candidate,
                        sent_checksum=packet[-1],
                    )
                except ValueError:
                    del buffer[0]
                    continue
                if response.address == self.address:
                    return response
                del buffer[:GENERAL_RESPONSE_LENGTH]
            time.sleep(0.001)
        raise PelcoTimeoutError(
            f"command={packet.hex()} expected=general_response "
            f"rx={bytes(buffer).hex() or '<empty>'}"
        )

    def query(self, frame: Frame, response_opcode: Opcode) -> Frame:
        self.serial.reset_input_buffer()
        self.send(frame)
        deadline = time.monotonic() + self.response_timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            waiting = self.serial.in_waiting
            chunk = self.serial.read(waiting if waiting > 0 else 1)
            if chunk:
                buffer.extend(chunk)
            while len(buffer) >= FRAME_LENGTH:
                sync_index = buffer.find(bytes((SYNC,)))
                if sync_index < 0:
                    buffer.clear()
                    break
                if sync_index:
                    del buffer[:sync_index]
                if len(buffer) < FRAME_LENGTH:
                    break
                candidate = bytes(buffer[:FRAME_LENGTH])
                try:
                    response = Frame.from_bytes(candidate)
                except ValueError:
                    del buffer[0]
                    continue
                del buffer[:FRAME_LENGTH]
                if (
                    response.address == self.address
                    and response.command2 == response_opcode
                ):
                    return response
            time.sleep(0.001)
        raise PelcoTimeoutError(
            f"query={frame.to_bytes().hex()} "
            f"expected_opcode=0x{response_opcode:02x} "
            f"rx={bytes(buffer).hex() or '<empty>'}"
        )

    def query_pan(self) -> float:
        response = self.query(
            query_pan_position(self.address),
            Opcode.PAN_POSITION_RESPONSE,
        )
        return response.value / 100

    def query_tilt(self) -> float:
        response = self.query(
            query_tilt_position(self.address),
            Opcode.TILT_POSITION_RESPONSE,
        )
        return response.value / 100

    def query_zoom(self) -> int:
        response = self.query(
            query_zoom_position(self.address),
            Opcode.ZOOM_POSITION_RESPONSE,
        )
        return response.value

    def query_magnification(self) -> float:
        response = self.query(
            query_magnification(self.address),
            Opcode.MAGNIFICATION_RESPONSE,
        )
        return decode_magnification_response(response)

    def query_focus(self) -> int:
        response = self.query(
            query_focus_position(self.address),
            Opcode.FOCUS_POSITION_RESPONSE,
        )
        return decode_focus_position_response(response)

    def query_device_info(self, value: int = 0) -> DeviceQueryResponse:
        frame = query_device(self.address, value)
        packet = frame.to_bytes()
        self.serial.reset_input_buffer()
        self.send(frame)
        deadline = time.monotonic() + self.response_timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            waiting = self.serial.in_waiting
            chunk = self.serial.read(waiting if waiting > 0 else 1)
            if chunk:
                buffer.extend(chunk)
            while len(buffer) >= DEVICE_QUERY_RESPONSE_LENGTH:
                sync_index = buffer.find(bytes((SYNC,)))
                if sync_index < 0:
                    buffer.clear()
                    break
                if sync_index:
                    del buffer[:sync_index]
                if len(buffer) < DEVICE_QUERY_RESPONSE_LENGTH:
                    break
                candidate = bytes(buffer[:DEVICE_QUERY_RESPONSE_LENGTH])
                try:
                    response = decode_device_query_response(
                        candidate,
                        sent_checksum=packet[-1],
                    )
                except ValueError:
                    del buffer[0]
                    continue
                if response.address == self.address:
                    return response
                del buffer[:DEVICE_QUERY_RESPONSE_LENGTH]
            time.sleep(0.001)
        raise PelcoTimeoutError(
            f"query={packet.hex()} expected=device_info "
            f"rx={bytes(buffer).hex() or '<empty>'}"
        )
