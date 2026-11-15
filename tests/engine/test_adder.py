"""A 4-bit ripple-carry adder built from torch NAND gates, converted from
both input formats and checked against integer addition."""

import itertools
import json
import pathlib

import pytest

from circuits import full_adder, ripple_adder

OUTS = ["s0", "s1", "s2", "s3", "cout"]
SETTLE = 120        # redstone ticks allowed per input change; see test_settle_time
FAST = [(0, 0, 0), (15, 15, 1), (15, 1, 0), (1, 15, 0), (5, 10, 0), (10, 5, 1), (7, 8, 1),
        (8, 8, 0), (3, 12, 1), (9, 6, 0), (0, 15, 1), (15, 0, 1), (1, 1, 0), (2, 2, 1),
        (4, 4, 0), (6, 9, 1)]


def steps_for(cases, wait=SETTLE):
    steps = []
    for a, b, cin in cases:
        inputs = {"cin": bool(cin)}
        for i in range(4):
            inputs[f"a{i}"] = bool(a >> i & 1)
            inputs[f"b{i}"] = bool(b >> i & 1)
        steps.append({"set": inputs, "wait": wait, "read": OUTS})
    return steps


def value(reads):
    return sum(reads[name]["on"] << i for i, name in enumerate(OUTS))


def test_full_adder(engine):
    c = full_adder()
    rows = list(itertools.product([False, True], repeat=3))
    out = engine.run(c, [{"set": {"a": a, "b": b, "cin": ci}, "wait": 40, "read": ["s", "cout"]}
                         for a, b, ci in rows])
    for (a, b, ci), reads in zip(rows, out):
        total = a + b + ci
        assert (reads["s"]["on"], reads["cout"]["on"]) == (bool(total & 1), bool(total >> 1)), (a, b, ci)


@pytest.mark.parametrize("fmt", ["schem", "litematic"])
def test_ripple_adder_fast(engine, fmt):
    out = engine.run(ripple_adder(4), steps_for(FAST), fmt=fmt)
    got = [value(r) for r in out]
    assert got == [a + b + cin for a, b, cin in FAST]


@pytest.mark.slow
def test_ripple_adder_all_512(engine):
    cases = list(itertools.product(range(16), range(16), range(2)))
    out = engine.run(ripple_adder(4), steps_for(cases))
    wrong = [(c, value(r)) for c, r in zip(cases, out) if value(r) != sum(c)]
    assert not wrong, wrong[:10]


@pytest.mark.slow
def test_settle_time(engine):
    """Smallest wait (in redstone ticks) at which the worst-case carry
    ripple settles; recorded for the README's clock guidance."""
    worst = [(0, 0, 0), (15, 0, 1), (0, 0, 0), (15, 1, 0), (0, 15, 1), (15, 15, 1), (0, 0, 0)]
    passing = None
    for wait in (4, 8, 16, 24, 32, 48, 64, 96):
        out = engine.run(ripple_adder(4), steps_for(worst, wait))
        if [value(r) for r in out] == [sum(c) for c in worst]:
            passing = wait
            break
    assert passing is not None
    record = pathlib.Path(__file__).parent / "settle_time.json"
    record.write_text(json.dumps({"circuit": "4-bit ripple-carry adder, 36 NAND columns",
                                  "settle_redstone_ticks": passing}) + "\n")
    assert passing <= SETTLE
