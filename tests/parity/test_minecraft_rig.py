"""The Minecraft test rig itself: does it drive and read a real server
the way a player would?"""

import os
import socket

import pytest

from craftpipe import nbt
from circuits import Circuit
from harness import minecraft as mc
from harness.readings import Reading

STONE = "minecraft:stone"


def lever_lamp() -> Circuit:
    c = Circuit((5, 2, 1))
    c.input("a", (0, 1, 0)).dust_line(1, 1, 0, 3, 0).output("lamp", (4, 1, 0)).probe("mid", (2, 1, 0))
    return c


def test_lever_dust_lamp(module_minecraft):
    out = module_minecraft.run(lever_lamp(), [
        {"read": ["lamp", "mid"]},
        {"set": {"a": True}, "wait": 10, "read": ["lamp", "mid"]},
        {"set": {"a": False}, "wait": 10, "read": ["lamp", "mid"]},
    ])
    assert out[0] == {"lamp": Reading(False, None), "mid": Reading(False, 0)}
    assert out[1] == {"lamp": Reading(True, None), "mid": Reading(True, 14)}
    assert out[2] == {"lamp": Reading(False, None), "mid": Reading(False, 0)}


def test_lamp_on_mounting_block_follows_lever(module_minecraft):
    """A lamp that touches only the block the lever hangs on. A bare
    /setblock would leave it dark; a player's pull lights it."""
    c = Circuit((5, 2, 3))
    c.block(2, 1, 1, STONE)
    c.input("a", (3, 1, 1), "minecraft:lever[face=wall,facing=east,powered=false]")
    c.output("lamp", (1, 1, 1))
    out = module_minecraft.run(c, [
        {"set": {"a": True}, "wait": 6, "read": ["lamp"]},
        {"set": {"a": False}, "wait": 6, "read": ["lamp"]},
    ])
    assert [o["lamp"].on for o in out] == [True, False]


@pytest.mark.parametrize("button,pulse", [("stone_button", 10), ("oak_button", 15)])
def test_button_pulse_is_released_by_the_rig(module_minecraft, button, pulse):
    c = Circuit((5, 2, 3))
    c.block(2, 1, 1, STONE)
    c.input("b", (3, 1, 1), f"minecraft:{button}[face=wall,facing=east,powered=false]")
    c.output("lamp", (1, 1, 1)).probe("button", (3, 1, 1))
    (out,) = module_minecraft.run(c, [{"set": {"b": True}, "trace": pulse + 6, "read": ["lamp", "button"]}])
    pressed = [t["button"].on for t in out["trace"]]
    assert pressed == [True] * pulse + [False] * 7       # ticks 0..n; released at tick `pulse`
    assert out["trace"][0]["lamp"].on is True            # a pressed button acts at once
    assert out["lamp"].on is False


def test_first_read_is_settled(module_minecraft):
    """Placing a structure must leave redstone initialised: a NOT gate
    whose torch was saved lit beside unpowered dust."""
    c = Circuit((5, 3, 3))
    c.block(2, 1, 1, STONE)
    c.input("a", (2, 2, 1))
    c.block(3, 1, 1, "minecraft:redstone_wall_torch[facing=east,lit=true]")
    c.output("lamp", (4, 1, 1))
    out = module_minecraft.run(c, [{"read": ["lamp"]}, {"wait": 20, "read": ["lamp"]},
                                   {"set": {"a": True}, "wait": 6, "read": ["lamp"]}])
    assert [o["lamp"].on for o in out] == [True, True, False]


def test_container_items_survive_structure_placement(module_minecraft):
    c = Circuit((3, 2, 1))
    c.block(0, 1, 0, "minecraft:chest[facing=north,type=single,waterlogged=false]")
    c.grid.block_entities[(0, 1, 0)] = {"id": "minecraft:chest", "Items": [
        {"Slot": nbt.Byte(i), "id": "minecraft:redstone", "count": nbt.Int(64)} for i in range(27)]}
    c.block(1, 1, 0, "minecraft:comparator[facing=west,mode=compare,powered=false]")
    c.probe("cmp", (1, 1, 0)).dust((2, 1, 0)).probe("out", (2, 1, 0))
    (out,) = module_minecraft.run(c, [{"wait": 6, "read": ["cmp", "out"]}])
    assert out == {"cmp": Reading(True, 15), "out": Reading(True, 15)}


def test_two_circuits_in_one_server_do_not_interact(module_minecraft):
    first = module_minecraft.run(lever_lamp(), [{"set": {"a": True}, "wait": 6, "read": ["lamp"]}])
    second = module_minecraft.run(lever_lamp(), [{"wait": 6, "read": ["lamp"]}])
    assert first[0]["lamp"].on is True and second[0]["lamp"].on is False


def test_server_is_stopped_on_error(tmp_path):
    mc.require_minecraft()
    server = mc.MinecraftServer(tmp_path / "srv")
    with pytest.raises(ZeroDivisionError):
        with server:
            port, proc = server.rcon_port, server.proc
            1 / 0
    assert proc.poll() is not None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=2)


def test_no_eula_marker_means_skip_and_no_eula_file(tmp_path, monkeypatch):
    mc.require_minecraft()
    real = mc.fetch_tool.cache_dir()
    fake = tmp_path / "cache"
    fake.mkdir()
    for name in ("server.jar", "server.jar.sha1"):
        os.symlink(real / name, fake / name)
    monkeypatch.setenv("CRAFTPIPE_MINECRAFT_DIR", str(fake))
    with pytest.raises(pytest.skip.Exception, match="--accept-eula"):
        mc.require_minecraft()
    with pytest.raises(RuntimeError, match="EULA"):
        mc.MinecraftServer(tmp_path / "srv").start()
    assert not list(tmp_path.rglob("eula.txt"))
