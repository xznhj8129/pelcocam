#!/usr/bin/env python3
"""Usage:
    python3 joystickcmd.py --target 127.0.0.1 --port 60000 \
        --rate 50 --joystick-index 0

Sends the same 40-byte UDP channel packets as crsfproxy/joystick_crsf.py.
The Pelco server, not this input client, owns the camera serial port.
"""

import argparse
import socket
import time

import pygame

from joystick_input import JoystickCameraActionMapper, JoystickChannelMapper
from udp_control import pack_control_packet, send_camera_action


DEFAULT_PORT = 60000
DEFAULT_RATE_HZ = 50.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send joystick channels to the Pelco camera server."
    )
    parser.add_argument("--target", required=True, help="Pelco server host/IP")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="Pelco server UDP control port",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_RATE_HZ,
        help="send rate in Hz",
    )
    parser.add_argument(
        "--joystick-index",
        type=int,
        default=0,
        help="joystick index reported by pygame",
    )
    parser.add_argument(
        "--debugch",
        action="store_true",
        help="print raw axes, buttons, and channels at approximately 2 Hz",
    )
    args = parser.parse_args()

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        raise RuntimeError("No joystick detected.")
    if args.joystick_index >= pygame.joystick.get_count():
        raise RuntimeError(
            f"joystick_index={args.joystick_index} "
            f"available={pygame.joystick.get_count()}"
        )

    joystick = pygame.joystick.Joystick(args.joystick_index)
    joystick.init()
    mapper = JoystickChannelMapper(joystick)
    action_mapper = JoystickCameraActionMapper()
    target = (args.target, args.port)
    period = 1 / args.rate
    debug_time = 0.0
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(
        f"Joystick {joystick.get_name()!r} ready on index "
        f"{args.joystick_index}."
    )
    print(f"Sending UDP camera control to {target[0]}:{target[1]}.")

    try:
        while True:
            loop_started = time.monotonic()
            channels, axes, buttons = mapper.read()
            actions = action_mapper.read(buttons)
            control_socket.sendto(pack_control_packet(channels), target)
            for action, value in actions:
                send_camera_action(
                    control_socket,
                    target,
                    action,
                    value,
                )
            if args.debugch and loop_started - debug_time >= 0.5:
                print(
                    f"axes={axes} buttons={buttons} channels={channels} "
                    f"actions={actions}"
                )
                debug_time = loop_started
            elapsed = time.monotonic() - loop_started
            if elapsed < period:
                time.sleep(period - elapsed)
    finally:
        control_socket.close()
        pygame.quit()


if __name__ == "__main__":
    main()
