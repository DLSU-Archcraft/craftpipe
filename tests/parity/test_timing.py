"""Tick-by-tick behaviour in real Minecraft and in Mineclonia, plus
circuits aimed at behaviours suspected to differ. Differences must be
recorded in known_differences.json."""

import pytest

import suites
from harness.readings import luanti_reading
from parity import differences
from parity.differences import changes, summarise

TILES = suites.TIMING_TILES
OUTPUTS = [(tile, out, mode) for tile, (_, outs) in TILES.items() for out, mode in outs.items()]


@pytest.fixture(scope="module")
def runs(module_minecraft, module_engine):
    suite = suites.timing()
    minecraft = module_minecraft.run(suite.circuit, suite.steps)
    raw = module_engine.run(suites.timing().circuit, suite.steps)
    mineclonia = []
    for step in raw:
        entry = {k: luanti_reading(v) for k, v in step.items() if k != "trace"}
        if "trace" in step:
            entry["trace"] = [{k: luanti_reading(v) for k, v in tick.items()} for tick in step["trace"]]
        mineclonia.append(entry)
    return {"minecraft": minecraft, "mineclonia": mineclonia}


def waveform(run, tile, out, mode, step):
    name, ref = f"{tile}.{out}", f"{tile}.ref"
    trace, before = run[step]["trace"], run[step - 1]
    ref_first = None
    if ref in before:
        ref_changes = changes(trace, ref, before[ref])
        ref_first = ref_changes[0][0] if ref_changes else None
    return summarise(mode, changes(trace, name, before[name]), ref_first)


# Free-running circuits are sampled at an arbitrary phase, so only their
# waveforms are compared.
FREE_RUNNING = {"clock"}


def test_clock_runs_and_torch_burns_out(runs):
    for game in ("minecraft", "mineclonia"):
        assert waveform(runs[game], "clock", "out", "period", 1) == {"half_periods": [5]}, game
        # The self-switching torch has burnt out by the first read and stays out.
        assert [runs[game][s]["burnout.out"].on for s in (0, 1, 2)] == [False] * 3, game
        assert waveform(runs[game], "burnout", "out", "count", 1)["changes"] == 0, game


@pytest.mark.parametrize("tile,out,step", [(t, o, s) for t, o, _ in OUTPUTS for s in (0, 1, 2)
                                           if t not in FREE_RUNNING])
def test_final_readings_agree(runs, tile, out, step):
    name = f"{tile}.{out}"
    differences.check("timing", name, step, runs["minecraft"][step][name], runs["mineclonia"][step][name])


@pytest.mark.parametrize("tile,out,mode,step",
                         [(t, o, m, s) for t, o, m in OUTPUTS if m for s in (1, 2)])
def test_waveforms_agree(runs, tile, out, mode, step):
    differences.check("timing", f"{tile}.{out}", f"trace{step}",
                      waveform(runs["minecraft"], tile, out, mode, step),
                      waveform(runs["mineclonia"], tile, out, mode, step))


def _latency(run, ref, step):
    found = changes(run[step]["trace"], ref, run[step - 1][ref])
    return found[0][0] if found else None


LATENCY_CASES = [(t, s) for t, (_, outs) in TILES.items() if "wave" in outs.values() for s in (1, 2)]


@pytest.mark.parametrize("tile,step", LATENCY_CASES)
def test_input_latency(runs, tile, step):
    """How many ticks after a lever or button is used the dust beside it
    reacts. (Waveforms above are timed from that moment, so this is the
    one place the input's own latency is compared.)"""
    ref = f"{tile}.ref"
    mc, mcl = _latency(runs["minecraft"], ref, step), _latency(runs["mineclonia"], ref, step)
    if mc is None and mcl is None:
        pytest.skip("this input does not change in this step")
    differences.check("timing", ref, f"input{step}", {"latency_ticks": mc}, {"latency_ticks": mcl})
