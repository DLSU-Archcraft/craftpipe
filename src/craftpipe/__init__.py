"""craftpipe: Minecraft redstone schematics to Mineclonia."""

from __future__ import annotations

import hashlib
import json
import os
import re

__version__ = "0.1.0"

from .errors import CraftpipeError, UnmappedBlocksError, UnsupportedFormatError  # noqa: E402
from .grid import BlockState, VoxelGrid  # noqa: E402


def output_paths(input_path, output_path=None) -> tuple[str, str]:
    """(.mts path, manifest path) for a conversion."""
    if output_path is None:
        output_path = os.path.splitext(os.fspath(input_path))[0] + ".mts"
    output_path = os.fspath(output_path)
    return output_path, os.path.splitext(output_path)[0] + ".craftpipe.json"


def convert(input_path, output_path=None, *, allow_unmapped: bool = False):
    """Convert a .litematic/.schem file; writes the .mts and its manifest.

    Returns the Conversion. Raises UnmappedBlocksError (nothing written)
    when a block has no mapping and allow_unmapped is false.
    """
    from . import mapper, mts
    from .reader import read_schematic

    grid = read_schematic(input_path)
    conv = mapper.map_grid(grid, allow_unmapped=allow_unmapped,
                           source=os.path.basename(os.fspath(input_path)))
    mts_path, manifest_path = output_paths(input_path, output_path)
    os.makedirs(os.path.dirname(os.path.abspath(mts_path)), exist_ok=True)
    mts.write_mts(mts_path, conv.size, conv.names, conv.node_ids, conv.param2)
    with open(mts_path, "rb") as fh:
        conv.manifest["mts_sha1"] = hashlib.sha1(fh.read()).hexdigest()
    stem = os.path.splitext(os.path.basename(mts_path))[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", stem):
        conv.report.warn(
            f"the file name '{stem}' cannot be used with /craftpipe_place, which accepts only "
            "letters, digits, _ and -; rename both output files (keeping the same base name)")
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(conv.manifest, fh, indent=1)
        fh.write("\n")
    return conv


__all__ = ["convert", "output_paths", "BlockState", "VoxelGrid", "CraftpipeError",
           "UnmappedBlocksError", "UnsupportedFormatError", "__version__"]
