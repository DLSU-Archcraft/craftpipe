import pytest

from craftpipe import nbt, schem
from craftpipe.errors import UnsupportedFormatError
from craftpipe.grid import BlockState, VoxelGrid
from helpers import grids_equal, sample_grid


def with_chest():
    g = sample_grid()
    g.set(2, 1, 3, BlockState.parse("chest[facing=north,type=single]"))
    g.block_entities[(2, 1, 3)] = {
        "id": "minecraft:chest",
        "Items": [{"Slot": nbt.Byte(0), "id": "minecraft:redstone", "count": nbt.Int(5)}],
    }
    return g


@pytest.mark.parametrize("version", [2, 3])
def test_roundtrip(tmp_path, version):
    g = with_chest()
    path = tmp_path / "a.schem"
    schem.write_schem(g, path, version=version)
    back = schem.read_schem(*nbt.load(path))
    assert grids_equal(g, back)
    assert back.block_entities[(2, 1, 3)]["Items"][0]["id"] == "minecraft:redstone"


@pytest.mark.parametrize("version", [2, 3])
def test_large_palette_varints(tmp_path, version):
    g = VoxelGrid((300, 1, 1))
    for i in range(300):
        g.set(i, 0, 0, BlockState("minecraft:stone", (("n", str(i)),)))
    path = tmp_path / "big.schem"
    schem.write_schem(g, path, version=version)
    assert grids_equal(g, schem.read_schem(*nbt.load(path)))


def test_axis_order(tmp_path):
    g = VoxelGrid((2, 3, 4))
    g.set(1, 2, 3, BlockState("minecraft:stone"))
    path = tmp_path / "a.schem"
    schem.write_schem(g, path, version=2)
    name, root = nbt.load(path)
    assert name == "Schematic"
    assert (root["Width"], root["Height"], root["Length"]) == (2, 3, 4)
    assert root["DataVersion"] == 3953


def test_unknown_version_raises():
    root = {"Version": nbt.Int(1), "Width": nbt.Short(1), "Height": nbt.Short(1),
            "Length": nbt.Short(1), "Palette": {}, "BlockData": nbt.ByteArray([])}
    with pytest.raises(UnsupportedFormatError, match="version 1"):
        schem.read_schem("Schematic", root)


def test_corrupt_block_data_raises(tmp_path):
    g = sample_grid()
    path = tmp_path / "a.schem"
    schem.write_schem(g, path, version=2)
    name, root = nbt.load(path)
    root["BlockData"] = nbt.ByteArray(list(root["BlockData"])[:3])
    with pytest.raises(UnsupportedFormatError):
        schem.read_schem(name, root)
    name, root = nbt.load(path)
    root["BlockData"] = nbt.ByteArray([99] * len(root["BlockData"]))
    with pytest.raises(UnsupportedFormatError):
        schem.read_schem(name, root)
