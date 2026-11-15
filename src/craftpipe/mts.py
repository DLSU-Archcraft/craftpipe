"""Luanti schematic (.mts) version 4."""

from __future__ import annotations

import struct
import zlib
from typing import Sequence

from .errors import CraftpipeError

MAGIC = b"MTSM"
VERSION = 4
ALWAYS_PLACE = 127


def index(size, x: int, y: int, z: int) -> int:
    """Position of a node in the .mts arrays (x fastest, then y, then z)."""
    return (z * size[1] + y) * size[0] + x


def write_mts(path, size, names: Sequence[str], node_ids: Sequence[int], param2: Sequence[int]) -> None:
    sx, sy, sz = size
    if not all(1 <= v <= 0xFFFF for v in (sx, sy, sz)):
        raise CraftpipeError(
            f"schematic size {sx}x{sy}x{sz} is outside what .mts can store (1 to 65535 per axis)")
    volume = sx * sy * sz
    if len(node_ids) != volume or len(param2) != volume:
        raise CraftpipeError("node data does not match the schematic size")
    if len(names) > 0xFFFF:
        raise CraftpipeError("too many distinct node names for .mts")
    head = bytearray(MAGIC)
    head += struct.pack(">HHHH", VERSION, sx, sy, sz)
    head += bytes([ALWAYS_PLACE]) * sy
    head += struct.pack(">H", len(names))
    for name in names:
        raw = name.encode("utf-8")
        head += struct.pack(">H", len(raw)) + raw
    body = struct.pack(f">{volume}H", *node_ids) + bytes([ALWAYS_PLACE]) * volume + bytes(param2)
    with open(path, "wb") as fh:
        fh.write(bytes(head) + zlib.compress(body, 9))


def read_mts(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != MAGIC:
        raise CraftpipeError("not an .mts file")
    version, sx, sy, sz = struct.unpack(">HHHH", data[4:12])
    if version != VERSION:
        raise CraftpipeError(f".mts version {version} is not supported")
    pos = 12 + sy
    (count,) = struct.unpack(">H", data[pos:pos + 2])
    pos += 2
    names = []
    for _ in range(count):
        (length,) = struct.unpack(">H", data[pos:pos + 2])
        names.append(data[pos + 2:pos + 2 + length].decode("utf-8"))
        pos += 2 + length
    body = zlib.decompress(data[pos:])
    volume = sx * sy * sz
    node_ids = list(struct.unpack(f">{volume}H", body[:volume * 2]))
    param2 = list(body[volume * 3:volume * 4])
    return (sx, sy, sz), names, node_ids, param2
