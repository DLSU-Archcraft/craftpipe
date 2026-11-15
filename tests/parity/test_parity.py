"""The same circuits in real Minecraft and in Mineclonia, compared output
by output. Any difference must be recorded in known_differences.json."""

import pytest

import suites
from harness.readings import luanti_reading
from parity import differences

FAST = [name for name in suites.ALL if name not in suites.SLOW]
_built = {name: suites.ALL[name]() for name in FAST}


def _cases(name):
    suite = _built[name]
    return [(index, output) for index, step in enumerate(suite.steps) for output in step.get("read", [])]


@pytest.fixture(scope="module")
def both(module_minecraft, module_engine):
    cache = {}

    def run(name):
        if name not in cache:
            suite = suites.ALL[name]()
            minecraft = module_minecraft.run(suite.circuit, suite.steps)
            raw = module_engine.run(suites.ALL[name]().circuit, suite.steps)
            mineclonia = [{k: luanti_reading(v) for k, v in step.items()} for step in raw]
            cache[name] = (minecraft, mineclonia)
        return cache[name]
    return run


@pytest.mark.parametrize("name,step,output",
                         [(n, s, o) for n in FAST for s, o in _cases(n)])
def test_same_in_both_games(both, name, step, output):
    minecraft, mineclonia = both(name)
    differences.check(name, output, step, minecraft[step][output], mineclonia[step][output])


@pytest.mark.slow
def test_adder_all_512_cases_agree(minecraft, engine):
    suite = suites.adder_all()
    mc = minecraft.run(suite.circuit, suite.steps)
    mcl = engine.run(suites.adder_all().circuit, suite.steps)
    wrong = [(i, o) for i, step in enumerate(suite.steps) for o in step["read"]
             if mc[i][o] != luanti_reading(mcl[i][o])]
    assert not wrong, wrong[:10]
    assert [suites.adder_value({k: {"on": v.on} for k, v in r.items()}) for r in mc] == \
        [sum(c) for c in suites.ADDER_ALL]
