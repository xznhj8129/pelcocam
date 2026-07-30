"""Usage:
    python3 example_pelco.py --port /dev/ttyUSB1 --baud 9600
"""

import argparse

from libpelco import PelcoCamera


parser = argparse.ArgumentParser(
    description="Read pan, tilt, and zoom telemetry from one Pelco-D camera."
)
parser.add_argument("--port", required=True, help="serial device")
parser.add_argument("--baud", type=int, default=9600, help="serial baud rate")
parser.add_argument("--address", type=int, default=1, help="Pelco-D camera address")
args = parser.parse_args()

camera = PelcoCamera.open(args.port, args.baud, args.address)
try:
    print(
        f"pan_deg={camera.query_pan():.2f} "
        f"tilt_deg={camera.query_tilt():.2f} "
        f"zoom_position={camera.query_zoom()}"
    )
finally:
    camera.close()
