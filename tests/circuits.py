"""Build small redstone circuits as Minecraft schematics for the tests.

Coordinates are Minecraft's (+X east, +Y up, +Z south). Every circuit
gets a stone floor at y=0, so components start at y=1.
"""

from __future__ import annotations

import os

from craftpipe import litematic, schem
from craftpipe.grid import BlockState, VoxelGrid

FLOOR = "minecraft:stone"
LAMP = "minecraft:redstone_lamp[lit=false]"
DUST = "minecraft:redstone_wire[east=none,north=none,power=0,south=none,west=none]"


class Circuit:
    def __init__(self, size):
        self.grid = VoxelGrid(size)
        self.inputs: dict[str, tuple[int, int, int]] = {}
        self.outputs: dict[str, tuple[int, int, int]] = {}
        sx, _, sz = size
        self.fill(0, 0, 0, sx - 1, 0, sz - 1, FLOOR)

    @property
    def size(self):
        return self.grid.size

    def block(self, x, y, z, state: str) -> "Circuit":
        self.grid.set(x, y, z, BlockState.parse(state))
        return self

    def fill(self, x0, y0, z0, x1, y1, z1, state: str) -> "Circuit":
        parsed = BlockState.parse(state)
        for x in range(min(x0, x1), max(x0, x1) + 1):
            for y in range(min(y0, y1), max(y0, y1) + 1):
                for z in range(min(z0, z1), max(z0, z1) + 1):
                    self.grid.set(x, y, z, parsed)
        return self

    def dust(self, *positions) -> "Circuit":
        for x, y, z in positions:
            self.block(x, y, z, DUST)
        return self

    def dust_line(self, x0, y, z0, x1, z1) -> "Circuit":
        return self.fill(x0, y, z0, x1, y, z1, DUST)

    def input(self, name: str, pos, state: str | None = None) -> "Circuit":
        """A lever (on the floor unless ``state`` says otherwise)."""
        self.block(*pos, state or "minecraft:lever[face=floor,facing=north,powered=false]")
        self.inputs[name] = tuple(pos)
        return self

    def output(self, name: str, pos, state: str = LAMP) -> "Circuit":
        self.block(*pos, state)
        self.outputs[name] = tuple(pos)
        return self

    def probe(self, name: str, pos) -> "Circuit":
        """Read whatever is at pos without placing anything."""
        self.outputs[name] = tuple(pos)
        return self

    def save(self, path) -> None:
        if os.fspath(path).endswith(".litematic"):
            litematic.write_litematic(self.grid, path)
        else:
            schem.write_schem(self.grid, path)
