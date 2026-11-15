import pytest

from craftpipe import litematic, nbt
from craftpipe.grid import AIR, BlockState, VoxelGrid
from helpers import grids_equal, sample_grid


def roundtrip(tmp_path, arg, **kw):
    path = tmp_path / "a.litematic"
    litematic.write_litematic(arg, path, **kw)
    return litematic.read_litematic(nbt.load(path)[1])


@pytest.mark.parametrize("n_states", [2, 4, 16, 40])  # palette sizes 3, 5, 17, 41 incl. air
def test_roundtrip_single_region(tmp_path, n_states):
    g = sample_grid((5, 3, 4), n_states)
    g.block_entities[(4, 2, 3)] = {"id": "minecraft:chest", "Items": []}
    assert grids_equal(g, roundtrip(tmp_path, g))


def test_bit_width_and_straddling(tmp_path):
    g = sample_grid((5, 3, 4), 4)  # 5 palette entries -> 3 bits, 60 cells -> 180 bits -> 3 longs
    path = tmp_path / "a.litematic"
    litematic.write_litematic(g, path)
    region = next(iter(nbt.load(path)[1]["Regions"].values()))
    assert len(region["BlockStatePalette"]) == 5
    assert len(region["BlockStates"]) == 3


def test_negative_size_region(tmp_path):
    g = sample_grid((5, 3, 4), 4)
    g.block_entities[(0, 0, 0)] = {"id": "minecraft:barrel"}
    path = tmp_path / "a.litematic"
    litematic.write_litematic(g, path, negative_size=True)
    region = next(iter(nbt.load(path)[1]["Regions"].values()))
    assert region["Size"]["x"] == -5 and region["Size"]["z"] == -4
    assert grids_equal(g, litematic.read_litematic(nbt.load(path)[1]))


def test_two_regions_merged(tmp_path):
    a = VoxelGrid((2, 1, 2))
    a.set(0, 0, 0, BlockState("minecraft:stone"))
    b = VoxelGrid((2, 1, 2))
    b.set(1, 0, 1, BlockState("minecraft:glass"))
    b.block_entities[(1, 0, 1)] = {"id": "minecraft:chest"}
    merged = roundtrip(tmp_path, [((0, 0, 0), a), ((3, 0, 1), b)])
    assert merged.size == (5, 1, 3)
    assert merged.get(0, 0, 0) == BlockState("minecraft:stone")
    assert merged.get(4, 0, 2) == BlockState("minecraft:glass")
    assert merged.get(2, 0, 1) == AIR
    assert list(merged.block_entities) == [(4, 0, 2)]


def test_overlapping_regions_air_does_not_erase(tmp_path):
    a = VoxelGrid((2, 1, 1))
    a.set(0, 0, 0, BlockState("minecraft:stone"))
    b = VoxelGrid((2, 1, 1))
    b.set(1, 0, 0, BlockState("minecraft:glass"))
    merged = roundtrip(tmp_path, [((0, 0, 0), a), ((0, 0, 0), b)])
    assert merged.get(0, 0, 0) == BlockState("minecraft:stone")
    assert merged.get(1, 0, 0) == BlockState("minecraft:glass")


def test_regions_at_negative_positions(tmp_path):
    a = VoxelGrid((1, 1, 1))
    a.set(0, 0, 0, BlockState("minecraft:stone"))
    merged = roundtrip(tmp_path, [((-7, 60, -3), a)])
    assert merged.size == (1, 1, 1)
    assert merged.get(0, 0, 0) == BlockState("minecraft:stone")
