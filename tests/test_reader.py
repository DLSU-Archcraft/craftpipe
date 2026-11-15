import os

import pytest

from craftpipe import litematic, nbt, schem
from craftpipe.errors import UnsupportedFormatError
from craftpipe.reader import read_schematic
from helpers import grids_equal, sample_grid


def test_reads_both_formats(tmp_path):
    g = sample_grid()
    schem.write_schem(g, tmp_path / "a.schem")
    litematic.write_litematic(g, tmp_path / "a.litematic")
    assert grids_equal(g, read_schematic(tmp_path / "a.schem"))
    assert grids_equal(g, read_schematic(tmp_path / "a.litematic"))


def test_dispatch_by_content(tmp_path):
    g = sample_grid()
    schem.write_schem(g, tmp_path / "wrong.litematic", version=2)
    assert grids_equal(g, read_schematic(tmp_path / "wrong.litematic"))


def test_legacy_mcedit_rejected(tmp_path):
    root = {"Materials": "Alpha", "Width": nbt.Short(1), "Height": nbt.Short(1),
            "Length": nbt.Short(1), "Blocks": nbt.ByteArray([1]), "Data": nbt.ByteArray([0])}
    path = tmp_path / "old.schematic"
    path.write_bytes(nbt.dumps(root, name="Schematic"))
    with pytest.raises(UnsupportedFormatError, match="MCEdit"):
        read_schematic(path)


def test_garbage_rejected(tmp_path):
    path = tmp_path / "junk.schem"
    path.write_bytes(os.urandom(512))
    with pytest.raises(UnsupportedFormatError):
        read_schematic(path)


def test_truncated_gzip_rejected(tmp_path):
    schem.write_schem(sample_grid(), tmp_path / "a.schem")
    data = (tmp_path / "a.schem").read_bytes()
    (tmp_path / "cut.schem").write_bytes(data[: len(data) // 2])
    with pytest.raises(UnsupportedFormatError):
        read_schematic(tmp_path / "cut.schem")


def test_unknown_nbt_names_keys(tmp_path):
    path = tmp_path / "level.dat"
    path.write_bytes(nbt.dumps({"Data": {"x": nbt.Int(1)}}))
    with pytest.raises(UnsupportedFormatError, match="Data"):
        read_schematic(path)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(UnsupportedFormatError, match="nope"):
        read_schematic(tmp_path / "nope.schem")
