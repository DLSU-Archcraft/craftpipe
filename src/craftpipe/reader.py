"""Open any supported schematic file as a VoxelGrid."""

from __future__ import annotations

import os

from . import nbt
from .errors import UnsupportedFormatError
from .grid import VoxelGrid
from .litematic import read_litematic
from .schem import read_schem


def read_schematic(path) -> VoxelGrid:
    label = os.path.basename(os.fspath(path))
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise UnsupportedFormatError(f"cannot read {label}: {exc.strerror or exc}") from None
    try:
        root_name, root = nbt.loads(data)
    except UnsupportedFormatError as exc:
        raise UnsupportedFormatError(f"{label}: {exc}") from None
    except RecursionError:
        raise UnsupportedFormatError(f"{label}: NBT data is nested too deeply") from None

    try:
        if isinstance(root.get("Regions"), dict):
            return read_litematic(root)
        if isinstance(root.get("Schematic"), dict) or "Palette" in root:
            return read_schem(root_name, root)
    except UnsupportedFormatError as exc:
        raise UnsupportedFormatError(f"{label}: {exc}") from None
    if "Materials" in root or isinstance(root.get("Blocks"), nbt.ByteArray):
        raise UnsupportedFormatError(
            f"{label}: MCEdit .schematic (numeric block IDs, pre-1.13) is not supported")
    keys = ", ".join(sorted(root)[:8]) or "none"
    raise UnsupportedFormatError(
        f"{label}: not a .litematic or Sponge .schem file (top-level keys: {keys})")
