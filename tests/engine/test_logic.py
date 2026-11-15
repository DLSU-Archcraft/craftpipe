"""Dust shapes, vertical transmission, torch logic and memory cells,
all in one engine run."""

import itertools

import pytest

from circuits import (Circuit, _repeater, and_gate, bench, d_latch, nand_gate, not_gate, or_gate,
                      rs_latch, xor_gate)

STONE = "minecraft:stone"
TOP_SLAB = "minecraft:smooth_stone_slab[type=top,waterlogged=false]"
WAIT = 12


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


GATES = {
    "not": (not_gate, lambda a: not a),
    "nand": (nand_gate, lambda a, b: not (a and b)),
    "and": (and_gate, lambda a, b: a and b),
    "or": (or_gate, lambda a, b: a or b),
    "xor": (xor_gate, lambda a, b: a != b),
}

SIMPLE = {   # tile -> {output: (before, on, off)}
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
}


def gate_tiles():
    """One copy of each gate per input row, so all rows run in parallel."""
    tiles = {}
    for name, (build, fn) in GATES.items():
        arity = fn.__code__.co_argcount
        for values in itertools.product([False, True], repeat=arity):
            tiles[f"{name}_{''.join('01'[v] for v in values)}"] = build()
    return tiles


@pytest.fixture(scope="module")
def run(module_engine):
    tiles = {k: v[0] for k, v in SIMPLE.items()}
    tiles.update(gate_tiles())
    tiles["rs"] = rs_latch()
    tiles["dl"] = d_latch()
    tiles["rs_stored1"] = rs_latch(stored=True)
    tiles["rs_stored0"] = rs_latch(stored=False)
    tiles["dl_stored1"] = d_latch(stored=True)
    circuit = bench(tiles)
    outs = list(circuit.outputs)

    simple_on = {f"{k}.in": True for k in SIMPLE}
    gate_on = {}
    for name, (_, fn) in GATES.items():
        arity = fn.__code__.co_argcount
        for values in itertools.product([False, True], repeat=arity):
            key = f"{name}_{''.join('01'[v] for v in values)}"
            for pin, v in zip("ab", values):
                gate_on[f"{key}.{pin}"] = v
    steps = [
        {"read": outs},                                                       # 0 as loaded
        {"set": {**simple_on, **gate_on, "rs.reset": True, "dl.d": True},
         "wait": WAIT, "read": outs},                                         # 1
        {"set": {**{k: False for k in simple_on}, "rs.reset": False, "dl.hold": True},
         "wait": WAIT, "read": outs},                                         # 2
        {"set": {"rs.set": True, "dl.d": False}, "wait": WAIT, "read": outs},  # 3
        {"set": {"rs.set": False, "dl.hold": False}, "wait": WAIT, "read": outs},  # 4
    ]
    return module_engine.run(circuit, steps)


@pytest.mark.parametrize("tile,output", [(t, o) for t, (_, outs) in SIMPLE.items() for o in outs])
def test_dust_and_towers(run, tile, output):
    got = tuple(run[i][f"{tile}.{output}"]["on"] for i in (0, 1, 2))
    assert got == SIMPLE[tile][1][output]


@pytest.mark.parametrize("key", sorted(gate_tiles()))
def test_gate_truth_table(run, key):
    name, bits = key.rsplit("_", 1)
    expected = bool(GATES[name][1](*[b == "1" for b in bits]))
    assert run[1][f"{key}.out"]["on"] is expected


def test_rs_latch_sets_and_holds(run):
    q = [run[i]["rs.q"]["on"] for i in range(1, 5)]
    # reset pressed, reset released (holds 0), set pressed, set released (holds 1)
    assert q == [False, False, True, True]


def test_d_latch_follows_then_holds(run):
    q = [run[i]["dl.q"]["on"] for i in range(1, 5)]
    # d=1 -> 1; hold on -> 1; d=0 while held -> still 1; hold released -> follows d -> 0
    assert q == [True, True, True, False]


def test_stored_state_survives_load(run):
    """A latch saved while holding a bit still holds it after conversion,
    placement and Mineclonia's redstone initialisation."""
    for step in (0, 4):
        assert run[step]["rs_stored1.q"]["on"] is True
        assert run[step]["rs_stored0.q"]["on"] is False
        assert run[step]["dl_stored1.q"]["on"] is True
