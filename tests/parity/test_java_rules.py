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


MC_TO_LUANTI_BIT = {"north": 0x4, "south": 0x1, "west": 0x2, "east": 0x8}   # Z is mirrored


def test_dust_beside_other_blocks_connects_as_in_minecraft(module_minecraft, module_engine_java):
    """Real Minecraft decides what each dust connects to; Mineclonia with
    the mod, shaping the same dust itself, must decide the same."""
    circuit = suites.dust_beside_blocks()
    minecraft = module_minecraft.dust_shapes(circuit)
    assert len(minecraft) == len(circuit.outputs)
    names = sorted(circuit.outputs)
    out = module_engine_java.run(suites.dust_beside_blocks(), [{"read": names}], native=True)
    wrong = {}
    for name in names:
        pos = circuit.outputs[name]
        want = sum(MC_TO_LUANTI_BIT[side] for side in minecraft[pos])
        node = out[0][name]["name"]
        got = int(node[-2:], 16) & 15 if node.startswith("mcl_redstone:wire_") else 0
        if got != want:
            beside = circuit.grid.get(pos[0], pos[1], pos[2] - 1).name
            wrong[beside] = (sorted(minecraft[pos]), f"{got:x}")
    assert not wrong, wrong


def test_mod_loads_without_the_loader(tmp_path):
    """The mod is independent of craftpipe_loader."""
    import shutil
    import subprocess
    from harness import luanti
    luanti.require_luanti()
    world = tmp_path / "world"
    (world / "worldmods/stopper").mkdir(parents=True)
    shutil.copytree(luanti.REPO / "mod/craftpipe_java_rules", world / "worldmods/craftpipe_java_rules")
    (world / "worldmods/stopper/mod.conf").write_text("name = stopper\ndepends = craftpipe_java_rules\n")
    (world / "worldmods/stopper/init.lua").write_text(
        "core.after(0, function() core.request_shutdown('done', false, 0) end)\n")
    (world / "world.mt").write_text("gameid = mineclonia\nbackend = sqlite3\nplayer_backend = sqlite3\n"
                                    "auth_backend = sqlite3\nmod_storage_backend = sqlite3\n")
    (world / "luanti.conf").write_text(f"mg_name = singlenode\nport = {luanti._free_port()}\n"
                                       "bind_address = 127.0.0.1\nserver_announce = false\n")
    proc = subprocess.run([luanti.LUANTI, "--server", "--world", str(world), "--config",
                           str(world / "luanti.conf"), "--logfile", str(world / "debug.txt")],
                          capture_output=True, text=True, timeout=180)
    log = (world / "debug.txt").read_text(errors="replace")
    assert proc.returncode == 0, log[-2000:]
    assert "ModError" not in log
    assert "[craftpipe_java_rules] dust no longer connects to" in log
    assert "mcl_redstone_lamp:lamp_off" in log and "mcl_hoppers:hopper" in log


# ---- found by review: things that must keep working with the mod -------------

STONE = "minecraft:stone"


def _observer_watching_lamp():
    c = Circuit((4, 2, 1))
    c.input("in", (0, 1, 0)).output("lamp", (1, 1, 0)).dust((3, 1, 0)).probe("pulse", (3, 1, 0))
    return c


def _observer_pulses(engine):
    # The converter does not support observers, so one is placed directly:
    # watching the lamp (to its west), output towards the dust.
    out = engine.run(_observer_watching_lamp(), [
        {"setnode": [{"pos": (2, 1, 0), "name": "mcl_observers:observer_off", "param2": 3}], "wait": 6,
         "read": ["pulse"]},
        {"set": {"in": True}, "trace": 10, "read": ["lamp", "pulse"]},
    ])
    trace = out[1]["trace"]
    assert trace[-1]["lamp"]["on"] is True
    return sum(1 for t in trace if t["pulse"]["param2"] & 15)


def test_observer_still_sees_a_lamp_turn_on(module_engine, module_engine_java):
    stock = _observer_pulses(module_engine)
    assert stock > 0, "test set-up: the observer never fires even in stock Mineclonia"
    assert _observer_pulses(module_engine_java) == stock


def _lone_dust_on_powered_block():
    """A dust kept at full power by the block under it (torch below), with
    a lamp beside it."""
    c = Circuit((3, 4, 3))
    c.block(1, 1, 1, "minecraft:redstone_torch[lit=true]").block(1, 2, 1, STONE)
    c.block(1, 3, 1, "minecraft:redstone_wire[east=side,north=side,power=15,south=side,west=side]")
    c.output("lamp", (2, 3, 1)).probe("dust", (1, 3, 1))
    return c


