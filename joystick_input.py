"""Map pygame joystick state to continuous channels and camera actions."""

import pygame

from udp_control import (
    CameraAction,
    CHANNEL_COUNT,
    MID_US,
    MIN_US,
    axis_to_us,
    button_to_us,
)


AXIS_COUNT = 4
BUTTON_COUNT = 12
GAMEPAD_AUX_BUTTON_COUNT = 8
GAMEPAD_LATCHED_BUTTON_COUNT = 4

# Original gamepad map recovered from joystickcmd.py history. Pygame indexes
# are zero-based; the old axis comments numbered them from one.
#
#   axis 0: left stick right   -> camera pan
#   axis 1: left stick down    -> camera tilt
#   axis 2: right stick down   -> tracker left/right input
#   axis 3: right stick right  -> tracker up/down input
#
#   button 0: A                -> unused by camera
#   button 1: B                -> unused by camera
#   button 2: C                -> iris open
#   button 3: D                -> night mode toggle / tracker reset
#   button 4: "Near LT"        -> zoom wide while held
#   button 5: "Near RT"        -> focus near
#   button 6: "Far LT"         -> zoom tele while held
#   button 7: "Far RT"         -> focus far / tracker lock
#   button 8: Select           -> unused
#   button 9: Start            -> open camera system menu
#   button 10: left stick click
#   button 11: right stick click
#
# SDL mappings vary. joystickcmd.py --debugch prints the raw axes and buttons.


def get_joystick_state(joystick, minimum_axes):
    pygame.event.pump()
    axes = [
        round(joystick.get_axis(index), 3)
        for index in range(joystick.get_numaxes())
    ]
    buttons = [
        joystick.get_button(index)
        for index in range(joystick.get_numbuttons())
    ]
    while len(axes) < minimum_axes:
        axes.append(0.0)
    while len(buttons) < BUTTON_COUNT:
        buttons.append(0)
    return axes[:minimum_axes], buttons[:BUTTON_COUNT]


class JoystickChannelMapper:
    def __init__(self, joystick) -> None:
        self.joystick = joystick
        joystick_name = joystick.get_name().casefold()
        self.is_tx12 = "tx12" in joystick_name or "radiomaster" in joystick_name
        self.required_axes = 8 if self.is_tx12 else AXIS_COUNT
        self.channels = [MID_US] * CHANNEL_COUNT
        self.channels[2] = MIN_US
        self.latched_buttons = [False] * GAMEPAD_AUX_BUTTON_COUNT
        self.last_buttons = [0] * GAMEPAD_AUX_BUTTON_COUNT

    def read(self):
        axes, buttons = get_joystick_state(
            self.joystick,
            self.required_axes,
        )
        if self.is_tx12:
            for index in range(4):
                self.channels[index] = axis_to_us(axes[index])
            for index in range(4):
                self.channels[4 + index] = axis_to_us(axes[4 + index])
            for index in range(4):
                self.channels[8 + index] = button_to_us(buttons[index])
        else:
            self.channels[0] = axis_to_us(axes[2])
            self.channels[1] = axis_to_us(axes[3])
            self.channels[2] = axis_to_us(-axes[1])
            self.channels[3] = axis_to_us(axes[0])

            for index in range(GAMEPAD_AUX_BUTTON_COUNT):
                if (
                    index < GAMEPAD_LATCHED_BUTTON_COUNT
                    and buttons[index]
                    and not self.last_buttons[index]
                ):
                    self.latched_buttons[index] = not self.latched_buttons[index]
                self.last_buttons[index] = buttons[index]
                active = (
                    buttons[index]
                    if index >= GAMEPAD_LATCHED_BUTTON_COUNT
                    else self.latched_buttons[index]
                )
                self.channels[5 + index] = button_to_us(active)

        return list(self.channels), axes, buttons


class JoystickCameraActionMapper:
    def __init__(self) -> None:
        self.last_buttons = [0] * BUTTON_COUNT
        self.night_mode = False

    def read(self, buttons):
        actions = []
        if buttons[9] and not self.last_buttons[9]:
            actions.append((CameraAction.OPEN_MENU, 0))
        if buttons[2] and not self.last_buttons[2]:
            actions.append((CameraAction.IRIS_OPEN, 0))
        if buttons[3] and not self.last_buttons[3]:
            self.night_mode = not self.night_mode
            actions.append((CameraAction.SET_NIGHT_MODE, int(self.night_mode)))

        self.last_buttons = list(buttons)
        return actions
