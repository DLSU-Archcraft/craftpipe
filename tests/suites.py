"""Test circuits and their step scripts, shared by the Mineclonia engine
tests and the Minecraft/Mineclonia parity tests.

A Suite is one circuit (usually many independent tiles laid out on one
floor) plus the steps to run on it. ``build()`` returns a fresh Suite, so
each backend gets its own copy of the circuit.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

from craftpipe import nbt
from circuits import (DIRS, OPPOSITE, Circuit, _repeater, and_gate, bench, d_latch, nand_gate,
                      not_gate, or_gate, ripple_adder, rs_latch, xor_gate)

STONE = "minecraft:stone"


@dataclass
class Suite:
    name: str
    circuit: Circuit
    steps: list


# ==========================================================================
# orientation: every directional component in every orientation
# ==========================================================================

C = (2, 2)  # tile centre (x, z)


def _at(d, n=1, y=1):
    dx, dz = DIRS[d]
    return (C[0] + n * dx, y, C[1] + n * dz)


def inline(kind, d, reverse=False):
    """lever -> component -> lamp along direction d."""
    c = Circuit((5, 2, 5))
    c.input("in", _at(OPPOSITE[d]))
    facing = d if reverse else OPPOSITE[d]   # MC facing names the input side
    extra = "delay=1,locked=false" if kind == "repeater" else "mode=compare"
    c.block(C[0], 1, C[1], f"minecraft:{kind}[facing={facing},{extra},powered=false]")
    c.output("lamp", _at(d))
    return c


def wall_torch(d):
    c = Circuit((5, 3, 5))
    c.block(C[0], 1, C[1], STONE)
    c.input("in", (C[0], 2, C[1]))
    c.block(*_at(d), f"minecraft:redstone_wall_torch[facing={d},lit=true]")
    c.output("lamp", _at(d, 2))
    return c


def floor_torch():
    c = Circuit((5, 3, 5))
    c.block(C[0], 1, C[1], STONE)
    c.input("in", _at("west"), "minecraft:lever[face=wall,facing=west,powered=false]")
    c.block(C[0], 2, C[1], "minecraft:redstone_torch[lit=true]")
    c.output("lamp", (C[0] + 1, 2, C[1]))
    return c


def attached(kind, face, d="north"):
    """A lever or button on a block; the lamp touches only that block."""
    state = {"lever": "minecraft:lever", "button": "minecraft:stone_button"}[kind]
    c = Circuit((5, 4, 5))
    if face == "wall":
        c.block(C[0], 1, C[1], STONE)
        c.input("in", _at(d), f"{state}[face=wall,facing={d},powered=false]")
        c.output("lamp", _at(OPPOSITE[d]))
    elif face == "floor":
        c.block(C[0], 1, C[1], STONE)
        c.input("in", (C[0], 2, C[1]), f"{state}[face=floor,facing={d},powered=false]")
        c.output("lamp", (C[0] + 1, 1, C[1]))
    else:
        c.block(C[0], 3, C[1], STONE)
        c.input("in", (C[0], 2, C[1]), f"{state}[face=ceiling,facing={d},powered=false]")
        c.output("lamp", (C[0] + 1, 3, C[1]))
    return c


def _orientation_tiles():
    out = {}
    for d in DIRS:
        out[f"repeater_{d}"] = inline("repeater", d)
        out[f"repeater_rev_{d}"] = inline("repeater", d, reverse=True)
        out[f"comparator_{d}"] = inline("comparator", d)
        out[f"comparator_rev_{d}"] = inline("comparator", d, reverse=True)
        out[f"walltorch_{d}"] = wall_torch(d)
        out[f"lever_wall_{d}"] = attached("lever", "wall", d)
        out[f"button_wall_{d}"] = attached("button", "wall", d)
    out["floortorch"] = floor_torch()
    for face in ("floor", "ceiling"):
        for d in ("north", "east"):
            out[f"lever_{face}_{d}"] = attached("lever", face, d)
        out[f"button_{face}"] = attached("button", face)
    return out


ORIENTATION_TILES = _orientation_tiles()
# name -> expected lamp state (before, inputs on, inputs off again)
ORIENTATION_EXPECT = {}
for name in ORIENTATION_TILES:
    if "_rev_" in name:
        ORIENTATION_EXPECT[name] = (False, False, False)
    elif "torch" in name:
        ORIENTATION_EXPECT[name] = (True, False, True)
    elif name.startswith("button"):
        ORIENTATION_EXPECT[name] = (False, True, False)   # third read: after the button released itself
    else:
        ORIENTATION_EXPECT[name] = (False, True, False)




def orientation() -> Suite:
    tiles = _orientation_tiles()
    lamps = [f"{n}.lamp" for n in tiles]
    levers = {f"{n}.in": True for n in tiles}
    levers_off = {k: False for k in levers if not k.startswith("button")}
    return Suite("orientation", bench(tiles), [
        {"read": lamps},
        {"set": levers, "wait": 6, "read": lamps},
        {"set": levers_off, "wait": 30, "read": lamps},
    ])


# ==========================================================================
# logic: dust shapes, towers, torch gates, memory cells
# ==========================================================================

TOP_SLAB = "minecraft:smooth_stone_slab[type=top,waterlogged=false]"
LOGIC_WAIT = 12


def corner():
    c = Circuit((3, 2, 4))
    c.input("in", (0, 1, 0)).dust((1, 1, 0), (2, 1, 0), (2, 1, 1), (2, 1, 2)).output("lamp", (2, 1, 3))
    return c


def cross():
    c = Circuit((6, 2, 5))
    c.input("in", (0, 1, 2)).dust_line(1, 1, 2, 4, 2).dust((2, 1, 1), (2, 1, 3))
    c.output("east", (5, 1, 2)).output("north", (2, 1, 0)).output("south", (2, 1, 4))
    return c


def step_up():
    c = Circuit((4, 3, 1))
    c.input("in", (0, 1, 0)).dust((1, 1, 0)).block(2, 1, 0, STONE).dust((2, 2, 0)).output("lamp", (3, 2, 0))
    return c


def step_down():
    c = Circuit((4, 3, 1))
    c.output("lamp", (0, 1, 0)).dust((1, 1, 0)).block(2, 1, 0, STONE).dust((2, 2, 0))
    c.block(3, 1, 0, STONE).input("in", (3, 2, 0))
    return c


def line(n_dust, repeater_at=None):
    c = Circuit((n_dust + 2, 2, 1))
    c.input("in", (0, 1, 0)).dust_line(1, 1, 0, n_dust, 0)
    if repeater_at:
        c.block(repeater_at, 1, 0, _repeater("west"))
    c.output("lamp", (n_dust + 1, 1, 0))
    return c


def torch_tower():
    c = Circuit((3, 5, 2))
    c.block(1, 1, 1, STONE).input("in", (0, 1, 1), "minecraft:lever[face=wall,facing=west,powered=false]")
    c.block(1, 2, 1, "minecraft:redstone_torch[lit=true]").block(1, 3, 1, STONE)
    c.block(1, 4, 1, "minecraft:redstone_torch[lit=false]").output("lamp", (2, 4, 1))
    return c


def slab_tower(source_at_top: bool):
    """Dust zig-zagging up top-half slabs. Minecraft carries the signal up
    such a tower but not down it."""
    c = Circuit((4, 5, 1))
    c.dust((1, 1, 0))
    c.block(2, 1, 0, TOP_SLAB).dust((2, 2, 0))
    c.block(1, 2, 0, TOP_SLAB).dust((1, 3, 0))
    c.block(2, 3, 0, TOP_SLAB).dust((2, 4, 0))
    if source_at_top:
        c.block(3, 3, 0, STONE).input("in", (3, 4, 0)).output("lamp", (0, 1, 0))
    else:
        c.input("in", (0, 1, 0)).output("lamp", (3, 4, 0))
    return c


def lone_dust(cross: bool):
    """One dust on a block that a lever powers; nothing connects to the
    dust. A cross powers the lamp beside it, a dot does not."""
    c = Circuit((3, 3, 2))
    c.block(1, 1, 1, STONE).input("in", (0, 1, 1), "minecraft:lever[face=wall,facing=west,powered=false]")
    c.block(1, 2, 1, "minecraft:redstone_wire[east=side,north=side,power=0,south=side,west=side]" if cross
            else "minecraft:redstone_wire[dot=true,east=none,north=none,power=0,south=none,west=none]")
    c.output("lamp", (2, 2, 1))
    return c


def wire_past_lamp():
    """A straight wire with a lamp beside it (not at its end). Java does
    not power the lamp; the lamp at the end is the control."""
    c = Circuit((6, 2, 2))
    c.input("in", (0, 1, 0)).dust_line(1, 1, 0, 4, 0).output("end", (5, 1, 0))
    c.output("beside", (3, 1, 1))
    return c


GATES = {
    "not": (not_gate, lambda a: not a),
    "nand": (nand_gate, lambda a, b: not (a and b)),
    "and": (and_gate, lambda a, b: a and b),
    "or": (or_gate, lambda a, b: a or b),
    "xor": (xor_gate, lambda a, b: a != b),
}

LOGIC_SIMPLE = {   # tile -> {output: (before, on, off)}
    "corner": (corner(), {"lamp": (False, True, False)}),
    "cross": (cross(), {k: (False, True, False) for k in ("east", "north", "south")}),
    "step_up": (step_up(), {"lamp": (False, True, False)}),
    "step_down": (step_down(), {"lamp": (False, True, False)}),
    "reach15": (line(15), {"lamp": (False, True, False)}),
    "dies16": (line(16), {"lamp": (False, False, False)}),
    "repeated": (line(20, repeater_at=11), {"lamp": (False, True, False)}),
    "torch_tower": (torch_tower(), {"lamp": (False, True, False)}),
    "slab_up": (slab_tower(False), {"lamp": (False, True, False)}),
    "slab_down": (slab_tower(True), {"lamp": (False, False, False)}),
    "lone_cross": (lone_dust(True), {"lamp": (False, True, False)}),
    "lone_dot": (lone_dust(False), {"lamp": (False, False, False)}),
    "wire_past_lamp": (wire_past_lamp(), {"end": (False, True, False), "beside": (False, False, False)}),
}


def gate_tiles():
    """One copy of each gate per input row, so all rows run in parallel."""
    tiles = {}
    for name, (build, fn) in GATES.items():
        arity = fn.__code__.co_argcount
        for values in itertools.product([False, True], repeat=arity):
            tiles[f"{name}_{''.join('01'[v] for v in values)}"] = build()
    return tiles




def logic() -> Suite:
    tiles = {k: v[0] for k, v in LOGIC_SIMPLE.items()}
    tiles.update(gate_tiles())
    tiles["rs"] = rs_latch()
    tiles["dl"] = d_latch()
    tiles["rs_stored1"] = rs_latch(stored=True)
    tiles["rs_stored0"] = rs_latch(stored=False)
    tiles["dl_stored1"] = d_latch(stored=True)
    circuit = bench(tiles)
    outs = list(circuit.outputs)
    simple_on = {f"{k}.in": True for k in LOGIC_SIMPLE}
    gate_on = {}
    for name, (_, fn) in GATES.items():
        arity = fn.__code__.co_argcount
        for values in itertools.product([False, True], repeat=arity):
            key = f"{name}_{''.join('01'[v] for v in values)}"
            for pin, v in zip("ab", values):
                gate_on[f"{key}.{pin}"] = v
    return Suite("logic", circuit, [
        {"read": outs},                                                       # 0 as loaded
        {"set": {**simple_on, **gate_on, "rs.reset": True, "dl.d": True},
         "wait": LOGIC_WAIT, "read": outs},                                   # 1
        {"set": {**{k: False for k in simple_on}, "rs.reset": False, "dl.hold": True},
         "wait": LOGIC_WAIT, "read": outs},                                   # 2
        {"set": {"rs.set": True, "dl.d": False}, "wait": LOGIC_WAIT, "read": outs},      # 3
        {"set": {"rs.set": False, "dl.hold": False}, "wait": LOGIC_WAIT, "read": outs},  # 4
    ])


# ==========================================================================
# comparator: compare and subtract over a grid of strengths
# ==========================================================================

COMPARATOR_LEVELS = (0, 1, 7, 8, 14, 15)
COMPARATOR_MODES = ("compare", "subtract")
CX = CZ = 16


def comparator_tile(mode, rear, side):
    """Strength k arrives through 16-k dust from a lever (15 at the first dust)."""
    c = Circuit((18, 2, 17))
    c.block(CX, 1, CZ, f"minecraft:comparator[facing=west,mode={mode},powered=false]")
    c.probe("cmp", (CX, 1, CZ))
    c.dust((CX + 1, 1, CZ)).probe("out", (CX + 1, 1, CZ))
    if rear:
        n = 16 - rear
        c.dust_line(CX - n, 1, CZ, CX - 1, CZ).input("rear", (CX - n - 1, 1, CZ))
    if side:
        n = 16 - side
        c.dust_line(CX, 1, CZ - n, CX, CZ - 1).input("side", (CX, 1, CZ - n - 1))
    return c


COMPARATOR_CASES = list(itertools.product(COMPARATOR_MODES, COMPARATOR_LEVELS, COMPARATOR_LEVELS))


def comparator_key(mode, rear, side):
    return f"{mode}_{rear}_{side}"


def comparator_expected(mode, rear, side):
    if mode == "compare":
        return rear if rear >= side else 0
    return max(rear - side, 0)




def comparator() -> Suite:
    circuit = bench({comparator_key(*case): comparator_tile(*case) for case in COMPARATOR_CASES},
                    per_row=9)
    probes = list(circuit.outputs)
    return Suite("comparator", circuit, [
        {"set": {name: True for name in circuit.inputs}, "wait": 12, "read": probes},
        {"set": {name: False for name in circuit.inputs}, "wait": 12, "read": probes},
    ])


# ==========================================================================
# rom: containers read by comparators
# ==========================================================================

def stacks(item, total, size=64, first_slot=0):
    out, slot = [], first_slot
    while total > 0:
        n = min(size, total)
        out.append({"Slot": nbt.Byte(slot), "id": item, "count": nbt.Int(n)})
        total -= n
        slot += 1
    return out


def reader(block_state, ident, items=None, extra=None):
    """container -> comparator -> dust; the comparator faces away from it."""
    c = Circuit((3, 2, 1))
    c.block(0, 1, 0, block_state)
    c.grid.block_entities[(0, 1, 0)] = {"id": ident, **({"Items": items} if items is not None else {}),
                                        **(extra or {})}
    c.block(1, 1, 0, "minecraft:comparator[facing=west,mode=compare,powered=false]")
    c.probe("cmp", (1, 1, 0)).dust((2, 1, 0)).probe("out", (2, 1, 0))
    return c


def chest_with_signal(n):
    """Fewest redstone items that make a 27-slot chest read n."""
    total = 1 if n == 1 else math.ceil((n - 1) * 27 * 64 / 14)
    return reader("minecraft:chest[facing=north,type=single,waterlogged=false]", "minecraft:chest",
                  stacks("minecraft:redstone", total))


def double_chest():
    c = Circuit((4, 2, 3))
    # North-facing pair: the LEFT half's partner is to its east.
    c.block(1, 1, 1, "minecraft:chest[facing=north,type=left,waterlogged=false]")
    c.block(2, 1, 1, "minecraft:chest[facing=north,type=right,waterlogged=false]")
    c.grid.block_entities[(1, 1, 1)] = {"id": "minecraft:chest",
                                        "Items": stacks("minecraft:redstone", 27 * 64)}
    c.grid.block_entities[(2, 1, 1)] = {"id": "minecraft:chest", "Items": []}
    # one comparator behind each half, reading south
    for name, x in (("full", 1), ("empty", 2)):
        c.block(x, 1, 2, "minecraft:comparator[facing=north,mode=compare,powered=false]")
        c.probe(name, (x, 1, 2))
    return c


ROM_TILES = {f"chest{n}": (chest_with_signal(n), n) for n in range(1, 16)}
ROM_TILES.update({
    "empty": (reader("minecraft:chest[facing=north,type=single]", "minecraft:chest", []), 0),
    "barrel": (reader("minecraft:barrel[facing=up,open=false]", "minecraft:barrel",
                      stacks("minecraft:redstone", 13 * 64 + 32)), 8),
    "furnace": (reader("minecraft:furnace[facing=north,lit=false]", "minecraft:furnace",
                       stacks("minecraft:redstone", 64)), 5),
    "hopper": (reader("minecraft:hopper[enabled=true,facing=down]", "minecraft:hopper",
                      stacks("minecraft:redstone", 128)), 6),
    "dropper": (reader("minecraft:dropper[facing=up,triggered=false]", "minecraft:dropper",
                       stacks("minecraft:redstone", 3 * 64)), 5),
    "dispenser": (reader("minecraft:dispenser[facing=east,triggered=false]", "minecraft:dispenser",
                         stacks("minecraft:redstone", 9 * 64)), 15),
    "pearls": (reader("minecraft:chest[facing=north,type=single]", "minecraft:chest",
                      stacks("minecraft:ender_pearl", 80, size=16)), 3),
    "unknown_item": (reader("minecraft:chest[facing=north,type=single]", "minecraft:chest",
                            stacks("minecraft:nautilus_shell", 640)), 6),
    "swords": (reader("minecraft:chest[facing=north,type=single]", "minecraft:chest",
                      stacks("minecraft:diamond_sword", 4, size=1)), 3),
    "lectern": (reader("minecraft:lectern[facing=north,has_book=true,powered=false]",
                       "minecraft:lectern", extra={"Page": nbt.Int(2), "Book": {
                           "id": "minecraft:written_book", "count": nbt.Int(1),
                           "components": {"minecraft:written_book_content": {
                               "title": {"raw": "ROM"}, "author": "craftpipe",
                               "pages": [{"raw": '"x"'}] * 5}}}}), 8),
})




def rom() -> Suite:
    tiles = {k: v[0] for k, v in ROM_TILES.items()}
    tiles["double"] = double_chest()
    circuit = bench(tiles)
    return Suite("rom", circuit, [{"wait": 10, "read": list(circuit.outputs)}])


# ==========================================================================
# adder: 4-bit ripple-carry adder from torch NAND gates
# ==========================================================================

ADDER_OUTS = ["s0", "s1", "s2", "s3", "cout"]
ADDER_SETTLE = 120        # redstone ticks allowed per input change; see test_settle_time
ADDER_FAST = [(0, 0, 0), (15, 15, 1), (15, 1, 0), (1, 15, 0), (5, 10, 0), (10, 5, 1), (7, 8, 1),
        (8, 8, 0), (3, 12, 1), (9, 6, 0), (0, 15, 1), (15, 0, 1), (1, 1, 0), (2, 2, 1),
        (4, 4, 0), (6, 9, 1)]


def adder_steps(cases, wait=ADDER_SETTLE):
    steps = []
    for a, b, cin in cases:
        inputs = {"cin": bool(cin)}
        for i in range(4):
            inputs[f"a{i}"] = bool(a >> i & 1)
            inputs[f"b{i}"] = bool(b >> i & 1)
        steps.append({"set": inputs, "wait": wait, "read": ADDER_OUTS})
    return steps


def adder_value(reads):
    return sum(reads[name]["on"] << i for i, name in enumerate(ADDER_OUTS))



ADDER_ALL = list(itertools.product(range(16), range(16), range(2)))


def adder_fast() -> Suite:
    return Suite("adder_fast", ripple_adder(4), adder_steps(ADDER_FAST))


def adder_all() -> Suite:
    return Suite("adder_all", ripple_adder(4), adder_steps(ADDER_ALL))


ALL = {"orientation": orientation, "logic": logic, "comparator": comparator, "rom": rom,
       "adder_fast": adder_fast, "adder_all": adder_all}
SLOW = {"adder_all"}
