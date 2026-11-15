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
