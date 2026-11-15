"""Run generated circuits in a real, unmodified, headless Minecraft server.

The server is driven over RCON with the game frozen (`/tick freeze`) and
advanced by hand (`/tick step`), so runs are deterministic. The public
interface counts redstone ticks (two game ticks each), like the Luanti
harness.

A command is not a player's hand, in two ways that matter here:

* `/setblock` on a lever does not notify the block the lever is mounted
  on, so things touching only that block would not react. After every
  change the rig swaps the mounting block for another solid block and
  straight back, which produces exactly that notification.
* A button set to pressed by command never releases (the release is
  scheduled by the press itself). The rig releases it after Minecraft's
  documented pulse length. That length is therefore an input to the rig,
  not something it measures.
"""

from __future__ import annotations

import atexit
import importlib.util
import pathlib
import re
import socket
import struct
import subprocess
import time

import pytest

from craftpipe import nbt
from craftpipe.grid import AIR, VoxelGrid

from .readings import Reading

REPO = pathlib.Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("fetch_minecraft_server",
                                               REPO / "tools/fetch_minecraft_server.py")
fetch_tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_tool)

DATA_VERSION = 3955                 # Java Edition 1.21.1
BASE_Y = 100
GAME_TICKS_PER_REDSTONE_TICK = 2
START_TIMEOUT = 180
# Documented pulse lengths, in redstone ticks (Minecraft Wiki, "Button").
STONE_BUTTON_TICKS = 10
WOODEN_BUTTON_TICKS = 15
_STONE_BUTTONS = ("minecraft:stone_button", "minecraft:polished_blackstone_button")
_DIRS = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0)}


def java_major_version() -> int | None:
    try:
        out = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r'version "(\d+)', out.stderr + out.stdout)
    return int(match.group(1)) if match else None


def require_minecraft() -> None:
    """Skip the calling test unless a Minecraft server can be run here."""
    ready, message = fetch_tool.status()
    if not ready:
        pytest.skip("Minecraft parity tests: " + message)
    major = java_major_version()
    if major is None or major < 21:
        pytest.skip("Minecraft parity tests need Java 21 or later on PATH (`java -version`)")


def structure_nbt(grid: VoxelGrid) -> bytes:
    """The grid as a Minecraft structure template (what /place template reads)."""
    palette, index, blocks = [], {}, []
    for pos, state in grid.cells():
        if state == AIR:
            continue
        if state not in index:
            index[state] = len(palette)
            entry = {"Name": state.name}
            if state.props:
                entry["Properties"] = {k: v for k, v in state.props}
            palette.append(entry)
        block = {"pos": [nbt.Int(v) for v in pos], "state": nbt.Int(index[state])}
        entity = grid.block_entities.get(pos)
        if entity is not None:
            block["nbt"] = dict(entity)
        blocks.append(block)
    return nbt.dumps({
        "DataVersion": nbt.Int(DATA_VERSION),
        "size": [nbt.Int(v) for v in grid.size],
        "palette": palette, "blocks": blocks, "entities": [],
    })


def _die_with_parent() -> None:
    """Run in the child before exec (Linux): have the kernel kill the
    server if the process that started it dies for any reason, including
    SIGTERM and SIGKILL, which atexit handlers never see."""
    import ctypes
    import signal
    try:
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGKILL)    # PR_SET_PDEATHSIG
    except OSError:
        pass


def _free_tcp_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Rcon:
    def __init__(self, port: int, password: str, proc: subprocess.Popen, timeout: float = START_TIMEOUT):
        deadline = time.time() + timeout
        while True:
            try:
                self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                break
            except OSError:
                if proc.poll() is not None:
                    raise RuntimeError("the Minecraft server exited while starting") from None
                if time.time() > deadline:
                    raise RuntimeError("the Minecraft server did not open its console in time") from None
                time.sleep(0.25)
        self.sock.settimeout(60)
        self._request(3, password)

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("the Minecraft server closed its console")
            buf += chunk
        return buf

    def _request(self, kind: int, body: str) -> str:
        payload = struct.pack("<ii", 1, kind) + body.encode() + b"\0\0"
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)
        (length,) = struct.unpack("<i", self._read(4))
        data = self._read(length)
        if struct.unpack("<i", data[:4])[0] == -1:
            raise RuntimeError("the Minecraft server refused the console password")
        return data[8:-2].decode(errors="replace")

    def cmd(self, text: str) -> str:
        return self._request(2, text)

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


