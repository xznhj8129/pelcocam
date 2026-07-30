# pelcocam

Pelco-D camera control with one serial owner, concurrent UDP input clients, and
continuous camera telemetry.

This project is tested with a Costar CDC2450MT configured for Pelco-P/D,
9600 baud, address 1. The camera successfully answered the standard Pelco-D
pan, tilt, and zoom position queries while it was moving.

## Architecture

```text
joystickcmd.py ─┐
                ├─ UDP control/actions ─> pelco_server.py ─> RS-485 camera
trackcmd.py ────┘                              │
                                              └─ JSON/UDP telemetry
```

Only `pelco_server.py` opens the serial device. Input clients can start and stop
without contending for RS-485, and the most recently received valid UDP packet
controls the camera. Motion stops after 500 ms without a valid packet by
default.

`libpelco.py` is the definitive Pelco-D implementation. It provides validated
seven-byte framing, the complete Pelco-D command set, all three response
formats, and the serial transport. It covers standard PTZ/lens/power/scan
control; presets, auxiliaries, zones, patterns, labels, alarms, and camera
modes; image adjustments; device identification; absolute positions; and
magnification.

## Installation

Python 3.10 or newer is recommended.

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
```

`pygame` is required by the joystick clients. `pyserial` is required by the
server and library. `simple-pid` is additionally required by `trackcmd.py`.

## Server

Start the serial owner first:

```bash
python3 pelco_server.py \
    --device /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \
    --baud 9600 \
    --address 1 \
    --host 0.0.0.0 \
    --port 60000 \
    --telemetry-udp 127.0.0.1:60001
```

The serial device, baud, camera address, control bind address, control port,
rates, and failsafe are all command-line arguments. Run
`python3 pelco_server.py --help` for the complete list. More than one
`--telemetry-udp HOST:PORT` may be supplied.

To inspect telemetry locally with `socat`:

```bash
socat -u UDP-RECV:60001 -
```

`TX` lines report commands sent to the camera. Their `joystick_pan` and
`joystick_tilt` values are normalized joystick inputs, not camera positions.
Small nonzero values can appear at stick center; values inside the deadband
produce `TX STOP`. Focus prints once on press and STOP once on release. While
zoom is held, every transmitted zoom frame is printed.

`MEASURED` lines report queried camera state in degrees and native zoom units.
They print when the rounded pan, tilt, or zoom position changes. `--debug`
additionally prints every accepted control state and complete telemetry
message; it is intentionally verbose.

## Joystick client

```bash
python3 joystickcmd.py \
    --target 127.0.0.1 \
    --port 60000 \
    --rate 50 \
    --joystick-index 0
```

The input mapping and UDP packet are compatible with
`crsfproxy/joystick_crsf.py`. RadioMaster/TX12 devices use their first eight
axes directly. Other gamepads use the same four-axis and latched-button mapping
as the CRSF client.

The original gamepad map, recovered from the old joystick scripts, is:

| Physical control | Pygame index | Array index | Camera function |
| --- | ---: | ---: | --- |
| Left stick horizontal | axis 0 | 3 | Pan |
| Left stick vertical | axis 1 | 2 | Tilt |
| A | button 0 | 5 | Unused by this camera |
| C | button 2 | 7 | Open iris |
| D | button 3 | 8 | Toggle night mode; also reset tracker |
| Near LT | button 4 | 9 | Zoom wide while held |
| Near RT | button 5 | 10 | One focus-near step per press-release |
| Far LT | button 6 | 11 | Zoom tele while held |
| Far RT | button 7 | 12 | One focus-far step per press-release |
| Start | button 9 | — | Open camera system menu |

The tested camera does not use A as a working autofocus/manual toggle. Pressing
either focus button enters manual focus itself. A focus command followed by
STOP on release advances one focus step, so repeated press-release cycles are
required. Near LT and Far LT issue continuous zoom-direction commands for as
long as they are held.

B, Select, and the two stick clicks remain unused. In `trackcmd.py`, D performs
both its original night-mode toggle and tracker reset. Far RT is reserved for
tracker lock, so that client does not also move focus far. The right stick axes
remain tracker inputs.

SDL/Pygame mappings can differ by controller. To see the actual zero-based raw
indexes, run:

```bash
python3 joystickcmd.py --target 127.0.0.1 --debugch
```

The debug line includes `axes`, `buttons`, and the resulting `channels`. Stop
`pelco_server.py` first if you only want to identify controls without commanding
the camera.

## Tracking client

`trackcmd.py` combines the same joystick mapping with MCVST tracking:

```bash
python3 trackcmd.py \
    --target 127.0.0.1 \
    --port 60000 \
    --tracker-host 127.0.0.1 \
    --tracker-output-port 8100 \
    --tracker-input-port 8101
