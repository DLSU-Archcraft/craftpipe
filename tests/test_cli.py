import json
import os
import subprocess
import sys

import pytest

from craftpipe import mts, schem
from craftpipe.grid import BlockState, VoxelGrid

P = BlockState.parse


def run(*args, cwd=None):
    return subprocess.run([sys.executable, "-m", "craftpipe", *map(str, args)],
                          capture_output=True, text=True, cwd=cwd)


def make(tmp_path, *states, name="build.schem"):
    g = VoxelGrid((len(states), 1, 2))
    for i, s in enumerate(states):
        g.set(i, 0, 0, P(s))
    schem.write_schem(g, tmp_path / name)
    return tmp_path / name


def test_convert_writes_both_files(tmp_path):
    src = make(tmp_path, "stone", "white_wool")
    r = run("convert", src)
    assert r.returncode == 0, r.stderr
    size, names, ids, p2 = mts.read_mts(tmp_path / "build.mts")
    assert size == (2, 1, 2)
    assert set(names) == {"air", "mcl_core:stone", "mcl_wool:white"}
    manifest = json.loads((tmp_path / "build.craftpipe.json").read_text())
    assert manifest["complete"] is True and manifest["source"] == "build.schem"
    assert "build.mts" in r.stdout


def test_convert_output_option(tmp_path):
    src = make(tmp_path, "stone")
    r = run("convert", src, "-o", tmp_path / "out" / "cpu.mts")
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "out" / "cpu.mts").exists()
    assert (tmp_path / "out" / "cpu.craftpipe.json").exists()


def test_convert_unmapped_exits_1(tmp_path):
    src = make(tmp_path, "stone", "dragon_egg", "piston[facing=up]")
    r = run("convert", src, "--report", tmp_path / "r.json")
    assert r.returncode == 1
    assert "minecraft:dragon_egg" in r.stderr
    assert "pistons are not supported" in r.stderr
    assert not (tmp_path / "build.mts").exists()
    report = json.loads((tmp_path / "r.json").read_text())
    assert report["unmapped"]["minecraft:dragon_egg"]["count"] == 1


def test_convert_allow_unmapped(tmp_path):
    src = make(tmp_path, "stone", "dragon_egg")
    r = run("convert", src, "--allow-unmapped", "--report", tmp_path / "r.json")
    assert r.returncode == 0
    assert "not gradeable" in r.stderr.lower()
    assert json.loads((tmp_path / "build.craftpipe.json").read_text())["complete"] is False
    assert json.loads((tmp_path / "r.json").read_text())["counts"]["mcl_core:stone"] == 1


@pytest.mark.parametrize("content", [os.urandom(300), b"", b"\x1f\x8b\x08\x00garbage"])
def test_garbage_exits_2_without_traceback(tmp_path, content):
    bad = tmp_path / "junk.litematic"
    bad.write_bytes(content)
    r = run("convert", bad)
    assert r.returncode == 2
    assert "Traceback" not in r.stderr
    assert len(r.stderr.strip().splitlines()) == 1
    assert "junk.litematic" in r.stderr


def test_missing_file_exits_2(tmp_path):
    r = run("convert", tmp_path / "nope.schem")
    assert r.returncode == 2 and "Traceback" not in r.stderr


def test_inspect(tmp_path):
    src = make(tmp_path, "stone", "stone", "white_wool")
    r = run("inspect", src)
    assert r.returncode == 0, r.stderr
    assert "3 x 1 x 2" in r.stdout
    assert "minecraft:stone" in r.stdout and "2" in r.stdout
    assert not (tmp_path / "build.mts").exists()


def test_inspect_reports_unmapped(tmp_path):
    src = make(tmp_path, "stone", "dragon_egg")
    r = run("inspect", src)
    assert r.returncode == 1
    assert "minecraft:dragon_egg" in r.stdout


def test_library_convert(tmp_path):
    import craftpipe
    src = make(tmp_path, "stone")
    conv = craftpipe.convert(src)
    assert (tmp_path / "build.mts").exists()
    assert conv.report.counts == {"mcl_core:stone": 1}
