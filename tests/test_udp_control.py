import struct
import unittest
import zlib

from pelco_server import (
    channels_to_control,
    continuous_control_active,
    control_command_names,
)
from udp_control import (
    ACTION_PACKET_LENGTH,
    ACTION_REPEAT_COUNT,
    CameraAction,
    MAX_US,
    MID_US,
    MIN_US,
    PACKET_LENGTH,
    axis_to_us,
    pack_camera_action,
    pack_control_packet,
    send_camera_action,
    unpack_camera_action,
    unpack_control_packet,
)


class UdpControlTests(unittest.TestCase):
    def test_packet_matches_crsfproxy_wire_format(self) -> None:
        channels = list(range(1400, 1416))
        packet = pack_control_packet(channels, timestamp_ms=0x12345678)
        payload = struct.pack("<I16H", 0x12345678, *channels)
        expected = payload + struct.pack(
            "<I",
            zlib.crc32(payload) & 0xFFFFFFFF,
        )
        self.assertEqual(len(packet), PACKET_LENGTH)
        self.assertEqual(packet, expected)
        decoded = unpack_control_packet(packet)
        self.assertEqual(decoded.timestamp_ms, 0x12345678)
        self.assertEqual(decoded.channels_us, tuple(channels))

    def test_bad_crc_is_rejected(self) -> None:
        packet = bytearray(pack_control_packet([MID_US] * 16, timestamp_ms=1))
        packet[10] ^= 1
        with self.assertRaisesRegex(ValueError, "packet_crc"):
            unpack_control_packet(bytes(packet))

    def test_camera_action_packet_round_trip(self) -> None:
        packet = pack_camera_action(
            CameraAction.SET_ZOOM_POSITION,
            value=1234,
            event_id=0x12345678,
        )
        self.assertEqual(len(packet), ACTION_PACKET_LENGTH)
        decoded = unpack_camera_action(packet)
        self.assertEqual(decoded.action, CameraAction.SET_ZOOM_POSITION)
        self.assertEqual(decoded.event_id, 0x12345678)
        self.assertEqual(decoded.value, 1234)

    def test_bad_camera_action_crc_is_rejected(self) -> None:
        packet = bytearray(
            pack_camera_action(CameraAction.OPEN_MENU, event_id=1)
        )
        packet[8] ^= 1
        with self.assertRaisesRegex(ValueError, "action_packet_crc"):
            unpack_camera_action(bytes(packet))

    def test_camera_actions_are_repeated_with_one_event_id(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.sent = []

            def sendto(self, packet, target) -> None:
                self.sent.append((packet, target))

        sock = FakeSocket()
        target = ("127.0.0.1", 60000)
        send_camera_action(sock, target, CameraAction.IRIS_OPEN)
        self.assertEqual(len(sock.sent), ACTION_REPEAT_COUNT)
        self.assertTrue(
            all(packet == sock.sent[0][0] for packet, _ in sock.sent)
        )
        self.assertTrue(all(sent_target == target for _, sent_target in sock.sent))

    def test_axis_mapping_matches_crsfproxy_truncation(self) -> None:
        self.assertEqual(axis_to_us(-1.0), MIN_US)
        self.assertEqual(axis_to_us(0.0), MID_US)
        self.assertEqual(axis_to_us(0.123), 1573)
        self.assertEqual(axis_to_us(1.0), MAX_US)

    def test_server_channel_mapping(self) -> None:
        channels = [MID_US] * 16
        channels[3] = axis_to_us(0.5)
        channels[2] = axis_to_us(0.25)
        channels[5] = MIN_US
        channels[9] = MIN_US
        channels[10] = MAX_US
        channels[11] = MAX_US
        channels[12] = MIN_US
        control = channels_to_control(channels)
        self.assertAlmostEqual(control.pan, 0.5)
        self.assertAlmostEqual(control.tilt, -0.25)
        self.assertEqual(control.zoom, 1)
        self.assertEqual(control.focus, -1)
        self.assertEqual(
            control_command_names(control),
            ("PAN_RIGHT", "TILT_UP", "ZOOM_TELE", "FOCUS_NEAR"),
        )
        self.assertTrue(continuous_control_active(control))

        channels = [MID_US] * 16
        channels[10] = MAX_US
        focus_step = channels_to_control(channels)
        self.assertEqual(control_command_names(focus_step), ("FOCUS_NEAR",))
        self.assertFalse(continuous_control_active(focus_step))


if __name__ == "__main__":
    unittest.main()