def test_right_click_toggles_what_a_lone_dust_powers(module_engine_java):
    out = module_engine_java.run(_lone_dust_on_powered_block(), [
        {"wait": 4, "read": ["lamp", "dust"]},
        {"rightclick": [(1, 3, 1)], "wait": 6, "read": ["lamp", "dust"]},
        {"rightclick": [(1, 3, 1)], "wait": 6, "read": ["lamp", "dust"]},
    ], native=True)
    assert [s["dust"]["name"] for s in out] == [
        "mcl_redstone:wire_0f", "mcl_redstone:redstone", "mcl_redstone:wire_0f"]
    assert [s["lamp"]["on"] for s in out] == [True, False, True]


def test_dust_that_becomes_a_cross_powers_its_new_neighbours(module_engine_java):
    """Dust in a line with a lever; a lamp at right angles is not powered.
    Remove the lever: the dust is unconnected, so it is a cross, and the
    lamp must light (the block under the dust keeps it powered)."""
    c = _lone_dust_on_powered_block()
    c.block(0, 2, 1, STONE)
    c.input("lever", (0, 3, 1))
    c.block(1, 3, 1, "minecraft:redstone_wire[east=side,north=none,power=15,south=none,west=side]")
    c.block(2, 3, 1, "minecraft:air")
    c.output("lamp", (1, 3, 0))
    out = module_engine_java.run(c, [
        {"wait": 4, "read": ["lamp", "dust"]},
        {"remove": [(0, 3, 1)], "wait": 6, "read": ["lamp", "dust"]},
    ], native=True)
    assert out[0]["dust"]["name"] == "mcl_redstone:wire_0a" and out[0]["lamp"]["on"] is False
    assert out[1]["dust"]["name"] == "mcl_redstone:wire_0f" and out[1]["lamp"]["on"] is True


def _dust_beside_unlit_torch():
    """Torches held off by a lever on their block, with dust beside them:
    once alone, once with a second dust at right angles."""
    c = Circuit((9, 3, 4))
    for x in (1, 5):
        c.block(x, 1, 1, STONE)
        c.block(x, 2, 1, "minecraft:lever[face=floor,facing=north,powered=true]")
        c.block(x + 1, 1, 1, "minecraft:redstone_wall_torch[facing=east,lit=false]")
        c.dust((x + 1, 1, 2)).probe(f"dust{x}", (x + 1, 1, 2))
    c.dust((7, 1, 2)).probe("second", (7, 1, 2))
    return c


def _assert_native_shapes_match_minecraft(minecraft, engine, build):
    circuit = build()
    real = minecraft.dust_shapes(circuit)
    names = sorted(circuit.outputs)
    out = engine.run(build(), [{"read": names}], native=True)
    wrong = {}
    for name in names:
        pos = circuit.outputs[name]
        want = sum(MC_TO_LUANTI_BIT[side] for side in real[pos])
        node = out[0][name]["name"]
        got = int(node[-2:], 16) & 15 if node.startswith("mcl_redstone:wire_") else 0
        if got != want:
            wrong[name] = (sorted(real[pos]), f"{got:x}")
    assert not wrong, wrong


def test_dust_connects_to_an_unlit_torch(module_minecraft, module_engine_java):
    _assert_native_shapes_match_minecraft(module_minecraft, module_engine_java, _dust_beside_unlit_torch)


@pytest.mark.parametrize("name", SUITES + ["timing"])
def test_saved_dust_shapes_are_what_real_minecraft_computes(module_minecraft, name):
    """The shapes the test circuits are saved with come from a model of
    Java's rule (circuits.java_dust_shapes). Real Minecraft must agree,
    or the native-shape tests above compare against the wrong thing."""
    suite = (suites.timing if name == "timing" else suites.ALL[name])()
    from circuits import java_dust_shapes
    java_dust_shapes(suite.circuit.grid)
    real = module_minecraft.dust_shapes(suite.circuit)
    wrong = []
    for pos, sides in real.items():
        state = suite.circuit.grid.get(*pos)
        model = {s for s in ("north", "east", "south", "west") if state.get(s, "none") != "none"}
        if model != sides:
            wrong.append((pos, sorted(model), sorted(sides)))
    assert not wrong, wrong[:8]
