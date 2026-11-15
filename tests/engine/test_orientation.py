"""Every directional component, in every orientation, in one engine run.

Each tile (see suites.py) is built so that only the correct orientation
gives the expected lamp state; a component turned the wrong way leaves the
lamp wrong in at least one step.
"""

import pytest

import suites


@pytest.fixture(scope="module")
def results(module_engine):
    suite = suites.orientation()
    return module_engine.run(suite.circuit, suite.steps)


@pytest.mark.parametrize("name", sorted(suites.ORIENTATION_TILES))
def test_orientation(results, name):
    got = tuple(step[f"{name}.lamp"]["on"] for step in results)
    assert got == suites.ORIENTATION_EXPECT[name]
