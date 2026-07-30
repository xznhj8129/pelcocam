#!/usr/bin/env python3
"""Usage:
    python3 trackcmd.py --target 127.0.0.1 --port 60000 \
        --tracker-host 127.0.0.1 --tracker-output-port 8100 \
        --tracker-input-port 8101

Combines joystick input with MCVST tracking corrections and sends the same
40-byte UDP channel packets as joystickcmd.py and crsfproxy/joystick_crsf.py.
The Pelco server, not this tracking client, owns the camera serial port.
"""

import argparse
import json
import socket
import time

import pygame
from simple_pid import PID

from joystick_input import JoystickCameraActionMapper, JoystickChannelMapper
from udp_control import (
    MID_US,
    axis_to_us,
    pack_control_packet,
    send_camera_action,
)


DEFAULT_CONTROL_PORT = 60000
DEFAULT_RATE_HZ = 20.0
DEFAULT_TRACKER_OUTPUT_PORT = 8100
DEFAULT_TRACKER_INPUT_PORT = 8101
DEFAULT_P = 0.75
DEFAULT_I = 0.05
DEFAULT_D = 0.1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send joystick or MCVST tracking control to the Pelco server."
    )
    parser.add_argument("--target", required=True, help="Pelco server host/IP")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_CONTROL_PORT,
        help="Pelco server UDP control port",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=DEFAULT_RATE_HZ,
        help="control and tracker update rate in Hz",
    )
    parser.add_argument(
        "--joystick-index",
        type=int,
        default=0,
        help="joystick index reported by pygame",
    )
    parser.add_argument(
        "--tracker-host",
        default="127.0.0.1",
        help="MCVST input/output host",
    )
    parser.add_argument(
        "--tracker-output-port",
        type=int,
        default=DEFAULT_TRACKER_OUTPUT_PORT,
        help="MCVST tracking-state TCP port",
    )
    parser.add_argument(
        "--tracker-input-port",
        type=int,
        default=DEFAULT_TRACKER_INPUT_PORT,
        help="MCVST command TCP port",
    )
    parser.add_argument("--p", type=float, default=DEFAULT_P, help="tracking P gain")
    parser.add_argument("--i", type=float, default=DEFAULT_I, help="tracking I gain")
    parser.add_argument("--d", type=float, default=DEFAULT_D, help="tracking D gain")
    parser.add_argument(
        "--gain",
        type=float,
        default=1.0,
        help="scale tracker error before PID",
    )
    parser.add_argument(
        "--debugch",
        action="store_true",
        help="print tracker state, raw joystick input, and channels",
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
    pid_pan = PID(
        args.p,
        args.i,
        args.d,
        setpoint=0,
        output_limits=(-1.0, 1.0),
        time_fn=time.monotonic,
        starting_output=0,
    )
    pid_tilt = PID(
        args.p,
        args.i,
        args.d,
        setpoint=0,
        output_limits=(-1.0, 1.0),
        time_fn=time.monotonic,
        starting_output=0,
    )

    tracker_output = socket.create_connection(
        (args.tracker_host, args.tracker_output_port),
        timeout=5,
    )
    tracker_input = socket.create_connection(
        (args.tracker_host, args.tracker_input_port),
        timeout=5,
    )
    tracker_output.settimeout(1)
    tracker_input.settimeout(1)
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    control_target = (args.target, args.port)
    period = 1 / args.rate
    debug_time = 0.0

    print(
        f"Joystick {joystick.get_name()!r} ready on index "
        f"{args.joystick_index}."
    )
    print(
        f"Connected to MCVST input={args.tracker_host}:"
        f"{args.tracker_input_port} output={args.tracker_host}:"
        f"{args.tracker_output_port}."
    )
    print(
        f"Sending UDP camera control to "
        f"{control_target[0]}:{control_target[1]}."
    )
    try:
        while True:
            loop_started = time.monotonic()
            channels, axes, buttons = mapper.read()
            actions = action_mapper.read(buttons)

            tracker_command = {
                "lock": buttons[7],
                "reset": buttons[3],
                "lr": axes[2],
                "ud": -axes[3],
                "boxsize": int(axes[0]),
                "shutdown": 0,
            }
            # Button 7 is reserved for MCVST lock in this client. In the
            # shared joystick mapping it is also channel 12 (focus far), so
            # neutralize that channel rather than moving focus while locking.
            channels[12] = MID_US
            tracker_input.sendall(
                (json.dumps(tracker_command) + "\n").encode()
            )
            acknowledgement = tracker_input.recv(1)
            if not acknowledgement:
                raise ConnectionError("MCVST command connection closed")

            tracker_output.sendall(b"x")
            response = tracker_output.recv(4096)
            if not response:
                raise ConnectionError("MCVST tracking connection closed")
            tracking_state = json.loads(response)
            tracking = bool(int(tracking_state["locked"]))
            track_pan = 0.0
            track_tilt = 0.0
            if tracking:
                track_pan = pid_pan(
                    -float(tracking_state["tracking"][0]) * args.gain
                )
                track_tilt = pid_tilt(
                    -float(tracking_state["tracking"][1]) * args.gain
                )
                channels[3] = axis_to_us(track_pan)
                channels[2] = axis_to_us(-track_tilt)
            else:
                pid_pan.reset()
                pid_tilt.reset()

            control_socket.sendto(pack_control_packet(channels), control_target)
            for action, value in actions:
                send_camera_action(
                    control_socket,
                    control_target,
                    action,
                    value,
                )
            if args.debugch and loop_started - debug_time >= 0.5:
                print(
                    f"locked={tracking} "
                    f"tracking={tracking_state['tracking']} "
                    f"pan={track_pan:.3f} tilt={track_tilt:.3f} "
                    f"axes={axes} buttons={buttons} "
                    f"channels={channels} actions={actions}"
                )
                debug_time = loop_started

            elapsed = time.monotonic() - loop_started
            if elapsed < period:
                time.sleep(period - elapsed)
    finally:
        control_socket.close()
        tracker_input.close()
        tracker_output.close()
        pygame.quit()


if __name__ == "__main__":
    main()
