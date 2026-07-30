import unittest
from unittest.mock import patch

from joystick_input import JoystickCameraActionMapper, JoystickChannelMapper
from pelco_server import camera_action_frame
from udp_control import CameraAction, MAX_US, MID_US, MIN_US


class JoystickCameraActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.mapper = JoystickCameraActionMapper()
        self.buttons = [0] * 12

    def read(self):
        return self.mapper.read(self.buttons)

    def test_menu_iris_and_night_mode_are_edge_triggered(self) -> None:
        self.assertEqual(self.read(), [])

        self.buttons[9] = 1
        self.assertEqual(self.read(), [(CameraAction.OPEN_MENU, 0)])
        self.assertEqual(self.read(), [])
        self.buttons[9] = 0
        self.read()

        self.buttons[2] = 1
        self.assertEqual(self.read(), [(CameraAction.IRIS_OPEN, 0)])
        self.buttons[2] = 0
        self.read()

        self.buttons[3] = 1
        self.assertEqual(
            self.read(),
            [(CameraAction.SET_NIGHT_MODE, 1)],
        )
        self.buttons[3] = 0
        self.read()
        self.buttons[3] = 1
        self.assertEqual(
            self.read(),
            [(CameraAction.SET_NIGHT_MODE, 0)],
        )

    def test_zoom_buttons_do_not_emit_absolute_position_actions(self) -> None:
        self.read()
        self.buttons[6] = 1
        self.assertEqual(self.read(), [])
        self.assertEqual(self.read(), [])

    def test_gamepad_zoom_is_continuous_and_start_is_not_arm(self) -> None:
        class FakeJoystick:
            def __init__(self) -> None:
                self.axes = [0.0] * 4
                self.buttons = [0] * 12

            def get_name(self):
                return "Test Gamepad"

            def get_numaxes(self):
                return len(self.axes)

            def get_axis(self, index):
                return self.axes[index]

            def get_numbuttons(self):
                return len(self.buttons)

            def get_button(self, index):
                return self.buttons[index]

        joystick = FakeJoystick()
        mapper = JoystickChannelMapper(joystick)
        with patch("joystick_input.pygame.event.pump"):
            joystick.buttons[4] = 1
            channels, _, _ = mapper.read()
            self.assertEqual(channels[9], MAX_US)
            self.assertEqual(channels[11], MIN_US)

            joystick.buttons[4] = 0
            joystick.buttons[6] = 1
            channels, _, _ = mapper.read()
            self.assertEqual(channels[9], MIN_US)
            self.assertEqual(channels[11], MAX_US)

            joystick.buttons[9] = 1
            channels, _, _ = mapper.read()
            self.assertEqual(channels[4], MID_US)

    def test_server_action_frames_match_original_camera_commands(self) -> None:
        self.assertEqual(
            camera_action_frame(1, CameraAction.OPEN_MENU, 0).to_bytes(),
            bytes.fromhex("ff 01 00 03 00 5f 63"),
        )
        self.assertEqual(
            camera_action_frame(1, CameraAction.IRIS_OPEN, 0).to_bytes(),
            bytes.fromhex("ff 01 02 00 00 00 03"),
        )
        self.assertEqual(
            camera_action_frame(
                1,
                CameraAction.SET_NIGHT_MODE,
                1,
            ).to_bytes(),
            bytes.fromhex("ff 01 00 03 03 78 7f"),
        )
        self.assertEqual(
            camera_action_frame(
                1,
                CameraAction.SET_NIGHT_MODE,
                0,
            ).to_bytes(),
            bytes.fromhex("ff 01 00 03 03 e7 ee"),
        )


if __name__ == "__main__":
    unittest.main()
