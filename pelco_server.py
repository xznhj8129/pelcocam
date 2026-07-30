#!/usr/bin/env python3
"""Usage:
    python3 pelco_server.py --device /dev/ttyUSB1 --baud 9600 \
        --host 0.0.0.0 --port 60000 \
        --telemetry-udp 127.0.0.1:60001

Owns the Pelco-D serial link, accepts crsfproxy-compatible 16-channel UDP
control packets, and continuously publishes measured camera telemetry as JSON.
"""

import argparse
from collections import deque
from dataclasses import dataclass
import json
import socket
import time

from libpelco import (
    PelcoCamera,
    PelcoTimeoutError,
    iris_open,
    set_extended_preset,
    set_preset,
    set_zoom_position,
    standard_control,
    stop,
)
from udp_control import (
    CameraAction,
    CHANNEL_COUNT,
    MID_US,
    PACKET_LENGTH,
    unpack_camera_action,
    unpack_control_packet,
    us_to_axis,
)


DEFAULT_DEVICE = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
DEFAULT_BAUD = 9600
DEFAULT_ADDRESS = 1
DEFAULT_CONTROL_PORT = 60000
DEFAULT_CONTROL_RATE_HZ = 20.0
DEFAULT_TELEMETRY_RATE_HZ = 5.0
DEFAULT_LOOP_RATE_HZ = 100.0
DEFAULT_FAILSAFE_MS = 500
CONTROL_DEADBAND = 0.05
PAN_CHANNEL = 3
TILT_CHANNEL = 2
ZOOM_WIDE_CHANNEL = 9
FOCUS_NEAR_CHANNEL = 10
ZOOM_TELE_CHANNEL = 11
FOCUS_FAR_CHANNEL = 12


@dataclass(frozen=True)
class CameraControl:
    pan: float
    tilt: float
    zoom: int
    focus: int


def channels_to_control(channels_us) -> CameraControl:
    if len(channels_us) != CHANNEL_COUNT:
        raise ValueError(
            f"channel_count={len(channels_us)} expected={CHANNEL_COUNT}"
        )
    zoom = (
        int(channels_us[ZOOM_TELE_CHANNEL] > MID_US)
        - int(channels_us[ZOOM_WIDE_CHANNEL] > MID_US)
    )
    focus = (
        int(channels_us[FOCUS_FAR_CHANNEL] > MID_US)
        - int(channels_us[FOCUS_NEAR_CHANNEL] > MID_US)
    )
    return CameraControl(
        pan=us_to_axis(channels_us[PAN_CHANNEL]),
        tilt=-us_to_axis(channels_us[TILT_CHANNEL]),
        zoom=zoom,
        focus=focus,
    )


def camera_action_frame(
    address: int,
    action: CameraAction,
    value: int,
):
    if action == CameraAction.OPEN_MENU:
        return set_preset(address, 95)
    if action == CameraAction.IRIS_OPEN:
        return iris_open(address)
    if action == CameraAction.SET_NIGHT_MODE:
        if value not in (0, 1):
            raise ValueError(f"night_mode={value} expected=0 or 1")
        return set_extended_preset(address, 888 if value else 999)
    if action == CameraAction.SET_ZOOM_POSITION:
        return set_zoom_position(address, value)
    raise ValueError(f"unsupported_camera_action={action!r}")


def control_command_names(control: CameraControl) -> tuple[str, ...]:
    commands = []
    if control.pan < -CONTROL_DEADBAND:
        commands.append("PAN_LEFT")
    elif control.pan > CONTROL_DEADBAND:
        commands.append("PAN_RIGHT")
    if control.tilt < -CONTROL_DEADBAND:
        commands.append("TILT_UP")
    elif control.tilt > CONTROL_DEADBAND:
        commands.append("TILT_DOWN")
    if control.zoom < 0:
        commands.append("ZOOM_WIDE")
    elif control.zoom > 0:
        commands.append("ZOOM_TELE")
    if control.focus < 0:
        commands.append("FOCUS_NEAR")
    elif control.focus > 0:
        commands.append("FOCUS_FAR")
    return tuple(commands) if commands else ("STOP",)


def continuous_control_active(control: CameraControl) -> bool:
    return (
        abs(control.pan) > CONTROL_DEADBAND
        or abs(control.tilt) > CONTROL_DEADBAND
        or control.zoom != 0
    )


