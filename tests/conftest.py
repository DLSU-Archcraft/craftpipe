"""Fixtures for the two engines the tests can run circuits in."""

import pytest

from harness.luanti import Engine, require_luanti


@pytest.fixture
def engine(tmp_path):
    """A headless Luanti + Mineclonia server (one world per run)."""
    require_luanti()
    return Engine(tmp_path)


@pytest.fixture(scope="module")
def module_engine(tmp_path_factory):
    """One Engine per test module, for tests that share a single server run."""
    require_luanti()
    return Engine(tmp_path_factory.mktemp("engine"))
