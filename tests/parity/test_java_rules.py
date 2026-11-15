"""Mineclonia with the craftpipe_java_rules mod, compared with real
Minecraft. Differences the mod is meant to remove must be gone, both for
converted builds and for dust shaped by the game itself ("native"), which
is what a participant building directly in Mineclonia gets."""

import re

import pytest

import suites
from circuits import Circuit
from craftpipe import mts
from harness.readings import luanti_reading
from parity import differences
from parity.differences import changes
from parity.test_timing import LATENCY_CASES, OUTPUTS, FREE_RUNNING, _latency, waveform

SUITES = ["orientation", "logic", "comparator", "rom", "adder_fast"]
VARIANTS = ["pinned", "native"]


def _neutral(raw):
    out = []
    for step in raw:
        entry = {k: luanti_reading(v) for k, v in step.items() if k != "trace"}
        if "trace" in step:
            entry["trace"] = [{k: luanti_reading(v) for k, v in tick.items()} for tick in step["trace"]]
        out.append(entry)
    return out


@pytest.fixture(scope="module")
def minecraft_runs(module_minecraft):
    cache = {}

    def run(name):
        if name not in cache:
            suite = (suites.timing if name == "timing" else suites.ALL[name])()
            cache[name] = module_minecraft.run(suite.circuit, suite.steps)
        return cache[name]
    return run


@pytest.fixture(scope="module")
def java_runs(module_engine_java):
    cache = {}

    def run(name, variant):
        if (name, variant) not in cache:
            suite = (suites.timing if name == "timing" else suites.ALL[name])()
            raw = module_engine_java.run(suite.circuit, suite.steps, native=(variant == "native"))
            cache[name, variant] = _neutral(raw)
        return cache[name, variant]
    return run


def _suite_cases(name):
    suite = suites.ALL[name]()
    return [(i, o) for i, step in enumerate(suite.steps) for o in step.get("read", [])]


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", SUITES)
def test_existing_suites_match_minecraft(minecraft_runs, java_runs, name, variant):
    mc, mcl = minecraft_runs(name), java_runs(name, variant)
    problems = []
    for step, output in _suite_cases(name):
        try:
            differences.check(name, output, step, mc[step][output], mcl[step][output], mode="java")
        except AssertionError as exc:
            problems.append(str(exc))
    assert not problems, f"{len(problems)} mismatches, first: {problems[:5]}"


@pytest.mark.parametrize("variant", VARIANTS)
def test_timing_matches_minecraft(minecraft_runs, java_runs, variant):
    mc, mcl = minecraft_runs("timing"), java_runs("timing", variant)
    problems = []

    def check(output, step, a, b):
        try:
            differences.check("timing", output, step, a, b, mode="java")
        except AssertionError as exc:
            problems.append(str(exc))

    for tile, out, mode in OUTPUTS:
        name = f"{tile}.{out}"
        if tile not in FREE_RUNNING:
            for step in (0, 1, 2):
                check(name, step, mc[step][name], mcl[step][name])
        if mode:
            for step in (1, 2):
                check(name, f"trace{step}", waveform(mc, tile, out, mode, step),
                      waveform(mcl, tile, out, mode, step))
    for tile, step in LATENCY_CASES:
        ref = f"{tile}.ref"
        a, b = _latency(mc, ref, step), _latency(mcl, ref, step)
        if a is not None or b is not None:
            check(ref, f"input{step}", {"latency_ticks": a}, {"latency_ticks": b})
    assert not problems, f"{len(problems)} mismatches, first: {problems[:5]}"


def _native_shape_mismatches(engine, name):
    """Dust whose game-computed horizontal connections differ from the
    ones Minecraft saved."""
    suite = (suites.timing if name == "timing" else suites.ALL[name])()
    world, conv = engine.prepare(suite.circuit)
    wanted = {}
    sx, sy, sz = conv.size
    for z in range(sz):
        for y in range(sy):
            for x in range(sx):
                node = conv.names[conv.node_ids[mts.index(conv.size, x, y, z)]]
                if node == "mcl_redstone:redstone":
                    wanted[x, y, z] = 0
                elif node.startswith("mcl_redstone:wire_"):
                    wanted[x, y, z] = int(node[-2:], 16) & 15
    positions = sorted(wanted)
    result = engine.run_raw(world, "circuit", conv.size, [{"read": [list(p) for p in positions]}],
                            native=True)
    assert result["place_ok"], result["place_message"]
    wrong = []
    for pos, read in zip(positions, result["steps"][0] or []):
        match = re.fullmatch(r"mcl_redstone:wire_([0-9a-f]{2})", read["name"])
        got = int(match.group(1), 16) & 15 if match else 0
        if got != wanted[pos]:
            wrong.append((pos, wanted[pos], got))
    return wrong, len(positions)


@pytest.mark.parametrize("name", SUITES + ["timing"])
def test_native_dust_shapes_equal_minecraft(module_engine_java, name):
    wrong, total = _native_shape_mismatches(module_engine_java, name)
    if total == 0:
        pytest.skip("this suite has no redstone dust")
    assert not wrong, f"{len(wrong)} of {total} dust differ (pos, minecraft, mineclonia): {wrong[:8]}"


def test_stock_mineclonia_still_differs_natively(module_engine):
    """Guards the test above against being vacuous: without the mod the
    game's own dust shapes do differ from Minecraft's."""
    wrong, total = _native_shape_mismatches(module_engine, "logic")
    assert wrong and total > 0


def test_player_made_dot_stays_a_dot(module_engine_java):
    """A dot is a deliberate choice (right-click). It must survive the
    game re-shaping dust around it."""
    c = Circuit((3, 3, 3))
    c.block(1, 1, 1, "minecraft:stone")
    c.input("in", (0, 1, 1), "minecraft:lever[face=wall,facing=west,powered=false]")
    c.block(1, 2, 1, "minecraft:redstone_wire[dot=true,east=none,north=none,power=0,south=none,west=none]")
    c.output("lamp", (2, 2, 1)).probe("dust", (1, 2, 1))
    out = module_engine_java.run(c, [
        {"set": {"in": True}, "wait": 6, "read": ["lamp", "dust"]},
        {"poke": [(1, 2, 0)], "wait": 6, "read": ["lamp", "dust"]},
    ], native=True)
    for step in out:
        assert step["dust"]["name"] == "mcl_redstone:redstone"
        assert step["lamp"]["on"] is False
