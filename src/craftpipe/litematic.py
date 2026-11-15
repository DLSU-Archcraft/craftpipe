"""Litematica (.litematic) schematics."""

from __future__ import annotations

from . import nbt
from .errors import UnsupportedFormatError
from .grid import AIR, BlockState, VoxelGrid, check_data_version, check_size
from .schem import DEFAULT_DATA_VERSION

_MASK64 = (1 << 64) - 1


def _bits_for(palette_len: int) -> int:
    return max(2, (palette_len - 1).bit_length())


def _unpack(longs, bits: int, count: int) -> list[int]:
    """Litematica packs entries tightly; an entry may straddle two longs."""
    if len(longs) * 64 < bits * count:
        raise UnsupportedFormatError("litematic block data is shorter than its region size")
    words = [v & _MASK64 for v in longs]
    mask = (1 << bits) - 1
    out = []
    for i in range(count):
        start = i * bits
        word, offset = divmod(start, 64)
        value = words[word] >> offset
        if offset + bits > 64:
            value |= words[word + 1] << (64 - offset)
        out.append(value & mask)
    return out


def _pack(values, bits: int) -> nbt.LongArray:
    n_longs = max(1, (len(values) * bits + 63) // 64)
    out = []
    word = filled = 0                 # bits collected for the current long
    for value in values:
        word |= value << filled
        filled += bits
        if filled >= 64:
            low = word & _MASK64
            out.append(low - (1 << 64) if low >> 63 else low)
            word >>= 64
            filled -= 64
    if filled:
        out.append(word - (1 << 64) if word >> 63 else word)
    out += [0] * (n_longs - len(out))
    return nbt.LongArray(out)


def _xyz(compound) -> tuple[int, int, int]:
    return int(compound["x"]), int(compound["y"]), int(compound["z"])


def _state_from_entry(entry) -> BlockState:
    props = entry.get("Properties", {})
    return BlockState(str(entry["Name"]), tuple((k, str(v)) for k, v in props.items()))


def read_litematic(root: dict) -> VoxelGrid:
    try:
        regions = []
        for region in root["Regions"].values():
            pos, size = _xyz(region["Position"]), _xyz(region["Size"])
            if 0 in size:
                continue
            origin = tuple(p + s + 1 if s < 0 else p for p, s in zip(pos, size))
            regions.append((origin, tuple(abs(s) for s in size), region))
        if not regions:
            raise UnsupportedFormatError("litematic file contains no regions")
        lo = tuple(min(r[0][a] for r in regions) for a in range(3))
        hi = tuple(max(r[0][a] + r[1][a] for r in regions) for a in range(3))
        data_version = (int(root["MinecraftDataVersion"])
                        if "MinecraftDataVersion" in root else None)
        check_data_version(data_version)
        total = tuple(h - l for h, l in zip(hi, lo))
        check_size(total)
        grid = VoxelGrid(total)
        grid.data_version = data_version
        for origin, (sx, sy, sz), region in regions:
            palette = [_state_from_entry(e) for e in region["BlockStatePalette"]]
            ids = _unpack(region["BlockStates"], _bits_for(len(palette)), sx * sy * sz)
            ox, oy, oz = (o - l for o, l in zip(origin, lo))
            i = 0
            for y in range(sy):
                for z in range(sz):
                    for x in range(sx):
                        state = palette[ids[i]]
                        i += 1
                        if state != AIR:
                            grid.set(ox + x, oy + y, oz + z, state)
            for entity in region.get("TileEntities", []):
                ex, ey, ez = _xyz(entity)
                where = (ox + ex, oy + ey, oz + ez)
                grid._index(*where)
                body = {k: v for k, v in entity.items() if k not in ("x", "y", "z", "id")}
                grid.block_entities[where] = {"id": str(entity.get("id", "")), **body}
    except (KeyError, IndexError, ValueError, TypeError, AttributeError) as exc:
        raise UnsupportedFormatError(f"litematic file is malformed: {exc!r}") from None
    return grid


def _vec(x, y, z) -> dict:
    return {"x": nbt.Int(x), "y": nbt.Int(y), "z": nbt.Int(z)}


def write_litematic(grid_or_regions, path, data_version: int = DEFAULT_DATA_VERSION,
                    negative_size: bool = False) -> None:
    if isinstance(grid_or_regions, VoxelGrid):
        regions = [((0, 0, 0), grid_or_regions)]
    else:
        regions = list(grid_or_regions)
    out_regions = {}
    total_blocks = 0
    for n, (pos, grid) in enumerate(regions):
        sx, sy, sz = grid.size
        palette = [
            {"Name": s.name, "Properties": {k: v for k, v in s.props}} if s.props else {"Name": s.name}
            for s in grid._palette
        ]
        total_blocks += sum(c for s, c in grid.counts().items() if s != AIR)
        if negative_size:
            position = _vec(pos[0] + sx - 1, pos[1], pos[2] + sz - 1)
            size = _vec(-sx, sy, -sz)
        else:
            position, size = _vec(*pos), _vec(sx, sy, sz)
        out_regions[f"region{n}"] = {
            "Position": position,
            "Size": size,
            "BlockStatePalette": palette,
            "BlockStates": _pack(list(grid._cells), _bits_for(len(palette))),
            "TileEntities": [
                {**_vec(*p), **e} for p, e in sorted(grid.block_entities.items())
            ],
            "Entities": [],
            "PendingBlockTicks": [],
            "PendingFluidTicks": [],
        }
    first = regions[0][1].size
    root = {
        "Version": nbt.Int(6),
        "SubVersion": nbt.Int(1),
        "MinecraftDataVersion": nbt.Int(data_version),
        "Metadata": {
            "Name": "craftpipe", "Author": "craftpipe", "Description": "",
            "RegionCount": nbt.Int(len(regions)),
            "TotalBlocks": nbt.Int(total_blocks),
            "TotalVolume": nbt.Int(sum(g.size[0] * g.size[1] * g.size[2] for _, g in regions)),
            "EnclosingSize": _vec(*first),
            "TimeCreated": nbt.Long(0), "TimeModified": nbt.Long(0),
        },
        "Regions": out_regions,
    }
    with open(path, "wb") as fh:
        fh.write(nbt.dumps(root, name=""))
