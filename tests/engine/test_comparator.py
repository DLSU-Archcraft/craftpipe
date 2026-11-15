"""Comparator compare and subtract modes over a grid of signal strengths
(circuits in suites.py)."""

import pytest

import suites
from suites import COMPARATOR_CASES, comparator_expected, comparator_key


@pytest.fixture(scope="module")
def run(module_engine):
    suite = suites.comparator()
    return module_engine.run(suite.circuit, suite.steps)


@pytest.mark.parametrize("mode,rear,side", COMPARATOR_CASES)
def test_comparator_output_strength(run, mode, rear, side):
    k = comparator_key(mode, rear, side)
    want = comparator_expected(mode, rear, side)
    assert run[0][f"{k}.cmp"]["param2"] >> 2 == want       # strength held by the comparator
    assert run[0][f"{k}.out"]["param2"] & 15 == want       # strength on the dust it drives
    assert run[0][f"{k}.cmp"]["on"] is (want > 0)
    assert run[1][f"{k}.out"]["param2"] & 15 == 0
