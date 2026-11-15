"""Dust shapes, vertical transmission, torch logic and memory cells,
all in one engine run (circuits in suites.py)."""

import pytest

import suites
from suites import GATES, LOGIC_SIMPLE, gate_tiles


@pytest.fixture(scope="module")
def run(module_engine):
    suite = suites.logic()
    return module_engine.run(suite.circuit, suite.steps)


@pytest.mark.parametrize("tile,output", [(t, o) for t, (_, outs) in LOGIC_SIMPLE.items() for o in outs])
def test_dust_and_towers(run, tile, output):
    got = tuple(run[i][f"{tile}.{output}"]["on"] for i in (0, 1, 2))
    assert got == LOGIC_SIMPLE[tile][1][output]


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
