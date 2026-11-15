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


@pytest.fixture(scope="module")
def module_engine_java(tmp_path_factory):
    """Mineclonia with the craftpipe_java_rules mod loaded."""
    require_luanti()
    return Engine(tmp_path_factory.mktemp("engine_java"), mods=("craftpipe_java_rules",))


@pytest.fixture
def minecraft(tmp_path):
    """A real headless Minecraft server (unmodified), stopped after the test."""
    from harness import minecraft as mc
    mc.require_minecraft()
    with mc.MinecraftServer(tmp_path / "minecraft") as server:
        yield server


@pytest.fixture(scope="module")
def module_minecraft(tmp_path_factory):
    """One Minecraft server per test module; circuits are placed side by side."""
    from harness import minecraft as mc
    mc.require_minecraft()
    with mc.MinecraftServer(tmp_path_factory.mktemp("minecraft")) as server:
        yield server
