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


# --------------------------------------------------------------------------
# Dust connection states, as Java Edition (1.16+) computes and saves them.
# Real schematics carry these, and the converter relies on them, so the
# generated test inputs must too. Dust placed with all four sides "none"
# is treated as "not yet shaped" and filled in here; to save a deliberate
# dot, give the state dot=true (stripped on save).
# --------------------------------------------------------------------------

_WIRE = "minecraft:redstone_wire"
_HORIZONTAL = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
_OPP = {"north": "south", "south": "north", "east": "west", "west": "east"}
# Signal sources: dust connects to these from any side.
_SOURCES = ("minecraft:lever", "minecraft:redstone_torch", "minecraft:redstone_wall_torch",
            "minecraft:redstone_block", "minecraft:comparator", "minecraft:target",
            "minecraft:trapped_chest")
# Full opaque cubes used by the test circuits ("redstone conductors").
_CONDUCTORS = ("minecraft:stone", "minecraft:redstone_lamp", "minecraft:white_wool",
               "minecraft:redstone_block", "minecraft:target", "minecraft:dragon_egg")


def _get(grid, x, y, z):
    sx, sy, sz = grid.size
    if 0 <= x < sx and 0 <= y < sy and 0 <= z < sz:
        return grid.get(x, y, z)
    return BlockState("minecraft:air")


def _connects(state, side) -> bool:
    name = state.name
    if name == _WIRE or name in _SOURCES or name.endswith("_button"):
        return True
    if name == "minecraft:repeater":
        return state.get("facing") in (side, _OPP[side])
    return False


def _sturdy_top(state) -> bool:
    return (state.name in _CONDUCTORS or state.name == "minecraft:hopper"
            or (state.name.endswith("_slab") and state.get("type") in ("top", "double")))


def java_dust_shapes(grid: VoxelGrid) -> None:
    todo = []
    for (x, y, z), state in grid.cells():
        if state.name != _WIRE:
            continue
        if state.get("dot") == "true":
            todo.append(((x, y, z), BlockState(_WIRE, tuple(p for p in state.props if p[0] != "dot"))))
            continue
        if any(state.get(s, "none") != "none" for s in _HORIZONTAL):
            continue                                    # shaped by hand
        open_above = _get(grid, x, y + 1, z).name not in _CONDUCTORS
        sides = {}
        for side, (dx, dz) in _HORIZONTAL.items():
            beside = _get(grid, x + dx, y, z + dz)
            if _connects(beside, side):
                sides[side] = "side"
            elif open_above and _sturdy_top(beside) and _get(grid, x + dx, y + 1, z + dz).name == _WIRE:
                sides[side] = "up" if beside.name in _CONDUCTORS else "side"
            elif beside.name not in _CONDUCTORS and _get(grid, x + dx, y - 1, z + dz).name == _WIRE:
                sides[side] = "side"
        if len(sides) == 1:
            (only,) = sides
            sides[_OPP[only]] = "side"
        elif not sides:
            sides = dict.fromkeys(_HORIZONTAL, "side")   # Java's default: a cross
        todo.append(((x, y, z), state.with_props(**{s: sides.get(s, "none") for s in _HORIZONTAL})))
    for pos, state in todo:
        grid.set(*pos, state)


class Circuit:
    def __init__(self, size):
        self.grid = VoxelGrid(size)
        self.inputs: dict[str, tuple[int, int, int]] = {}
        self.outputs: dict[str, tuple[int, int, int]] = {}
        sx, _, sz = size
        self.fill(0, 0, 0, sx - 1, 0, sz - 1, FLOOR)

    @classmethod
    def from_grid(cls, grid: VoxelGrid, inputs: dict, outputs: dict) -> "Circuit":
        """Wrap a build read from a file. Its dust already has the shapes
        it was saved with, so they are left alone."""
        circuit = cls.__new__(cls)
        circuit.grid = grid
        circuit.inputs, circuit.outputs = dict(inputs), dict(outputs)
        circuit.shaped = True
        return circuit

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

    def embed(self, sub: "Circuit", x: int, z: int, prefix: str) -> "Circuit":
        """Copy another circuit in at (x, 0, z); its names get ``prefix``."""
        from craftpipe.grid import AIR
        for (sx, sy, sz), state in sub.grid.cells():
            if state != AIR:
                self.grid.set(x + sx, sy, z + sz, state)
        for (sx, sy, sz), entity in sub.grid.block_entities.items():
            self.grid.block_entities[(x + sx, sy, z + sz)] = entity
        for name, (sx, sy, sz) in sub.inputs.items():
            self.inputs[prefix + name] = (x + sx, sy, z + sz)
        for name, (sx, sy, sz) in sub.outputs.items():
            self.outputs[prefix + name] = (x + sx, sy, z + sz)
        return self

    def save(self, path) -> None:
        if not getattr(self, "shaped", False):
            java_dust_shapes(self.grid)
        if os.fspath(path).endswith(".litematic"):
            litematic.write_litematic(self.grid, path)
        else:
            schem.write_schem(self.grid, path)


