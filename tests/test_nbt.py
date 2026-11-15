import pytest

from craftpipe import nbt
from craftpipe.errors import UnsupportedFormatError


def sample():
    return {
        "b": nbt.Byte(-3),
        "s": nbt.Short(1234),
        "i": nbt.Int(-70000),
        "l": nbt.Long(2**40),
        "f": nbt.Float(1.5),
        "d": nbt.Double(-2.25),
        "str": "héllo",
        "ba": nbt.ByteArray([1, -2, 3]),
        "ia": nbt.IntArray([1, -2, 300000]),
        "la": nbt.LongArray([5, -6]),
        "nested": {"x": nbt.Int(1)},
        "list": [{"a": nbt.Byte(1)}, {"a": nbt.Byte(2)}],
        "strs": ["a", "b"],
        "empty": [],
    }


def assert_same(a, b):
    assert type(a) is type(b), (a, b)
    if isinstance(a, dict):
        assert a.keys() == b.keys()
        for k in a:
            assert_same(a[k], b[k])
    elif isinstance(a, list):
        assert len(a) == len(b)
        for x, y in zip(a, b):
            assert_same(x, y)
    else:
        assert a == b


def test_roundtrip_all_tags():
    name, root = nbt.loads(nbt.dumps(sample(), name="root"))
    assert name == "root"
    assert_same(root, sample())


def test_negative_long_array():
    data = {"la": nbt.LongArray([-1, 2**63 - 1])}
    _, root = nbt.loads(nbt.dumps(data))
    assert root["la"] == [-1, 2**63 - 1]
    assert type(root["la"]) is nbt.LongArray


def test_reads_uncompressed():
    _, root = nbt.loads(nbt.dumps(sample(), gzipped=False))
    assert_same(root, sample())


def test_load_from_path(tmp_path):
    p = tmp_path / "x.nbt"
    p.write_bytes(nbt.dumps({"a": nbt.Int(7)}))
    assert nbt.load(p)[1]["a"] == 7


@pytest.mark.parametrize("bad", ["truncated", "garbage", "empty"])
def test_truncated_raises(bad):
    data = {"truncated": nbt.dumps(sample())[:20], "garbage": b"not nbt", "empty": b""}[bad]
    with pytest.raises(UnsupportedFormatError):
        nbt.loads(data)


def test_truncated_uncompressed_raises():
    with pytest.raises(UnsupportedFormatError):
        nbt.loads(nbt.dumps(sample(), gzipped=False)[:30])
