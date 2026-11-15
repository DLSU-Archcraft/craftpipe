"""Sponge schematic (.schem) versions 2 and 3."""

from __future__ import annotations

from . import nbt
from .errors import UnsupportedFormatError
from .grid import BlockState, VoxelGrid, check_data_version, check_size

DEFAULT_DATA_VERSION = 3953  # Java Edition 1.21


def _decode_varints(raw, expected: int) -> list[int]:
    out = []
    value = shift = 0
    for byte in raw:
        byte &= 0xFF
        value |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            if shift > 35:
                raise UnsupportedFormatError("schematic block data is corrupt")
        else:
            out.append(value)
            value = shift = 0
    if shift or len(out) != expected:
        raise UnsupportedFormatError(
            f"schematic block data has {len(out)} entries, expected {expected}")
    return out


def _encode_varints(values) -> nbt.ByteArray:
    out = []
    for value in values:
        while True:
            byte = value & 0x7F
            value >>= 7
            if value:
                out.append((byte | 0x80) - 256)
            else:
                out.append(byte)
                break
    return nbt.ByteArray(out)


def read_schem(root_name: str, root: dict) -> VoxelGrid:
    if isinstance(root.get("Schematic"), dict):
        root = root["Schematic"]
    try:
        version = int(root["Version"])
        if version == 2:
            palette, data = root["Palette"], root["BlockData"]
            entities = root.get("BlockEntities", [])
        elif version == 3:
            blocks = root["Blocks"]
            palette, data = blocks["Palette"], blocks["Data"]
            entities = blocks.get("BlockEntities", [])
        else:
            raise UnsupportedFormatError(
                f"Sponge schematic version {version} is not supported (only 2 and 3)")
        size = (int(root["Width"]) & 0xFFFF, int(root["Height"]) & 0xFFFF, int(root["Length"]) & 0xFFFF)
        data_version = int(root["DataVersion"]) if "DataVersion" in root else None
        check_data_version(data_version)
        check_size(size)
        grid = VoxelGrid(size)
        grid.data_version = data_version
        states = {int(idx): BlockState.parse(text) for text, idx in palette.items()}
        ids = _decode_varints(data, size[0] * size[1] * size[2])
        remap = {idx: grid._palette_id(state) for idx, state in states.items()}
        cells = grid._cells
        for i, idx in enumerate(ids):
            cells[i] = remap[idx]
        for entity in entities:
            pos = tuple(int(v) for v in entity["Pos"])
            grid._index(*pos)
            if version == 3:
                data_part = dict(entity.get("Data", {}))
            else:
                data_part = {k: v for k, v in entity.items() if k not in ("Pos", "Id")}
            data_part.pop("id", None)
            grid.block_entities[pos] = {"id": str(entity.get("Id", "")), **data_part}
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        raise UnsupportedFormatError(f"Sponge schematic is malformed: {exc!r}") from None
    return grid


def write_schem(grid: VoxelGrid, path, version: int = 3, data_version: int = DEFAULT_DATA_VERSION) -> None:
    if version not in (2, 3):
        raise ValueError("version must be 2 or 3")
    palette = {str(state): nbt.Int(i) for i, state in enumerate(grid._palette)}
    data = _encode_varints(grid._cells)
    sx, sy, sz = grid.size
    entities = []
    for pos, entity in sorted(grid.block_entities.items()):
        body = {k: v for k, v in entity.items() if k != "id"}
        entry = {"Pos": nbt.IntArray(pos), "Id": str(entity.get("id", ""))}
        if version == 3:
            entry["Data"] = body
        else:
            entry.update(body)
        entities.append(entry)
    def short(v):
        return nbt.Short(v - 65536 if v > 32767 else v)
    head = {
        "Version": nbt.Int(version),
        "DataVersion": nbt.Int(data_version),
        "Width": short(sx), "Height": short(sy), "Length": short(sz),
    }
    if version == 2:
        root = {**head, "PaletteMax": nbt.Int(len(palette)), "Palette": palette,
                "BlockData": data, "BlockEntities": entities}
        blob = nbt.dumps(root, name="Schematic")
    else:
        root = {"Schematic": {**head, "Blocks": {
            "Palette": palette, "Data": data, "BlockEntities": entities}}}
        blob = nbt.dumps(root, name="")
    with open(path, "wb") as fh:
        fh.write(blob)