def bench(tiles: dict[str, Circuit], gap: int = 2, per_row: int = 12) -> Circuit:
    """Lay independent circuits out on one floor so a single engine run
    can exercise all of them. Names become "<tile>.<name>"."""
    items = list(tiles.items())
    rows = [items[i:i + per_row] for i in range(0, len(items), per_row)]
    width = max(sum(c.size[0] + gap for _, c in row) for row in rows)
    depth = sum(max(c.size[2] for _, c in row) + gap for row in rows)
    height = max(c.size[1] for _, c in items)
    out = Circuit((width, height, depth))
    z = 0
    for row in rows:
        x = 0
        for name, tile in row:
            out.embed(tile, x, z, name + ".")
            x += tile.size[0] + gap
        z += max(c.size[2] for _, c in row) + gap
    return out


# Minecraft horizontal directions as (dx, dz).
DIRS = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}

STONE = "minecraft:stone"
TORCH = "minecraft:redstone_torch[lit=true]"


def _repeater(facing: str, **props) -> str:
    merged = {"delay": "1", "facing": facing, "locked": "false", "powered": "false", **props}
    return "minecraft:repeater[" + ",".join(f"{k}={v}" for k, v in sorted(merged.items())) + "]"


# --------------------------------------------------------------------------
# NAND netlists
#
# Every signal runs east along its own row of dust on the floor ("track",
# rows two apart). Gate g sits in column X = 4 + 4g. A track that feeds the
# gate ends in a stone block with a torch on top (an inverter); the torch
# strongly powers a block above it, which feeds a north-south line of dust
# running over the other tracks. That line is the OR of the inverted
# inputs, i.e. their NAND. It steps down onto the gate's output track.
# Tracks that merely pass are re-driven by a repeater, so every track gains
# the same one-tick delay per column.
# --------------------------------------------------------------------------

COLUMN_PITCH = 4
ROW_PITCH = 2
MAX_ROW_SPAN = 7        # a torch must reach the output row within 15 dust


