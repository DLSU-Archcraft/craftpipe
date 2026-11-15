"""Minecraft -> Mineclonia -> Minecraft, through the real engines.

Each suite is loaded into a Mineclonia world running craftpipe_java_rules,
exported with /craftpipe_export's function, converted back with
`to_minecraft`, and run in the real Minecraft server. It must behave
exactly like the original circuit does in Minecraft."""

import pytest

import craftpipe
import suites
from circuits import Circuit
from craftpipe.reader import read_schematic
from parity.test_timing import FREE_RUNNING, OUTPUTS, waveform

NAMES = ["orientation", "logic", "comparator", "rom", "adder_fast", "timing"]


def _suite(name):
    return (suites.timing if name == "timing" else suites.ALL[name])()


@pytest.fixture(scope="module")
def runs(module_minecraft, module_engine_java, tmp_path_factory):
    cache = {}

    def run(name):
        if name in cache:
            return cache[name]
        suite = _suite(name)
        original = module_minecraft.run(suite.circuit, suite.steps)

        fresh = _suite(name)
        world, conv = module_engine_java.prepare(fresh.circuit)
        result = module_engine_java.run_raw(world, "circuit", conv.size, [{"export": {"name": "exported"}}])
        assert result["place_ok"], result["place_message"]
        assert result["exports"][0]["ok"], result["exports"][0]["message"]
        out = tmp_path_factory.mktemp("back") / "back.litematic"
        report = craftpipe.to_minecraft(world / "schems/exported.mts", out)
        grid = read_schematic(out)
        assert grid.size == fresh.circuit.size
        returned = Circuit.from_grid(grid, fresh.circuit.inputs, fresh.circuit.outputs)
        round_trip = module_minecraft.run(returned, suite.steps)
        cache[name] = (suite, original, round_trip, report, grid)
        return cache[name]
    return run


@pytest.mark.parametrize("name", NAMES)
def test_round_tripped_build_behaves_like_the_original(runs, name):
    suite, original, round_trip, report, _ = runs(name)
    assert not report.unmapped
    wrong = []
    for index, step in enumerate(suite.steps):
        for output in step.get("read", []):
            tile = output.split(".")[0]
            if name == "timing" and tile in FREE_RUNNING:
                continue
            if original[index][output] != round_trip[index][output]:
                wrong.append((index, output, tuple(original[index][output]),
                              tuple(round_trip[index][output])))
    assert not wrong, f"{len(wrong)} differ (step, output, original, round trip): {wrong[:8]}"


def test_round_tripped_timing_is_tick_for_tick_the_same(runs):
    _, original, round_trip, _, _ = runs("timing")
    wrong = []
    for tile, out, mode in OUTPUTS:
        if not mode:
            continue
        for step in (1, 2):
            a = waveform(original, tile, out, mode, step)
            b = waveform(round_trip, tile, out, mode, step)
            if a != b:
                wrong.append((tile, out, step, a, b))
    assert not wrong, wrong[:6]


@pytest.mark.parametrize("name", NAMES)
def test_round_tripped_build_has_the_same_blocks(runs, name):
    """Same kind of block everywhere; same orientation for everything
    whose orientation matters."""
    suite, _, _, _, grid = runs(name)
    wrong = []
    for (pos, a), (_, b) in zip(suite.circuit.grid.cells(), grid.cells()):
        if a.name != b.name:
            wrong.append((pos, str(a), str(b)))
            continue
        for prop in ("facing", "face", "type", "delay", "mode", "enabled", "has_book"):
            if a.get(prop) is not None and a.get(prop) != b.get(prop):
                # floor/ceiling levers and buttons, and vertical barrels, do
                # not keep a facing in Mineclonia
                if prop == "facing" and (a.get("face") in ("floor", "ceiling")
                                         or a.name == "minecraft:barrel"):
                    continue
                wrong.append((pos, str(a), str(b)))
                break
    assert not wrong, wrong[:8]


