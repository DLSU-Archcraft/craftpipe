"""Comparator compare and subtract modes over a grid of signal strengths."""

import itertools

import pytest

from circuits import Circuit, bench

LEVELS = (0, 1, 7, 8, 14, 15)
MODES = ("compare", "subtract")
CX = CZ = 16


def tile(mode, rear, side):
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


CASES = list(itertools.product(MODES, LEVELS, LEVELS))


def key(mode, rear, side):
    return f"{mode}_{rear}_{side}"


def expected(mode, rear, side):
    if mode == "compare":
        return rear if rear >= side else 0
    return max(rear - side, 0)


@pytest.fixture(scope="module")
def run(module_engine):
    circuit = bench({key(*case): tile(*case) for case in CASES}, per_row=9)
    probes = list(circuit.outputs)
    out = module_engine.run(circuit, [
        {"set": {name: True for name in circuit.inputs}, "wait": 12, "read": probes},
        {"set": {name: False for name in circuit.inputs}, "wait": 12, "read": probes},
    ])
    return out


@pytest.mark.parametrize("mode,rear,side", CASES)
def test_comparator_output_strength(run, mode, rear, side):
    k = key(mode, rear, side)
    want = expected(mode, rear, side)
    assert run[0][f"{k}.cmp"]["param2"] >> 2 == want       # strength held by the comparator
    assert run[0][f"{k}.out"]["param2"] & 15 == want       # strength on the dust it drives
    assert run[0][f"{k}.cmp"]["on"] is (want > 0)
    assert run[1][f"{k}.out"]["param2"] & 15 == 0