def nand_netlist(gates, outputs) -> Circuit:
    """gates: [(output_name, [input_names])] in evaluation order (inputs
    must be primary inputs or outputs of earlier gates). ``outputs`` get
    lamps. Primary inputs get levers. One-input gates are inverters."""
    gates = [(out, list(dict.fromkeys(ins))) for out, ins in gates]
    driver = {out: g for g, (out, _) in enumerate(gates)}
    first_use: dict[str, int] = {}
    last_use: dict[str, int] = {}
    for g, (_, ins) in enumerate(gates):
        for s in ins:
            if s not in driver and s not in first_use:
                first_use[s] = g
            assert s not in driver or driver[s] < g, f"{s} is used before it is driven"
            last_use[s] = g
    for s in outputs:
        assert s in driver and s not in last_use, f"output {s} must be an unused gate output"

    rows: dict[str, int] = {}
    busy_until: dict[int, int] = {}      # row -> last gate index at which it is occupied

    def free_rows(g):
        used = {r for r, until in busy_until.items() if until >= g}
        return [r for r in range(64) if r not in used]

    def allocate(signal, g, near):
        candidates = free_rows(g)
        row = min(candidates, key=lambda r: (abs(r - near), r)) if near is not None else candidates[0]
        rows[signal] = row
        end = last_use.get(signal, g)
        busy_until[row] = end + 1 if signal in outputs else end
        return row

    plan = []
    for g, (out, ins) in enumerate(gates):
        known = [rows[s] for s in ins if s in rows]
        near = sorted(known)[len(known) // 2] if known else None
        new_inputs = [s for s in ins if s not in rows]
        for s in new_inputs:
            near = allocate(s, g, near) if near is None else near
            if s not in rows:
                allocate(s, g, near)
        in_rows = [rows[s] for s in ins]
        out_row = allocate(out, g, sorted(in_rows)[len(in_rows) // 2])
        span = max(in_rows + [out_row]) - min(in_rows + [out_row])
        assert span <= MAX_ROW_SPAN, f"gate {out}: rows span {span}, signal would die"
        passing = [s for s in rows if s not in ins and s != out
                   and (driver.get(s, first_use.get(s, 0) - 1) < g) and last_use.get(s, -1) > g]
        plan.append((g, out, ins, new_inputs, passing))

    n_rows = max(rows.values()) + 1
    c = Circuit((4 + COLUMN_PITCH * len(gates) + 4, 5, ROW_PITCH * (n_rows - 1) + 1))
    east = _repeater("west")
    for g, out, ins, new_inputs, passing in plan:
        X = 4 + COLUMN_PITCH * g
        for s in ins + passing:
            z = ROW_PITCH * rows[s]
            if s in new_inputs:
                c.input(s, (X - 2, 1, z))
            else:
                c.dust((X - 2, 1, z))
            c.dust((X - 1, 1, z))
            if s in ins:
                c.block(X, 1, z, STONE).block(X, 2, z, TORCH).block(X, 3, z, STONE).dust((X, 4, z))
            else:
                c.dust((X, 1, z))
            if last_use[s] > g:
                c.block(X + 1, 1, z, east)
        zo = ROW_PITCH * rows[out]
        c.block(X, 1, zo, STONE).dust((X, 2, zo), (X + 1, 1, zo))
        if out in outputs:
            c.output(out, (X + 2, 1, zo))
        tapped = {ROW_PITCH * rows[s] for s in ins}
        for z in range(min(tapped | {zo}), max(tapped | {zo}) + 1):
            if z not in tapped and z != zo:
                c.block(X, 2, z, STONE).dust((X, 3, z))
    return c


def not_gate() -> Circuit:
    return nand_netlist([("out", ["a"])], ["out"])


def nand_gate() -> Circuit:
    return nand_netlist([("out", ["a", "b"])], ["out"])


def and_gate() -> Circuit:
    return nand_netlist([("n", ["a", "b"]), ("out", ["n"])], ["out"])


def or_gate() -> Circuit:
    return nand_netlist([("na", ["a"]), ("nb", ["b"]), ("out", ["na", "nb"])], ["out"])


def xor_gate() -> Circuit:
    return nand_netlist([("n1", ["a", "b"]), ("n2", ["a", "n1"]), ("n3", ["b", "n1"]),
                         ("out", ["n2", "n3"])], ["out"])


def full_adder_gates(a, b, cin, s, cout, tag=""):
    n = lambda k: f"{tag}n{k}"  # noqa: E731
    return [
        (n(1), [a, b]), (n(2), [a, n(1)]), (n(3), [b, n(1)]), (n("x"), [n(2), n(3)]),
        (n(4), [n("x"), cin]), (n(5), [n("x"), n(4)]), (n(6), [cin, n(4)]),
        (s, [n(5), n(6)]), (cout, [n(1), n(4)]),
    ]


def full_adder() -> Circuit:
    return nand_netlist(full_adder_gates("a", "b", "cin", "s", "cout"), ["s", "cout"])


def ripple_adder(bits: int = 4) -> Circuit:
    """Inputs a0.., b0.., cin; outputs s0.., cout."""
    gates = []
    carry = "cin"
    for i in range(bits):
        nxt = "cout" if i == bits - 1 else f"c{i + 1}"
        gates += full_adder_gates(f"a{i}", f"b{i}", carry, f"s{i}", nxt, tag=f"b{i}_")
        carry = nxt
    return nand_netlist(gates, [f"s{i}" for i in range(bits)] + ["cout"])


# --------------------------------------------------------------------------
# Memory cells
# --------------------------------------------------------------------------

def _dust(power: int) -> str:
    return f"minecraft:redstone_wire[east=none,north=none,power={power},south=none,west=none]"


def rs_latch(stored: bool | None = None) -> Circuit:
    """Two cross-coupled torches. Inputs "set" and "reset", output "q".
    ``stored`` saves the latch already holding that bit (None: holding 0)."""
    q = bool(stored)
    c = Circuit((4, 3, 5))
    c.block(1, 1, 1, STONE).block(1, 1, 3, STONE)
    c.block(0, 1, 1, f"minecraft:redstone_wall_torch[facing=west,lit={'false' if q else 'true'}]")
    c.block(2, 1, 3, f"minecraft:redstone_wall_torch[facing=east,lit={'true' if q else 'false'}]")
    for i, pos in enumerate([(0, 1, 2), (0, 1, 3), (1, 2, 3)]):     # from torch A onto block Q
        c.block(*pos, _dust(0 if q else 15 - i))
    for i, pos in enumerate([(2, 1, 2), (2, 1, 1), (1, 2, 1)]):     # from torch B onto block P
        c.block(*pos, _dust(15 - i if q else 0))
    c.input("set", (1, 1, 0), "minecraft:lever[face=wall,facing=north,powered=false]")
    c.input("reset", (1, 1, 4), "minecraft:lever[face=wall,facing=south,powered=false]")
    c.output("q", (3, 1, 3), f"minecraft:redstone_lamp[lit={'true' if q else 'false'}]")
    return c


def d_latch(stored: bool | None = None) -> Circuit:
    """A repeater locked by a second repeater: the memory cell of most
    redstone RAM. Inputs "d" and "hold"; output "q" follows d while hold
    is off and keeps its value while hold is on. ``stored=True`` saves it
    locked and holding 1 with d off."""
    c = Circuit((3, 2, 4))
    held = stored is not None
    on = "true" if stored else "false"
    c.input("d", (0, 1, 1))
    c.block(1, 1, 1, _repeater("west", locked="true" if held else "false", powered=on))
    c.output("q", (2, 1, 1), f"minecraft:redstone_lamp[lit={on}]")
    c.block(1, 1, 2, _repeater("south", powered="true" if held else "false"))
    c.input("hold", (1, 1, 3),
            f"minecraft:lever[face=floor,facing=north,powered={'true' if held else 'false'}]")
    return c
