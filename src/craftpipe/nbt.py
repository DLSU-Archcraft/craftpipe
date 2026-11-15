"""Minimal NBT (Java Edition, big-endian) reader and writer.

Values are plain Python objects, but numbers and arrays use the small
subclasses below so that a value read from a file can be written back
with the same tag types.
"""

from __future__ import annotations

import gzip
import struct
import zlib

from .errors import UnsupportedFormatError


class Byte(int): pass
class Short(int): pass
class Int(int): pass
class Long(int): pass
class Float(float): pass
class Double(float): pass
class ByteArray(list): pass
class IntArray(list): pass
class LongArray(list): pass


TAG_END, TAG_BYTE, TAG_SHORT, TAG_INT, TAG_LONG, TAG_FLOAT, TAG_DOUBLE = range(7)
TAG_BYTE_ARRAY, TAG_STRING, TAG_LIST, TAG_COMPOUND, TAG_INT_ARRAY, TAG_LONG_ARRAY = range(7, 13)

_SCALARS = {
    TAG_BYTE: (Byte, ">b"),
    TAG_SHORT: (Short, ">h"),
    TAG_INT: (Int, ">i"),
    TAG_LONG: (Long, ">q"),
    TAG_FLOAT: (Float, ">f"),
    TAG_DOUBLE: (Double, ">d"),
}
_ARRAYS = {
    TAG_BYTE_ARRAY: (ByteArray, "b"),
    TAG_INT_ARRAY: (IntArray, "i"),
    TAG_LONG_ARRAY: (LongArray, "q"),
}
_MAX_DEPTH = 512


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise UnsupportedFormatError("NBT data is truncated")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def unpack(self, fmt: str):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def string(self) -> str:
        return self.take(self.unpack(">H")).decode("utf-8", errors="replace")

    def payload(self, tag: int, depth: int = 0):
        if depth > _MAX_DEPTH:
            raise UnsupportedFormatError("NBT data is nested too deeply")
        if tag in _SCALARS:
            cls, fmt = _SCALARS[tag]
            return cls(self.unpack(fmt))
        if tag in _ARRAYS:
            cls, code = _ARRAYS[tag]
            n = self.unpack(">i")
            size = struct.calcsize(code)
            raw = self.take(n * size) if n >= 0 else self.take(-1)
            return cls(struct.unpack(f">{n}{code}", raw))
        if tag == TAG_STRING:
            return self.string()
        if tag == TAG_LIST:
            inner = self.unpack(">b")
            n = self.unpack(">i")
            if n > 0 and inner == TAG_END:
                raise UnsupportedFormatError("NBT list has no element type")
            if n > len(self.data) - self.pos:
                raise UnsupportedFormatError("NBT data is truncated")
            return [self.payload(inner, depth + 1) for _ in range(max(n, 0))]
        if tag == TAG_COMPOUND:
            out = {}
            while True:
                inner = self.unpack(">b")
                if inner == TAG_END:
                    return out
                key = self.string()
                out[key] = self.payload(inner, depth + 1)
        raise UnsupportedFormatError(f"unknown NBT tag type {tag}")


def loads(data: bytes) -> tuple[str, dict]:
    """Parse NBT bytes (gzip-compressed or raw). Returns (root name, root compound)."""
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError, zlib.error) as exc:
            raise UnsupportedFormatError(f"cannot decompress file: {exc}") from None
    reader = _Reader(data)
    if not data or data[0] != TAG_COMPOUND:
        raise UnsupportedFormatError("not an NBT file (no root compound)")
    reader.pos = 1
    name = reader.string()
    return name, reader.payload(TAG_COMPOUND)


def load(path) -> tuple[str, dict]:
    with open(path, "rb") as fh:
        return loads(fh.read())


def _tag_of(value) -> int:
    for tag, (cls, _) in {**_SCALARS, **_ARRAYS}.items():
        if type(value) is cls:
            return tag
    if isinstance(value, str):
        return TAG_STRING
    if isinstance(value, dict):
        return TAG_COMPOUND
    if isinstance(value, list):
        return TAG_LIST
    raise TypeError(f"cannot write {type(value).__name__} as NBT; wrap it in an nbt tag type")


def _write_string(out: bytearray, s: str) -> None:
    raw = s.encode("utf-8")
    out += struct.pack(">H", len(raw)) + raw


def _write(out: bytearray, value) -> None:
    tag = _tag_of(value)
    if tag in _SCALARS:
        out += struct.pack(_SCALARS[tag][1], value)
    elif tag in _ARRAYS:
        out += struct.pack(">i", len(value))
        out += struct.pack(f">{len(value)}{_ARRAYS[tag][1]}", *value)
    elif tag == TAG_STRING:
        _write_string(out, value)
    elif tag == TAG_LIST:
        inner = _tag_of(value[0]) if value else TAG_END
        out += struct.pack(">bi", inner, len(value))
        for item in value:
            if _tag_of(item) != inner:
                raise TypeError("NBT lists must hold a single tag type")
            _write(out, item)
    else:
        for key, item in value.items():
            out += struct.pack(">b", _tag_of(item))
            _write_string(out, key)
            _write(out, item)
        out.append(TAG_END)


def dumps(root: dict, name: str = "", gzipped: bool = True) -> bytes:
    out = bytearray([TAG_COMPOUND])
    _write_string(out, name)
    _write(out, root)
    return gzip.compress(bytes(out)) if gzipped else bytes(out)
