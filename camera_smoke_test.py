#!/usr/bin/env python3
"""Usage:
    python3 camera_smoke_test.py --port /dev/ttyUSB0 --address 1 --menu

Exercises a connected Pelco-D camera, restores the original zoom position,
leaves night mode off, and optionally opens the system menu as the final step.
"""

import argparse
import time

from libpelco import (
    PelcoCamera,
    iris_open,
    set_extended_preset,
    set_preset,
    set_zoom_position,
    stop,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run non-destructive Pelco-D camera hardware checks."
    )
    parser.add_argument("--port", required=True, help="camera serial device")
    parser.add_argument("--baud", type=int, default=9600, help="serial baud rate")
    parser.add_argument("--address", type=int, default=1, help="camera address")
    parser.add_argument(
        "--menu",
        action="store_true",
        help="open the camera system menu as the final test",
    )
    parser.add_argument(
        "--restore-zoom",
        type=int,
        help="restore this zoom position instead of the initial measurement",
    )
    args = parser.parse_args()

    camera = PelcoCamera.open(args.port, args.baud, args.address)
    try:
        pan = camera.query_pan()
        tilt = camera.query_tilt()
        original_zoom = camera.query_zoom()
        print(
            f"QUERY pan_deg={pan:.2f} tilt_deg={tilt:.2f} "
            f"zoom_position={original_zoom}"
        )

        test_zoom = (
            original_zoom + 100
            if original_zoom <= 65435
            else original_zoom - 100
        )
        camera.send(set_zoom_position(args.address, test_zoom))
        time.sleep(0.5)
        measured_zoom = camera.query_zoom()
        print(
            f"ZOOM requested={test_zoom} measured={measured_zoom} "
            f"original={original_zoom}"
        )
        restore_zoom = (
            args.restore_zoom
            if args.restore_zoom is not None
            else original_zoom
        )
        camera.send(set_zoom_position(args.address, restore_zoom))
        time.sleep(0.5)
        restored_zoom = camera.query_zoom()
        print(
            f"ZOOM_RESTORE requested={restore_zoom} "
            f"measured={restored_zoom}"
        )

        camera.send(iris_open(args.address))
        camera.send(stop(args.address))
        print("IRIS_OPEN transmitted=true")

        camera.send(set_extended_preset(args.address, 888))
        print("NIGHT_MODE enabled=true transmitted=true")
        camera.send(set_extended_preset(args.address, 999))
        print("NIGHT_MODE enabled=false transmitted=true")

        if args.menu:
            camera.send(set_preset(args.address, 95))
            print("MENU_OPEN transmitted=true")
    finally:
        camera.close()


if __name__ == "__main__":
    main()
