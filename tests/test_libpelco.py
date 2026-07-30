import unittest

import libpelco as pelco
from libpelco import (
    Command1,
    Command2,
    Frame,
    Opcode,
    PelcoCamera,
    decode_position_response,
    query_pan_position,
    standard_control,
)


class FakeSerial:
    def __init__(self, response: bytes) -> None:
        self.response = bytearray(response)
        self.written = bytearray()

    @property
    def in_waiting(self) -> int:
        return len(self.response)

    def reset_input_buffer(self) -> None:
        pass

    def write(self, packet: bytes) -> int:
        self.written.extend(packet)
        return len(packet)

    def flush(self) -> None:
        pass

    def read(self, size: int) -> bytes:
        data = bytes(self.response[:size])
        del self.response[:size]
        return data


class FrameTests(unittest.TestCase):
    def test_query_pan_packet(self) -> None:
        packet = query_pan_position(1).to_bytes()
        self.assertEqual(packet, bytes.fromhex("ff 01 00 51 00 00 52"))
        self.assertEqual(Frame.from_bytes(packet), query_pan_position(1))

    def test_invalid_checksum_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "frame_checksum"):
            Frame.from_bytes(bytes.fromhex("ff 01 00 51 00 00 00"))

    def test_standard_control_combines_axes_and_lens(self) -> None:
        frame = standard_control(
            1,
            pan=0.5,
            tilt=-1.0,
            zoom=1,
            focus=-1,
            iris=1,
        )
        self.assertEqual(
            frame.command1,
            Command1.FOCUS_NEAR | Command1.IRIS_OPEN,
        )
        self.assertEqual(
            frame.command2,
            Command2.RIGHT | Command2.UP | Command2.ZOOM_TELE,
        )
        self.assertEqual(frame.data1, 32)
        self.assertEqual(frame.data2, 63)

    def test_autofocus_toggle_uses_auto_and_off_modes(self) -> None:
        self.assertEqual(
            pelco.set_auto_focus(1, True).to_bytes(),
            bytes.fromhex("ff 01 00 2b 00 00 2c"),
        )
        self.assertEqual(
            pelco.set_auto_focus(1, False).to_bytes(),
            bytes.fromhex("ff 01 00 2b 00 02 2e"),
        )
        self.assertEqual(
            pelco.set_auto_iris(1, False).to_bytes(),
            bytes.fromhex("ff 01 00 2d 00 02 30"),
        )

    def test_standard_command_family(self) -> None:
        cases = (
            (pelco.camera_on(1), (0x88, 0x00, 0x00, 0x00)),
            (pelco.camera_off(1), (0x08, 0x00, 0x00, 0x00)),
            (pelco.set_auto_scan(1, True), (0x90, 0x00, 0x00, 0x00)),
            (pelco.set_auto_scan(1, False), (0x10, 0x00, 0x00, 0x00)),
            (pelco.iris_open(1), (0x02, 0x00, 0x00, 0x00)),
            (pelco.iris_close(1), (0x04, 0x00, 0x00, 0x00)),
            (pelco.focus_near(1), (0x01, 0x00, 0x00, 0x00)),
            (pelco.focus_far(1), (0x00, 0x80, 0x00, 0x00)),
            (pelco.zoom_wide(1), (0x00, 0x40, 0x00, 0x00)),
            (pelco.zoom_tele(1), (0x00, 0x20, 0x00, 0x00)),
            (pelco.pan_left(1, 0x40), (0x00, 0x04, 0x40, 0x00)),
            (pelco.pan_right(1, 0x3F), (0x00, 0x02, 0x3F, 0x00)),
            (pelco.pan(1, -1), (0x00, 0x04, 0x01, 0x00)),
            (pelco.tilt_up(1, 0x3F), (0x00, 0x08, 0x00, 0x3F)),
            (pelco.tilt_down(1, 1), (0x00, 0x10, 0x00, 0x01)),
            (pelco.tilt(1, -1), (0x00, 0x10, 0x00, 0x01)),
        )
        for frame, expected in cases:
            with self.subTest(frame=frame):
                self.assertEqual(
                    (frame.command1, frame.command2, frame.data1, frame.data2),
                    expected,
                )
        for opcode in (0x47, 0x57, 0x65, 0x67, 0x69, 0x6B, 0x6D, 0x6F, 0x71):
            with self.subTest(reserved_opcode=opcode):
                self.assertEqual(
                    pelco.reserved_opcode(1, opcode).command2,
                    opcode,
                )

    def test_extended_command_families(self) -> None:
        cases = (
            (pelco.set_preset(1, 95), (0x00, 0x03, 0x00, 0x5F)),
            (pelco.set_extended_preset(1, 888), (0x00, 0x03, 0x03, 0x78)),
            (pelco.clear_preset(1, 5), (0x00, 0x05, 0x00, 0x05)),
            (pelco.goto_preset(1, 5), (0x00, 0x07, 0x00, 0x05)),
            (pelco.flip_180(1), (0x00, 0x07, 0x00, 0x21)),
            (pelco.goto_zero_pan(1), (0x00, 0x07, 0x00, 0x22)),
            (pelco.set_auxiliary(1, 8), (0x00, 0x09, 0x00, 0x08)),
            (pelco.clear_auxiliary(1, 8), (0x00, 0x0B, 0x00, 0x08)),
            (pelco.remote_reset(1), (0x00, 0x0F, 0x00, 0x00)),
            (pelco.set_zone_start(1, 2), (0x00, 0x11, 0x00, 0x02)),
            (pelco.set_zone_end(1, 2), (0x00, 0x13, 0x00, 0x02)),
            (pelco.write_character(1, 39, ord("A")), (0x00, 0x15, 39, 65)),
            (pelco.write_zone_label(1, 19, 65), (0x00, 0x15, 19, 65)),
            (pelco.write_preset_label(1, 19, 65), (0x00, 0x15, 39, 65)),
            (pelco.clear_screen(1), (0x00, 0x17, 0x00, 0x00)),
            (pelco.acknowledge_alarm(1, 8), (0x00, 0x19, 0x00, 0x08)),
            (pelco.set_zone_scan(1, True), (0x00, 0x1B, 0x00, 0x00)),
            (pelco.set_zone_scan(1, False), (0x00, 0x1D, 0x00, 0x00)),
            (pelco.set_pattern_start(1, 3), (0x00, 0x1F, 0x00, 0x03)),
            (pelco.set_pattern_stop(1), (0x00, 0x21, 0x00, 0x00)),
            (pelco.run_pattern(1, 3), (0x00, 0x23, 0x00, 0x03)),
            (pelco.set_zoom_speed(1, 3), (0x00, 0x25, 0x00, 0x03)),
            (pelco.set_focus_speed(1, 3), (0x00, 0x27, 0x00, 0x03)),
            (pelco.reset_camera(1), (0x00, 0x29, 0x00, 0x00)),
            (
                pelco.set_focus_mode(1, pelco.AutoMode.OFF),
                (0x00, 0x2B, 0x00, 0x02),
            ),
            (
                pelco.set_iris_mode(1, pelco.AutoMode.AUTO),
                (0x00, 0x2D, 0x00, 0x00),
            ),
            (
                pelco.set_gain_control_mode(1, pelco.AutoMode.ON),
                (0x00, 0x2F, 0x00, 0x01),
            ),
            (
                pelco.set_backlight_compensation(1, pelco.SwitchMode.OFF),
                (0x00, 0x31, 0x00, 0x02),
            ),
            (
                pelco.set_auto_white_balance(1, pelco.SwitchMode.ON),
                (0x00, 0x33, 0x00, 0x01),
            ),
            (pelco.enable_phase_delay_mode(1), (0x00, 0x35, 0x00, 0x00)),
            (pelco.set_shutter_speed(1, 0x1234), (0x00, 0x37, 0x12, 0x34)),
            (
                pelco.adjust_line_lock_phase_delay(1, 0x1234, bank=1),
                (0x01, 0x39, 0x12, 0x34),
            ),
            (
                pelco.adjust_white_balance_rb(1, 0x1234, bank=1),
                (0x01, 0x3B, 0x12, 0x34),
            ),
            (
                pelco.adjust_white_balance_mg(1, 0x1234),
                (0x00, 0x3D, 0x12, 0x34),
            ),
            (
                pelco.adjust_gain(1, 0x1234, bank=1),
                (0x01, 0x3F, 0x12, 0x34),
            ),
            (
                pelco.adjust_auto_iris_level(1, 0x1234),
                (0x00, 0x41, 0x12, 0x34),
            ),
            (
                pelco.adjust_auto_iris_peak(1, 0x1234, bank=1),
                (0x01, 0x43, 0x12, 0x34),
            ),
            (pelco.query_device(1, 0x1234), (0x00, 0x45, 0x12, 0x34)),
            (pelco.reserved_opcode(1, 0x47), (0x00, 0x47, 0x00, 0x00)),
            (pelco.set_zero_position(1), (0x00, 0x49, 0x00, 0x00)),
            (pelco.set_pan_position(1, 45), (0x00, 0x4B, 0x11, 0x94)),
            (pelco.set_tilt_position(1, 30), (0x00, 0x4D, 0x0B, 0xB8)),
            (pelco.set_zoom_position(1, 1781), (0x00, 0x4F, 0x06, 0xF5)),
            (pelco.query_pan_position(1), (0x00, 0x51, 0x00, 0x00)),
            (pelco.query_tilt_position(1), (0x00, 0x53, 0x00, 0x00)),
            (pelco.query_zoom_position(1), (0x00, 0x55, 0x00, 0x00)),
            (
                pelco.set_magnification(1, 5),
                (0x00, 0x5F, 0x01, 0xF4),
            ),
            (pelco.query_magnification(1), (0x00, 0x61, 0x00, 0x00)),
            (
                pelco.set_focus_position(1, 500),
                (0x00, 0x5F, 0x01, 0xF4),
            ),
            (pelco.query_focus_position(1), (0x00, 0x61, 0x00, 0x00)),
        )
        for frame, expected in cases:
            with self.subTest(frame=frame):
                self.assertEqual(
                    (frame.command1, frame.command2, frame.data1, frame.data2),
                    expected,
                )

    def test_position_response_decode(self) -> None:
        frame = Frame.from_bytes(
            bytes.fromhex("ff 01 00 59 81 4a 25")
        )
        self.assertEqual(decode_position_response(frame), ("pan_deg", 330.98))

    def test_all_response_formats(self) -> None:
        general = pelco.decode_general_response(
            bytes.fromhex("ff 01 45 a8"),
            sent_checksum=0x63,
        )
        self.assertEqual(general.address, 1)
        self.assertEqual(general.active_alarms, frozenset((1, 3, 7)))

        query_checksum = pelco.query_device(1).to_bytes()[-1]
        part_number = b"123456789012345"
        response_checksum = (
            query_checksum + 1 + sum(part_number)
        ) & 0xFF
        device = pelco.decode_device_query_response(
            b"\xff\x01" + part_number + bytes((response_checksum,)),
            sent_checksum=query_checksum,
        )
        self.assertEqual(device.address, 1)
        self.assertEqual(device.part_number, part_number)

        magnification = pelco.Frame(1, 0, 0x63, 0x01, 0xF4)
        self.assertEqual(
            pelco.decode_magnification_response(magnification),
            5.0,
        )
        self.assertEqual(
            pelco.decode_focus_position_response(magnification),
            500,
        )

    def test_public_range_validation(self) -> None:
        with self.assertRaisesRegex(ValueError, "preset"):
            pelco.set_preset(1, 0)
        with self.assertRaisesRegex(ValueError, "pan_speed"):
            pelco.pan_left(1, 65)
        with self.assertRaisesRegex(ValueError, "bank"):
            pelco.adjust_gain(1, 0, bank=2)
        with self.assertRaisesRegex(ValueError, "pan_degrees"):
            pelco.set_pan_position(1, 360)

    def test_camera_query_ignores_leading_ack_and_garbage(self) -> None:
        response = (
            bytes.fromhex("ff 01 00 52")
            + b"\x12\x34"
            + bytes.fromhex("ff 01 00 59 81 4a 25")
        )
        serial_port = FakeSerial(response)
        camera = PelcoCamera(serial_port, address=1, response_timeout=0.01)
        frame = camera.query(
            query_pan_position(1),
            Opcode.PAN_POSITION_RESPONSE,
        )
        self.assertEqual(frame.value, 33098)
        self.assertEqual(
            bytes(serial_port.written),
            bytes.fromhex("ff 01 00 51 00 00 52"),
        )

    def test_camera_general_and_device_query_transports(self) -> None:
        command = pelco.camera_on(1)
        general_packet = bytes(
            (0xFF, 1, 0x05, (command.to_bytes()[-1] + 0x05) & 0xFF)
        )
        serial_port = FakeSerial(general_packet)
        camera = PelcoCamera(serial_port, address=1, response_timeout=0.01)
        response = camera.send_with_general_response(command)
        self.assertEqual(response.active_alarms, frozenset((1, 3)))

        query = pelco.query_device(1)
        part_number = b"123456789012345"
        checksum = (query.to_bytes()[-1] + 1 + sum(part_number)) & 0xFF
        serial_port = FakeSerial(
            b"\xff\x01" + part_number + bytes((checksum,))
        )
        camera = PelcoCamera(serial_port, address=1, response_timeout=0.01)
        response = camera.query_device_info()
        self.assertEqual(response.part_number, part_number)


if __name__ == "__main__":
    unittest.main()
