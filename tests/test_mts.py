import zlib

import pytest

from craftpipe import mts
from craftpipe.errors import CraftpipeError


def test_header_bytes(tmp_path):
    path = tmp_path / "a.mts"
    mts.write_mts(path, (2, 3, 4), ["air"], [0] * 24, [0] * 24)
    data = path.read_bytes()
    assert data[:12] == b"MTSM\x00\x04\x00\x02\x00\x03\x00\x04"
    assert data[12:15] == b"\x7f\x7f\x7f"           # one slice probability per Y layer
    assert data[15:17] == b"\x00\x01"               # name count
    assert data[17:22] == b"\x00\x03air"
    body = zlib.decompress(data[22:])
    assert len(body) == 24 * 4
    assert body[48:72] == b"\x7f" * 24              # param1


def test_roundtrip(tmp_path):
    path = tmp_path / "a.mts"
    size = (2, 3, 4)
    ids = [i % 3 for i in range(24)]
    p2 = [i % 256 for i in range(24)]
    mts.write_mts(path, size, ["air", "mcl_core:stone", "mcl_wool:white"], ids, p2)
    assert mts.read_mts(path) == (size, ["air", "mcl_core:stone", "mcl_wool:white"], ids, p2)


def test_index_order():
    assert mts.index((2, 3, 4), 1, 0, 0) == 1
    assert mts.index((2, 3, 4), 0, 1, 0) == 2
    assert mts.index((2, 3, 4), 0, 0, 1) == 6


@pytest.mark.parametrize("size", [(65536, 1, 1), (0, 1, 1), (1, 1, 70000)])
def test_oversize_raises(tmp_path, size):
    with pytest.raises(CraftpipeError):
        mts.write_mts(tmp_path / "a.mts", size, ["air"], [], [])


def test_length_mismatch_raises(tmp_path):
    with pytest.raises(CraftpipeError):
        mts.write_mts(tmp_path / "a.mts", (2, 1, 1), ["air"], [0], [0])
