"""Run converted circuits in a real headless Luanti + Mineclonia server."""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import subprocess

import pytest

import craftpipe

REPO = pathlib.Path(__file__).resolve().parents[2]
GAME_DIRS = [pathlib.Path.home() / ".minetest/games/mineclonia",
             pathlib.Path.home() / ".local/share/luanti/games/mineclonia",
             pathlib.Path("/usr/share/luanti/games/mineclonia")]
LUANTI = shutil.which("luanti") or shutil.which("minetest")
ORIGIN = [0, 10, 0]
TIMEOUT = 180


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Engine:
    def __init__(self, tmp_path: pathlib.Path):
        self.tmp = tmp_path
        self.runs = 0

    def _world(self) -> pathlib.Path:
        self.runs += 1
        world = self.tmp / f"world{self.runs}"
        (world / "worldmods").mkdir(parents=True)
        (world / "schems").mkdir()
        (world / "craftpipe_test").mkdir()
        shutil.copytree(REPO / "mod/craftpipe_loader", world / "worldmods/craftpipe_loader")
        shutil.copytree(REPO / "tests/engine/craftpipe_test", world / "worldmods/craftpipe_test")
        (world / "world.mt").write_text(
            "gameid = mineclonia\nworld_name = craftpipe_test\nbackend = sqlite3\n"
            "player_backend = sqlite3\nauth_backend = sqlite3\nmod_storage_backend = sqlite3\n")
        (world / "luanti.conf").write_text(
            f"mg_name = singlenode\nport = {_free_port()}\nbind_address = 127.0.0.1\n"
            "server_announce = false\nmcl_redstone_time_budget = 1000\n"
            "secure.enable_security = true\n")
        return world

    def run_raw(self, world: pathlib.Path, name: str, size, steps, settle: int = 20) -> dict:
        """Run a job against files already in <world>/schems/. Positions in
        ``steps`` are schematic-relative Luanti coordinates."""
        job = {"name": name, "origin": ORIGIN, "size": list(size), "steps": steps, "settle": settle}
        (world / "craftpipe_test/job.json").write_text(json.dumps(job))
        log = world / "server.log"
        with open(log, "wb") as out:
            proc = subprocess.Popen(
                [LUANTI, "--server", "--world", str(world), "--config", str(world / "luanti.conf"),
                 "--logfile", str(world / "debug.txt")],
                stdout=out, stderr=subprocess.STDOUT)
            try:
                proc.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                raise AssertionError(
                    f"Luanti did not finish within {TIMEOUT}s; see {log}") from None
        result_path = world / "craftpipe_test/result.json"
        if not result_path.exists():
            tail = log.read_text(errors="replace")[-3000:]
            raise AssertionError(f"Luanti exited without a result. Log tail:\n{tail}")
        result = json.loads(result_path.read_text())
        if result.get("error"):
            raise AssertionError(f"engine-side error: {result['error']}")
        return result

    def prepare(self, circuit, fmt: str = "schem", name: str = "circuit", **convert_kw):
        """Save, convert and stage a circuit. Returns (world, conversion)."""
        world = self._world()
        src = self.tmp / f"{name}{self.runs}.{fmt}"
        circuit.save(src)
        conv = craftpipe.convert(src, world / "schems" / f"{name}.mts", **convert_kw)
        return world, conv

    def run(self, circuit, steps, fmt: str = "schem", settle: int = 20) -> list[dict]:
        """steps: [{"set": {input: bool}, "wait": ticks, "read": [output, ...]}]
        Returns one {output: {"name", "param2", "on"}} dict per step."""
        world, conv = self.prepare(circuit, fmt)
        raw_steps = []
        for step in steps:
            raw_steps.append({
                "set": [{"pos": list(conv.to_luanti(circuit.inputs[k])), "on": bool(v)}
                        for k, v in step.get("set", {}).items()],
                "wait": step.get("wait", 0),
                "read": [list(conv.to_luanti(circuit.outputs[k])) for k in step.get("read", [])],
            })
        result = self.run_raw(world, "circuit", conv.size, raw_steps, settle)
        assert result["place_ok"], result["place_message"]
        return [dict(zip(step.get("read", []), reads))
                for step, reads in zip(steps, result["steps"])]


@pytest.fixture
def engine(tmp_path):
    if LUANTI is None:
        pytest.skip("engine tests need the `luanti` binary on PATH")
    if not any(d.is_dir() for d in GAME_DIRS):
        pytest.skip("engine tests need the Mineclonia game installed (e.g. ~/.minetest/games/mineclonia)")
    return Engine(tmp_path)