```

It preserves the existing MCVST interfaces: port 8100 receives `x` and returns
tracking JSON; port 8101 receives newline-delimited command JSON and returns a
one-byte acknowledgement. While locked, PID output replaces the pan and tilt
channels. Gamepad button 7 remains the MCVST lock button; its shared focus-far
channel is neutralized by this client so locking cannot move focus.

## UDP control protocol

Continuous control datagrams remain exactly 40 bytes, little-endian:

```text
<uint32 timestamp_ms><16 × uint16 channel_us><uint32 crc32>
```

The CRC32 covers the first 36 bytes. Channel values normally span 900–2100 µs
with 1500 µs neutral. A malformed length or CRC is rejected. This is the same
wire format emitted by `crsfproxy/joystick_crsf.py`.

One-shot camera actions use a separate 18-byte packet:

```text
<"PCAM"><uint8 version><uint8 action><uint32 event_id><int32 value><uint32 crc32>
```

Actions currently cover opening the menu, opening the iris, selecting the
camera-specific night mode, and setting absolute zoom position. Clients repeat
each action packet three times; the server deduplicates `event_id`, retaining
one execution while reducing the chance that a single dropped UDP datagram
loses a button command.

There is deliberately no per-client serial session. Any number of producers
may send packets, with latest valid packet winning. Applications that require
authority or priority should put that policy in a single upstream producer.

## Telemetry

The server polls one of pan, tilt, and zoom each cycle and publishes a JSON
snapshot at `--telemetry-rate`. A typical message is:

```json
{
  "timestamp": 1785362051.7492528,
  "address": 1,
  "link": {
    "responding": true,
    "query_errors": {"pan": 0, "tilt": 0, "zoom": 0},
    "updated": {
      "pan_deg": 1785362051.6174958,
      "tilt_deg": 1785362051.7089028,
      "zoom_position": 1785362051.5258706
    }
  },
  "measured": {
    "pan_deg": 245.4,
    "tilt_deg": 2.3,
    "zoom_position": 0
  },
  "commanded": {
    "pan": 0.0,
    "tilt": 0.0,
    "zoom": 0,
    "zoom_position": null,
    "focus": 0
  },
  "control": {
    "state": "live",
    "sender": "127.0.0.1:56457",
    "age_ms": 14.2
  }
}
```

Standard Pelco-D provides unambiguous position replies for pan, tilt, and zoom.
Opcodes `0x5F`/`0x61`/`0x63` are dialect-dependent: revision 2.1 calls them
magnification while the command sheet in this repository calls them focus
position. The server therefore does not present focus as measured telemetry
without a confirmed device interpretation. Standard Pelco-D also does not
define queries for exposure, iris, or autofocus state. The requested focus
step direction is included under `commanded`.

## Library example

Read the three supported position values without running the server:

```bash
python3 example_pelco.py \
    --port /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0 \
    --baud 9600 \
    --address 1
```

Do not run this at the same time as `pelco_server.py`; both would own the same
serial link.

`libpelco.py` exposes snake-case constructors returning validated `Frame`
objects. Representative calls are:

```python
from libpelco import (
    AutoMode,
    adjust_gain,
    query_device,
    run_pattern,
    set_focus_mode,
    set_pan_position,
    write_preset_label,
)

frames = [
    set_pan_position(1, 45.0),
    set_focus_mode(1, AutoMode.AUTO),
    run_pattern(1, 2),
    write_preset_label(1, 0, ord("A")),
    adjust_gain(1, 0x1234, bank=1),
    query_device(1),
]
```

The serial owner can send any command frame with `PelcoCamera.send()`.
`PelcoCamera.query_pan()`, `query_tilt()`, `query_zoom()`, `query_focus()`,
`query_magnification()`, and `query_device_info()` parse their corresponding
responses. Pelco-D revision 2.1 defines opcodes `0x5F`/`0x61`/`0x63` as
magnification, while the camera command sheet in this repository defines those
same opcodes as focus position. Both explicit interpretations are available;
the device determines which one applies.

## Camera setup and wiring

For the tested CDC2450MT:

- Select Pelco-P/D, 9600 baud, and camera ID 001.
- Connect the camera’s differential TX pair to the USB RS-485 adapter A/B pair.
  Adapter labeling is inconsistent, so reverse A/B if the camera does not move
  or answer.
- Connect the signal reference/ground when the adapter and camera provide it.
- Check for shorts or stray strands between the differential conductors.

`DOME ANSWER` in the camera system menu enables protocol acknowledgements and
query replies. It is required for telemetry, but ordinary movement commands do
not depend on a reply.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