class _Placed:
    """One circuit placed in the world, with its input state and clock."""

    def __init__(self, circuit, origin):
        self.circuit = circuit
        self.origin = origin
        self.inputs = {name: circuit.grid.get(*pos).get("powered") == "true"
                       for name, pos in circuit.inputs.items()}
        self.now = 0                       # redstone ticks since placement
        self.releases: list[tuple[int, str]] = []

    def world(self, pos):
        return tuple(o + p for o, p in zip(self.origin, pos))


class MinecraftServer:
    def __init__(self, directory: pathlib.Path):
        self.dir = pathlib.Path(directory)
        self.proc: subprocess.Popen | None = None
        self.rcon: Rcon | None = None
        self.rcon_port = 0
        self._next_x = 0
        self._count = 0

    # ---- lifecycle -------------------------------------------------------

    def start(self) -> "MinecraftServer":
        ready, message = fetch_tool.status()
        if not ready:
            raise RuntimeError(message)
        if self.proc is not None:
            raise RuntimeError("this server is already running")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.rcon_port = _free_tcp_port()
        (self.dir / "eula.txt").write_text("eula=true\n")
        (self.dir / "server.properties").write_text("\n".join([
            "enable-rcon=true", f"rcon.port={self.rcon_port}", "rcon.password=craftpipe",
            f"server-port={_free_tcp_port()}", "server-ip=127.0.0.1", "online-mode=false",
            "level-type=minecraft\\:flat",
            'generator-settings={"layers"\\:[],"biome"\\:"minecraft\\:the_void"}',
            "generate-structures=false", "spawn-protection=0", "max-tick-time=-1",
            "view-distance=2", "simulation-distance=2", "spawn-monsters=false",
            "spawn-animals=false", "spawn-npcs=false", "sync-chunk-writes=false",
            "enable-status=false", "broadcast-rcon-to-ops=false", "enable-query=false",
        ]) + "\n")
        log = open(self.dir / "stdout.log", "wb")
        self.proc = subprocess.Popen(
            ["java", "-Xmx1G", "-jar", str(fetch_tool.jar_path()), "nogui"],
            cwd=self.dir, stdout=log, stderr=subprocess.STDOUT, preexec_fn=_die_with_parent)
        log.close()
        atexit.register(self.stop)
        try:
            self.rcon = Rcon(self.rcon_port, "craftpipe", self.proc)
            self.rcon.cmd("tick freeze")
            self.rcon.cmd("tick rate 10000")
            self.rcon.cmd("gamerule randomTickSpeed 0")
        except BaseException:
            self.stop()
            raise
        return self

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            if self.rcon is not None:
                try:
                    self.rcon.cmd("stop")
                except (OSError, RuntimeError):
                    pass
                self.rcon.close()
                self.rcon = None
                proc.wait(timeout=30)
            else:
                # The console never came up, so there is nothing to ask
                # politely and nothing worth saving.
                proc.terminate()
                proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        finally:
            # Whatever happened above (including an interrupt), never
            # leave a server behind.
            if proc.poll() is None:
                proc.kill()
                proc.wait()

    def __enter__(self) -> "MinecraftServer":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()

    # ---- low level ---------------------------------------------------------

    def cmd(self, text: str) -> str:
        return self.rcon.cmd(text)

    def _gametime(self) -> int:
        return int(self.cmd("time query gametime").rsplit(" ", 1)[-1])

    def _step(self, redstone_ticks: int) -> None:
        if redstone_ticks <= 0:
            return
        game_ticks = redstone_ticks * GAME_TICKS_PER_REDSTONE_TICK
        target = self._gametime() + game_ticks
        self.cmd(f"tick step {game_ticks}")
        deadline = time.time() + 120
        while self._gametime() < target:
            if time.time() > deadline:
                raise RuntimeError("Minecraft did not finish stepping ticks")
            time.sleep(0.001)

    def _is(self, wpos, predicate: str) -> bool:
        x, y, z = wpos
        return "passed" in self.cmd(f"execute if block {x} {y} {z} {predicate}")

    def _setblock(self, wpos, state) -> None:
        x, y, z = wpos
        reply = self.cmd(f"setblock {x} {y} {z} {state}")
        if "Changed the block" not in reply:
            raise RuntimeError(f"setblock {state} at {wpos} failed: {reply}")

    # ---- circuits ----------------------------------------------------------

    def _place(self, circuit) -> _Placed:
        from circuits import java_dust_shapes
        java_dust_shapes(circuit.grid)
        self._count += 1
        name = f"circuit{self._count}"
        target = self.dir / "world/generated/minecraft/structures"
        target.mkdir(parents=True, exist_ok=True)
        (target / f"{name}.nbt").write_bytes(structure_nbt(circuit.grid))
        sx, _, sz = circuit.size
        ox = self._next_x
        self._next_x += (sx // 16 + 2) * 16          # at least one empty chunk between circuits
        self._load_area(ox, 0, ox + sx, sz)
        reply = self.cmd(f"place template minecraft:{name} {ox} {BASE_Y} 0")
        if "Loaded template" not in reply:
            raise RuntimeError(f"Minecraft could not place the circuit: {reply}")
        return _Placed(circuit, (ox, BASE_Y, 0))

    def _load_area(self, x0: int, z0: int, x1: int, z1: int) -> None:
        """Force-load the chunks under a circuit (plus a one-chunk margin)
        and wait until every one of them is fully active.

        A structure placed into a chunk that is not ticking yet silently
        loses redstone updates: a comparator beside a full chest stayed at
        0, and levers in some tiles of a large bench did nothing. Chunk
        activation takes a varying number of ticks, so poll for it.
        """
        cx0, cz0, cx1, cz1 = x0 // 16 - 1, z0 // 16 - 1, x1 // 16 + 1, z1 // 16 + 1
        reply = self.cmd(f"forceload add {cx0 * 16} {cz0 * 16} {cx1 * 16} {cz1 * 16}")
        if "force loaded" not in reply:
            raise RuntimeError(f"Minecraft would not load the area for a circuit: {reply}")
        pending = [(cx, cz) for cx in range(cx0, cx1 + 1) for cz in range(cz0, cz1 + 1)]
        deadline = time.time() + 120
        while pending:
            self._step(1)
            pending = [(cx, cz) for cx, cz in pending
                       if "passed" not in self.cmd(f"execute if loaded {cx * 16} {BASE_Y} {cz * 16}")]
            if pending and time.time() > deadline:
                raise RuntimeError(f"Minecraft never activated chunks {pending[:5]}")
        self._step(2)

    def _mount(self, placed: _Placed, pos):
        """Position of the block a lever or button at ``pos`` hangs on."""
        state = placed.circuit.grid.get(*pos)
        face = state.get("face", "wall")
        x, y, z = pos
        if face == "floor":
            return (x, y - 1, z)
        if face == "ceiling":
            return (x, y + 1, z)
        dx, dy, dz = _DIRS[state.get("facing", "north")]
        return (x - dx, y - dy, z - dz)

    def _drive(self, placed: _Placed, name: str, on: bool) -> None:
        pos = placed.circuit.inputs[name]
        state = placed.circuit.grid.get(*pos)
        self._setblock(placed.world(pos), state.with_props(powered="true" if on else "false"))
        # What a player's use also does: notify the mounting block's neighbours.
        mount = self._mount(placed, pos)
        original = placed.circuit.grid.get(*mount)
        if mount in placed.circuit.grid.block_entities:
            raise RuntimeError(f"input {name} is mounted on a container; the rig cannot drive it")
        other = "minecraft:cobblestone" if original.name == "minecraft:stone" else "minecraft:stone"
        self._setblock(placed.world(mount), other)
        self._setblock(placed.world(mount), original)
        placed.inputs[name] = on

    def _set(self, placed: _Placed, name: str, on: bool) -> None:
        pos = placed.circuit.inputs[name]
        block = placed.circuit.grid.get(*pos).name
        if block.endswith("_button"):
            if not on or placed.inputs[name]:
                return                              # buttons are only pressed; they release themselves
            self._drive(placed, name, True)
            pulse = STONE_BUTTON_TICKS if block in _STONE_BUTTONS else WOODEN_BUTTON_TICKS
            placed.releases.append((placed.now + pulse, name))
        elif placed.inputs[name] != on:
            self._drive(placed, name, on)

    def _advance(self, placed: _Placed, redstone_ticks: int) -> None:
        end = placed.now + redstone_ticks
        while True:
            due = sorted(r for r in placed.releases if r[0] <= end)
            if not due:
                break
            at, name = due[0]
            self._step(at - placed.now)
            placed.now = at
            placed.releases.remove((at, name))
            self._drive(placed, name, False)
        self._step(end - placed.now)
        placed.now = end

    def _read(self, placed: _Placed, name: str) -> Reading:
        pos = placed.circuit.outputs[name]
        wpos = placed.world(pos)
        block = placed.circuit.grid.get(*pos).name
        if block == "minecraft:redstone_wire":
            if self._is(wpos, "minecraft:redstone_wire[power=0]"):
                return Reading(False, 0)
            for power in range(15, 0, -1):
                if self._is(wpos, f"minecraft:redstone_wire[power={power}]"):
                    return Reading(True, power)
            raise RuntimeError(f"no redstone dust at {wpos} any more")
        if block == "minecraft:comparator":
            x, y, z = wpos
            reply = self.cmd(f"data get block {x} {y} {z} OutputSignal")
            match = re.search(r"(-?\d+)\s*$", reply)
            power = int(match.group(1)) if match else 0
            return Reading(self._is(wpos, "minecraft:comparator[powered=true]"), power)
        if block == "minecraft:hopper":
            return Reading(self._is(wpos, "minecraft:hopper[enabled=false]"), None)
        for prop in ("lit", "powered"):
            if self._is(wpos, f"{block}[{prop}=true]"):
                return Reading(True, None)
        return Reading(False, None)

    def dust_shapes(self, circuit, settle: int = 4) -> dict:
        """Place a circuit and return, for every redstone dust in it, the
        set of sides Minecraft itself connected it to:
        {(x, y, z): {"north", "east", ...}} in the circuit's coordinates."""
        placed = self._place(circuit)
        self._advance(placed, settle)
        shapes = {}
        for pos, state in circuit.grid.cells():
            if state.name != "minecraft:redstone_wire":
                continue
            wpos = placed.world(pos)
            shapes[pos] = {side for side in ("north", "east", "south", "west")
                           if not self._is(wpos, f"minecraft:redstone_wire[{side}=none]")}
        return shapes

    def run(self, circuit, steps, settle: int = 20) -> list[dict]:
        """Same contract as the Luanti Engine.run, with Reading values.

        steps: [{"set": {input: bool}, "trace": n, "wait": ticks, "read": [names]}]
        Each result maps the step's ``read`` names to a Reading; with
        ``trace`` it also has "trace": {name: Reading} at tick 0 (inputs
        just set, nothing stepped yet) and after each of the n redstone
        ticks that follow.
        """
        placed = self._place(circuit)
        self._advance(placed, settle)
        results = []
        for step in steps:
            for name, on in step.get("set", {}).items():
                self._set(placed, name, bool(on))
            names = step.get("read", [])
            result = {}
            if step.get("trace"):
                result["trace"] = [{n: self._read(placed, n) for n in names}]    # tick 0
                for _ in range(step["trace"]):
                    self._advance(placed, 1)
                    result["trace"].append({n: self._read(placed, n) for n in names})
            self._advance(placed, step.get("wait", 0))
            result.update({n: self._read(placed, n) for n in names})
            results.append(result)
        return results