def parse_udp_target(value: str) -> tuple[str, int]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("expected HOST:PORT")
    host, port = value.rsplit(":", 1)
    return host, int(port)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Concurrent UDP control and telemetry service for Pelco-D cameras."
    )
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="serial device")
    parser.add_argument("--baud", type=int, default=DEFAULT_BAUD, help="serial baud rate")
    parser.add_argument(
        "--address",
        type=int,
        default=DEFAULT_ADDRESS,
        help="Pelco-D camera address",
    )
    parser.add_argument("--host", default="0.0.0.0", help="UDP control bind host")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_CONTROL_PORT,
        help="UDP control port",
    )
    parser.add_argument(
        "--control-rate",
        type=float,
        default=DEFAULT_CONTROL_RATE_HZ,
        help="camera control update rate in Hz",
    )
    parser.add_argument(
        "--telemetry-rate",
        type=float,
        default=DEFAULT_TELEMETRY_RATE_HZ,
        help="rate in Hz for each pan/tilt/zoom query and JSON publication",
    )
    parser.add_argument(
        "--loop-rate",
        type=float,
        default=DEFAULT_LOOP_RATE_HZ,
        help="maximum server loop rate in Hz",
    )
    parser.add_argument(
        "--failsafe-ms",
        type=int,
        default=DEFAULT_FAILSAFE_MS,
        help="stop motion after this much control silence",
    )
    parser.add_argument(
        "--telemetry-udp",
        action="append",
        type=parse_udp_target,
        default=[],
        metavar="HOST:PORT",
        help="JSON telemetry target; may be supplied more than once",
    )
    parser.add_argument("--debug", action="store_true", help="print control and telemetry")
    args = parser.parse_args()

    camera = PelcoCamera.open(
        args.device,
        args.baud,
        args.address,
        response_timeout=max(0.05, 1 / args.telemetry_rate),
    )
    control_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    control_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    control_socket.bind((args.host, args.port))
    control_socket.setblocking(False)
    telemetry_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    telemetry_socket.setblocking(False)

    print(
        f"Pelco-D serial device={args.device} baud={args.baud} "
        f"address={args.address}"
    )
    print(f"Control UDP listening on {args.host}:{args.port}")
    for target in args.telemetry_udp:
        print(f"Telemetry JSON target {target[0]}:{target[1]}")

    neutral_channels = [MID_US] * CHANNEL_COUNT
    active_channels = neutral_channels
    active_control = channels_to_control(active_channels)
    last_control_update = 0.0
    last_control_sender = None
    last_control_frame = None
    last_control_commands = None
    last_zoom_position_request = None
    last_control_send = 0.0
    last_telemetry_send = 0.0
    last_position_log = None
    next_query = 0.0
    query_index = 0
    query_errors = {"pan": 0, "tilt": 0, "zoom": 0}
    telemetry = {
        "pan_deg": None,
        "tilt_deg": None,
        "zoom_position": None,
    }
    telemetry_updated = {
        "pan_deg": None,
        "tilt_deg": None,
        "zoom_position": None,
    }
    handled_action_keys = set()
    handled_action_order = deque(maxlen=256)
    query_schedule = (
        ("pan", "pan_deg", camera.query_pan),
        ("tilt", "tilt_deg", camera.query_tilt),
        ("zoom", "zoom_position", camera.query_zoom),
    )
    loop_period = 1 / args.loop_rate
    control_period = 1 / args.control_rate
    query_period = 1 / (args.telemetry_rate * len(query_schedule))
    telemetry_period = 1 / args.telemetry_rate

    try:
        while True:
            loop_started = time.monotonic()
            now = loop_started

            while True:
                try:
                    packet, sender = control_socket.recvfrom(128)
                except BlockingIOError:
                    break
                try:
                    if len(packet) == PACKET_LENGTH:
                        decoded = unpack_control_packet(packet)
                    else:
                        action_packet = unpack_camera_action(packet)
                except ValueError as error:
                    print(f"Rejected control sender={sender} error={error}")
                    continue
                if len(packet) != PACKET_LENGTH:
                    action_key = (sender, action_packet.event_id)
                    if action_key in handled_action_keys:
                        continue
                    if len(handled_action_order) == handled_action_order.maxlen:
                        handled_action_keys.remove(handled_action_order[0])
                    handled_action_order.append(action_key)
                    handled_action_keys.add(action_key)
                    try:
                        action_frame = camera_action_frame(
                            args.address,
                            action_packet.action,
                            action_packet.value,
                        )
                    except ValueError as error:
                        print(
                            f"Rejected camera action sender={sender} "
                            f"action={action_packet.action.name} "
                            f"value={action_packet.value} error={error}"
                        )
                        continue
                    camera.send(action_frame)
                    if (
                        action_packet.action
                        == CameraAction.SET_ZOOM_POSITION
                    ):
                        last_zoom_position_request = action_packet.value
                    print(
                        f"TX {action_packet.action.name} "
                        f"sender={sender} value={action_packet.value} "
                        f"frame={action_frame.to_bytes().hex()}"
                    )
                    continue
                active_channels = list(decoded.channels_us)
                active_control = channels_to_control(active_channels)
                last_control_update = now
                last_control_sender = sender

            control_age_ms = (
                (now - last_control_update) * 1000
                if last_control_update
                else None
            )
            control_live = (
                control_age_ms is not None
                and control_age_ms < args.failsafe_ms
            )
            selected_control = (
                active_control
                if control_live
                else channels_to_control(neutral_channels)
            )

            if now - last_control_send >= control_period:
                control_frame = standard_control(
                    args.address,
                    pan=selected_control.pan,
                    tilt=selected_control.tilt,
                    zoom=selected_control.zoom,
                    focus=selected_control.focus,
                )
                control_commands = control_command_names(selected_control)
                control_changed = control_commands != last_control_commands
                zoom_active = any(
                    command.startswith("ZOOM_")
                    for command in control_commands
                )
                if control_changed or zoom_active:
                    print(
                        f"TX {'+'.join(control_commands)} "
                        f"joystick_pan={selected_control.pan:.3f} "
                        f"joystick_tilt={selected_control.tilt:.3f} "
                        f"zoom_direction={selected_control.zoom} "
                        f"focus_step={selected_control.focus} "
                        f"frame={control_frame.to_bytes().hex()}"
                    )
                    last_control_commands = control_commands
                if (
                    control_frame != last_control_frame
                    or (
                        control_live
                        and continuous_control_active(selected_control)
                    )
                ):
                    camera.send(control_frame)
                    last_control_frame = control_frame
                    if args.debug:
                        print(
                            f"CTRL state={'live' if control_live else 'failsafe'} "
                            f"sender={last_control_sender} age_ms={control_age_ms} "
                            f"pan={selected_control.pan:.3f} "
                            f"tilt={selected_control.tilt:.3f} "
                            f"zoom={selected_control.zoom} "
                            f"focus={selected_control.focus} "
                            f"tx={control_frame.to_bytes().hex()}"
                        )
                last_control_send = now

            if now >= next_query:
                query_name, telemetry_name, query = query_schedule[query_index]
                try:
                    telemetry[telemetry_name] = query()
                    telemetry_updated[telemetry_name] = time.time()
                except PelcoTimeoutError as error:
                    query_errors[query_name] += 1
                    if args.debug:
                        print(f"TEL query={query_name} error={error}")
                query_index = (query_index + 1) % len(query_schedule)
                if (
                    query_index == 0
                    and all(value is not None for value in telemetry.values())
                ):
                    position_log = (
                        round(telemetry["pan_deg"], 2),
                        round(telemetry["tilt_deg"], 2),
                        telemetry["zoom_position"],
                    )
                    if position_log != last_position_log:
                        print(
                            f"MEASURED pan_deg={position_log[0]:.2f} "
                            f"tilt_deg={position_log[1]:.2f} "
                            f"zoom_position={position_log[2]}"
                        )
                        last_position_log = position_log
                next_query = time.monotonic() + query_period

            if now - last_telemetry_send >= telemetry_period:
                message = {
                    "timestamp": time.time(),
                    "address": args.address,
                    "link": {
                        "responding": any(
                            updated is not None
                            and time.time() - updated < 2 / args.telemetry_rate
                            for updated in telemetry_updated.values()
                        ),
                        "query_errors": query_errors,
                        "updated": telemetry_updated,
                    },
                    "measured": telemetry,
                    "commanded": {
                        "pan": selected_control.pan,
                        "tilt": selected_control.tilt,
                        "zoom": selected_control.zoom,
                        "zoom_position": last_zoom_position_request,
                        "focus": selected_control.focus,
                    },
                    "control": {
                        "state": "live" if control_live else "failsafe",
                        "sender": (
                            f"{last_control_sender[0]}:{last_control_sender[1]}"
                            if last_control_sender
                            else None
                        ),
                        "age_ms": control_age_ms,
                    },
                }
                payload = json.dumps(
                    message,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode()
                for target in args.telemetry_udp:
                    telemetry_socket.sendto(payload, target)
                if args.debug:
                    print(f"TEL {payload.decode()}")
                last_telemetry_send = now

            elapsed = time.monotonic() - loop_started
            if elapsed < loop_period:
                time.sleep(loop_period - elapsed)
    except KeyboardInterrupt:
        print("Shutdown requested.")
    finally:
        try:
            camera.send(stop(args.address))
        finally:
            telemetry_socket.close()
            control_socket.close()
            camera.close()


if __name__ == "__main__":
    main()