def test_structure_built_by_hand_in_mineclonia_works_in_minecraft(module_minecraft, module_engine_java,
                                                                  tmp_path):
    """Nothing here came from Minecraft: the nodes are placed in Mineclonia
    the way a player places them (with the param2 values the game itself
    produces), then exported and converted.

    Row z=1: floor lever, two dust, a 3-tick repeater, dust, lamp.
    At x=7: a lever on the north face of a block, lamp on its south face."""
    base = Circuit((9, 3, 5))                      # just a floor
    world, conv = module_engine_java.prepare(base)

    def node(pos, name, param2=0):
        return {"pos": list(conv.to_luanti(pos)), "name": name, "param2": param2}

    built = [
        node((0, 1, 1), "mcl_lever:lever_off", 13),            # on the floor, handle along X
        node((1, 1, 1), "mcl_redstone:redstone"),
        node((2, 1, 1), "mcl_redstone:redstone"),
        node((3, 1, 1), "mcl_repeaters:repeater_off_3", 1),    # output towards +X
        node((4, 1, 1), "mcl_redstone:redstone"),
        node((5, 1, 1), "mcl_redstone_lamp:lamp_off"),
        node((7, 1, 2), "mcl_core:stone"),
        node((7, 1, 1), "mcl_lever:lever_off", 2),             # hangs on the block towards Luanti -Z
        node((7, 1, 3), "mcl_redstone_lamp:lamp_off"),
    ]
    result = module_engine_java.run_raw(world, "circuit", conv.size, [
        {"setnode": built, "wait": 6},
        {"export": {"name": "handmade"}},
    ])
    assert result["place_ok"] and result["exports"][0]["ok"], result

    report = craftpipe.to_minecraft(world / "schems/handmade.mts", tmp_path / "handmade.litematic")
    assert not report.unmapped and not report.warnings
    grid = read_schematic(tmp_path / "handmade.litematic")

    def state(pos):
        return grid.get(*pos)

    assert state((0, 1, 1)).name == "minecraft:lever" and state((0, 1, 1)).get("face") == "floor"
    assert str(state((3, 1, 1))) == "minecraft:repeater[delay=3,facing=west,locked=false,powered=false]"
    assert str(state((7, 1, 1))) == "minecraft:lever[face=wall,facing=north,powered=false]"
    for pos in ((1, 1, 1), (2, 1, 1), (4, 1, 1)):
        dust = state(pos)
        assert dust.name == "minecraft:redstone_wire"
        assert (dust.get("east"), dust.get("west"), dust.get("north"), dust.get("south")) == \
            ("side", "side", "none", "none"), pos

    circuit = Circuit.from_grid(grid, {"a": (0, 1, 1), "w": (7, 1, 1)},
                                {"near": (1, 1, 1), "lamp": (5, 1, 1), "wall_lamp": (7, 1, 3)})
    out = module_minecraft.run(circuit, [
        {"read": ["lamp", "wall_lamp"]},
        {"set": {"a": True}, "trace": 6, "read": ["near", "lamp", "wall_lamp"]},
        {"set": {"w": True}, "wait": 4, "read": ["lamp", "wall_lamp"]},
        {"set": {"a": False, "w": False}, "wait": 8, "read": ["lamp", "wall_lamp"]},
    ])
    assert (out[0]["lamp"].on, out[0]["wall_lamp"].on) == (False, False)
    lit = [t["lamp"].on for t in out[1]["trace"]]
    assert lit == [False, False, False, True, True, True, True]      # the 3-tick repeater
    assert out[1]["trace"][0]["near"].power == 15
    assert out[1]["wall_lamp"].on is False                           # the levers are independent
    assert (out[2]["lamp"].on, out[2]["wall_lamp"].on) == (True, True)
    assert (out[3]["lamp"].on, out[3]["wall_lamp"].on) == (False, False)
