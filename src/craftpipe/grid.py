"""Block states and the voxel grid every reader produces.

Coordinates are (x, y, z). A grid read from a Minecraft file is in
Minecraft's orientation (+Z south); ``mirror_z`` returns the same build
in Luanti's orientation (+Z north).
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass
from typing import Iterator

Pos = tuple[int, int, int]

MAX_AXIS = 65535            # what .mts can store
MAX_VOLUME = 50_000_000     # cells; keeps a hostile file from exhausting memory
FLATTENING_DATA_VERSION = 1451   # Java 1.13 (17w47a): namespaced block states
CROSS_DUST_DATA_VERSION = 2566   # Java 1.16: unconnected dust is stored as cross or dot


def check_size(size) -> None:
    """Raise UnsupportedFormatError for sizes no real build has."""
    from .errors import UnsupportedFormatError
    sx, sy, sz = size
    if min(sx, sy, sz) < 1:
        raise UnsupportedFormatError(f"schematic has an empty or negative size {sx}x{sy}x{sz}")
    if max(sx, sy, sz) > MAX_AXIS or sx * sy * sz > MAX_VOLUME:
        raise UnsupportedFormatError(
            f"schematic is too large ({sx}x{sy}x{sz}); the limit is {MAX_AXIS} per axis "
            f"and {MAX_VOLUME:,} blocks in total")


def check_data_version(version) -> None:
    from .errors import UnsupportedFormatError
    if version is not None and version < FLATTENING_DATA_VERSION:
        raise UnsupportedFormatError(
            f"schematic was saved by a Minecraft version before 1.13 (data version {version}); "
            "its block names and states are not supported")


@dataclass(frozen=True)
class BlockState:
    name: str
    props: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        name = self.name if ":" in self.name else "minecraft:" + self.name
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "props", tuple(sorted((str(k), str(v)) for k, v in self.props)))

    @classmethod
    def parse(cls, text: str) -> "BlockState":
        text = text.strip()
        if "[" not in text:
            return cls(text)
        name, _, rest = text.partition("[")
        props = []
        for part in rest.rstrip("]").split(","):
            if part.strip():
                key, _, value = part.partition("=")
                props.append((key.strip(), value.strip()))
        return cls(name, tuple(props))

    def get(self, key: str, default: str | None = None) -> str | None:
        for k, v in self.props:
            if k == key:
                return v
        return default

    def with_props(self, **changes: str) -> "BlockState":
        merged = dict(self.props)
        merged.update(changes)
        return BlockState(self.name, tuple(merged.items()))

    def __str__(self) -> str:
        if not self.props:
            return self.name
        return self.name + "[" + ",".join(f"{k}={v}" for k, v in self.props) + "]"


AIR = BlockState("minecraft:air")

_SWAP_VALUES = {
    "facing": {"north": "south", "south": "north"},
    "type": {"left": "right", "right": "left"},
    "hinge": {"left": "right", "right": "left"},
    "shape": {
        "inner_left": "inner_right", "inner_right": "inner_left",
        "outer_left": "outer_right", "outer_right": "outer_left",
    },
}
_SWAP_KEYS = {"north": "south", "south": "north"}


def mirror_state(state: BlockState) -> BlockState:
    """The block state as seen after mirroring the world along Z."""
    if not state.props:
        return state
    out = []
    for key, value in state.props:
        value = _SWAP_VALUES.get(key, {}).get(value, value)
        out.append((_SWAP_KEYS.get(key, key), value))
    return BlockState(state.name, tuple(out))


class VoxelGrid:
    def __init__(self, size: Pos):
        sx, sy, sz = (int(v) for v in size)
        if min(sx, sy, sz) < 1:
            raise ValueError(f"grid size must be positive, got {size}")
        self.size: Pos = (sx, sy, sz)
        self._palette: list[BlockState] = [AIR]
        self._lookup: dict[BlockState, int] = {AIR: 0}
        self._cells = array("I", bytes(array("I").itemsize * sx * sy * sz))
        self.block_entities: dict[Pos, dict] = {}
        self.data_version: int | None = None    # Minecraft data version of the source file

    def _index(self, x: int, y: int, z: int) -> int:
        sx, sy, sz = self.size
        if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
            raise IndexError(f"position {(x, y, z)} is outside grid of size {self.size}")
        return (y * sz + z) * sx + x

    def _palette_id(self, state: BlockState) -> int:
        idx = self._lookup.get(state)
        if idx is None:
            idx = len(self._palette)
            self._palette.append(state)
            self._lookup[state] = idx
        return idx

    def get(self, x: int, y: int, z: int) -> BlockState:
        return self._palette[self._cells[self._index(x, y, z)]]

    def set(self, x: int, y: int, z: int, state: BlockState) -> None:
        self._cells[self._index(x, y, z)] = self._palette_id(state)

    def cells(self) -> Iterator[tuple[Pos, BlockState]]:
        """Every cell in x-fastest, then z, then y order."""
        sx, sy, sz = self.size
        palette, data = self._palette, self._cells
        i = 0
        for y in range(sy):
            for z in range(sz):
                for x in range(sx):
                    yield (x, y, z), palette[data[i]]
                    i += 1

    def counts(self) -> dict[BlockState, int]:
        tally: dict[int, int] = {}
        for idx in self._cells:
            tally[idx] = tally.get(idx, 0) + 1
        return {self._palette[i]: n for i, n in tally.items()}

    def positions(self, state: BlockState) -> Iterator[Pos]:
        target = self._lookup.get(state)
        if target is None:
            return
        for pos, _ in ((p, s) for p, s in self.cells() if s is self._palette[target]):
            yield pos

    def mirror_z(self) -> "VoxelGrid":
        sx, sy, sz = self.size
        out = VoxelGrid(self.size)
        out.data_version = self.data_version
        remap = [out._palette_id(mirror_state(s)) for s in self._palette]
        src, dst = self._cells, out._cells
        for y in range(sy):
            for z in range(sz):
                a = (y * sz + z) * sx
                b = (y * sz + (sz - 1 - z)) * sx
                for x in range(sx):
                    dst[b + x] = remap[src[a + x]]
        out.block_entities = {(x, y, sz - 1 - z): data for (x, y, z), data in self.block_entities.items()}
        return out
