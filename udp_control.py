"""Shared UDP control packet codec used by pelcocam input clients."""

from dataclasses import dataclass
from enum import IntEnum
import struct
import time
import zlib


CHANNEL_COUNT = 16
MIN_US = 900
MAX_US = 2100
MID_US = 1500
PAYLOAD_LENGTH = 4 + CHANNEL_COUNT * 2
PACKET_LENGTH = PAYLOAD_LENGTH + 4
ACTION_MAGIC = b"PCAM"
ACTION_VERSION = 1
ACTION_PAYLOAD_FORMAT = "<4sBBIi"
ACTION_PAYLOAD_LENGTH = struct.calcsize(ACTION_PAYLOAD_FORMAT)
ACTION_PACKET_LENGTH = ACTION_PAYLOAD_LENGTH + 4
ACTION_REPEAT_COUNT = 3


class CameraAction(IntEnum):
    OPEN_MENU = 1
    IRIS_OPEN = 2
    SET_NIGHT_MODE = 3
    SET_ZOOM_POSITION = 4


@dataclass(frozen=True)
class ControlPacket:
    timestamp_ms: int
    channels_us: tuple[int, ...]


@dataclass(frozen=True)
class CameraActionPacket:
    action: CameraAction
    event_id: int
    value: int


def axis_to_us(value: float) -> int:
    clamped = max(-1.0, min(1.0, float(value)))
    span = MAX_US - MIN_US
    return int(MIN_US + ((clamped + 1.0) * 0.5 * span))


def us_to_axis(value: int) -> float:
    clamped = max(MIN_US, min(MAX_US, int(value)))
    return (clamped - MID_US) / ((MAX_US - MIN_US) / 2)


def button_to_us(pressed: int) -> int:
    return MAX_US if pressed else MIN_US


def pack_control_packet(channels_us, timestamp_ms=None) -> bytes:
    if len(channels_us) != CHANNEL_COUNT:
        raise ValueError(
            f"channel_count={len(channels_us)} expected={CHANNEL_COUNT}"
        )
    if timestamp_ms is None:
        timestamp_ms = int(time.time() * 1000)
    payload = struct.pack(
        "<I16H",
        timestamp_ms & 0xFFFFFFFF,
        *(int(value) for value in channels_us),
    )
    return payload + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF)


def unpack_control_packet(packet: bytes) -> ControlPacket:
    if len(packet) != PACKET_LENGTH:
        raise ValueError(
            f"packet_length={len(packet)} expected={PACKET_LENGTH}"
        )
    payload = packet[:PAYLOAD_LENGTH]
    received_crc = struct.unpack_from("<I", packet, PAYLOAD_LENGTH)[0]
    calculated_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if received_crc != calculated_crc:
        raise ValueError(
            f"packet_crc=0x{received_crc:08x} "
            f"expected=0x{calculated_crc:08x}"
        )
    timestamp_ms, *channels_us = struct.unpack("<I16H", payload)
    return ControlPacket(timestamp_ms, tuple(channels_us))


def pack_camera_action(
    action: CameraAction,
    value: int = 0,
    event_id: int | None = None,
) -> bytes:
    if event_id is None:
        event_id = time.monotonic_ns() & 0xFFFFFFFF
    payload = struct.pack(
        ACTION_PAYLOAD_FORMAT,
        ACTION_MAGIC,
        ACTION_VERSION,
        CameraAction(action),
        event_id & 0xFFFFFFFF,
        int(value),
    )
    return payload + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF)


def unpack_camera_action(packet: bytes) -> CameraActionPacket:
    if len(packet) != ACTION_PACKET_LENGTH:
        raise ValueError(
            f"action_packet_length={len(packet)} "
            f"expected={ACTION_PACKET_LENGTH}"
        )
    payload = packet[:ACTION_PAYLOAD_LENGTH]
    received_crc = struct.unpack_from("<I", packet, ACTION_PAYLOAD_LENGTH)[0]
    calculated_crc = zlib.crc32(payload) & 0xFFFFFFFF
    if received_crc != calculated_crc:
        raise ValueError(
            f"action_packet_crc=0x{received_crc:08x} "
            f"expected=0x{calculated_crc:08x}"
        )
    magic, version, action, event_id, value = struct.unpack(
        ACTION_PAYLOAD_FORMAT,
        payload,
    )
    if magic != ACTION_MAGIC:
        raise ValueError(
            f"action_packet_magic={magic!r} expected={ACTION_MAGIC!r}"
        )
    if version != ACTION_VERSION:
        raise ValueError(
            f"action_packet_version={version} expected={ACTION_VERSION}"
        )
    try:
        decoded_action = CameraAction(action)
    except ValueError as error:
        raise ValueError(f"unknown_camera_action={action}") from error
    return CameraActionPacket(decoded_action, event_id, value)


def send_camera_action(sock, target, action: CameraAction, value: int = 0) -> None:
    packet = pack_camera_action(action, value)
    for _ in range(ACTION_REPEAT_COUNT):
        sock.sendto(packet, target)
