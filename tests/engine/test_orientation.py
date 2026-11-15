"""Every directional component, in every orientation, in one engine run.

Each tile is built so that only the correct orientation gives the expected
lamp state; a component turned the wrong way leaves the lamp wrong in at
least one step.
"""

import pytest

from circuits import DIRS, OPPOSITE, Circuit, bench

C = (2, 2)  # tile centre (x, z)
STONE = "minecraft:stone"


def at(d, n=1, y=1):
    dx, dz = DIRS[d]
    return (C[0] + n * dx, y, C[1] + n * dz)


def inline(kind, d, reverse=False):
    """lever -> component -> lamp along direction d."""
    c = Circuit((5, 2, 5))
    c.input("in", at(OPPOSITE[d]))
    facing = d if reverse else OPPOSITE[d]   # MC facing names the input side
    extra = "delay=1,locked=false" if kind == "repeater" else "mode=compare"
    c.block(C[0], 1, C[1], f"minecraft:{kind}[facing={facing},{extra},powered=false]")
    c.output("lamp", at(d))
    return c


def wall_torch(d):
    c = Circuit((5, 3, 5))
    c.block(C[0], 1, C[1], STONE)
    c.input("in", (C[0], 2, C[1]))
    c.block(*at(d), f"minecraft:redstone_wall_torch[facing={d},lit=true]")
    c.output("lamp", at(d, 2))
    return c


def floor_torch():
    c = Circuit((5, 3, 5))
    c.block(C[0], 1, C[1], STONE)
    c.input("in", at("west"), "minecraft:lever[face=wall,facing=west,powered=false]")
    c.block(C[0], 2, C[1], "minecraft:redstone_torch[lit=true]")
    c.output("lamp", (C[0] + 1, 2, C[1]))
    return c


def attached(kind, face, d="north"):
    """A lever or button on a block; the lamp touches only that block."""
    state = {"lever": "minecraft:lever", "button": "minecraft:stone_button"}[kind]
    c = Circuit((5, 4, 5))
    if face == "wall":
        c.block(C[0], 1, C[1], STONE)
        c.input("in", at(d), f"{state}[face=wall,facing={d},powered=false]")
        c.output("lamp", at(OPPOSITE[d]))
    elif face == "floor":
        c.block(C[0], 1, C[1], STONE)
        c.input("in", (C[0], 2, C[1]), f"{state}[face=floor,facing={d},powered=false]")
        c.output("lamp", (C[0] + 1, 1, C[1]))
    else:
        c.block(C[0], 3, C[1], STONE)
        c.input("in", (C[0], 2, C[1]), f"{state}[face=ceiling,facing={d},powered=false]")
        c.output("lamp", (C[0] + 1, 3, C[1]))
    return c


def tiles():
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


TILES = tiles()
# name -> expected lamp state (before, inputs on, inputs off again)
EXPECT = {}
for name in TILES:
    if "_rev_" in name:
        EXPECT[name] = (False, False, False)
    elif "torch" in name:
        EXPECT[name] = (True, False, True)
    elif name.startswith("button"):
        EXPECT[name] = (False, True, False)   # third read: after the button released itself
    else:
        EXPECT[name] = (False, True, False)


@pytest.fixture(scope="module")
def results(module_engine):
    circuit = bench(TILES)
    lamps = [f"{n}.lamp" for n in TILES]
    levers = {f"{n}.in": True for n in TILES}
    levers_off = {k: False for k in levers if not k.startswith("button")}
    out = module_engine.run(circuit, [
        {"read": lamps},
        {"set": levers, "wait": 6, "read": lamps},
        {"set": levers_off, "wait": 30, "read": lamps},
    ])
    return out


@pytest.mark.parametrize("name", sorted(TILES))
def test_orientation(results, name):
    got = tuple(step[f"{name}.lamp"]["on"] for step in results)
    assert got == EXPECT[name]
