import json

import pytest

from circuits import Circuit


def lever_lamp() -> Circuit:
    c = Circuit((5, 2, 1))
    c.input("a", (0, 1, 0))
    c.dust_line(1, 1, 0, 3, 0)
    c.output("lamp", (4, 1, 0))
    c.probe("mid", (2, 1, 0))
    return c


@pytest.mark.parametrize("fmt", ["schem", "litematic"])
def test_lever_dust_lamp(engine, fmt):
    out = engine.run(lever_lamp(), [
        {"read": ["lamp"]},
        {"set": {"a": True}, "wait": 10, "read": ["lamp", "mid"]},
        {"set": {"a": False}, "wait": 10, "read": ["lamp", "mid"]},
    ], fmt=fmt)
    assert out[0]["lamp"]["name"] == "mcl_redstone_lamp:lamp_off"
    assert out[1]["lamp"]["name"] == "mcl_redstone_lamp:lamp_on"
    assert out[1]["mid"]["param2"] & 15 == 14       # second dust from the lever (15, 14, 13)
    assert out[2]["lamp"]["name"] == "mcl_redstone_lamp:lamp_off"
    assert out[2]["mid"]["param2"] & 15 == 0


def test_dust_is_connected_after_place(engine):
    out = engine.run(lever_lamp(), [{"read": ["mid"]}])
    assert out[0]["mid"]["name"].startswith("mcl_redstone:wire_")


def staged(engine):
    c = lever_lamp()
    world, conv = engine.prepare(c)
    return world, conv


def test_loader_refuses_path_traversal(engine):
    world, conv = staged(engine)
    result = engine.run_raw(world, "../schems/circuit", conv.size, [])
    assert result["place_ok"] is False
    assert "invalid schematic name" in result["place_message"]


def test_loader_refuses_missing_manifest(engine):
    world, conv = staged(engine)
    (world / "schems/circuit.craftpipe.json").unlink()
    result = engine.run_raw(world, "circuit", conv.size, [{"read": [[4, 1, 0]]}])
    assert result["place_ok"] is False
    assert "manifest" in result["place_message"]


def test_loader_refuses_out_of_range_manifest(engine):
    world, conv = staged(engine)
    path = world / "schems/circuit.craftpipe.json"
    manifest = json.loads(path.read_text())
    manifest["containers"] = [{"pos": [99, 0, 0], "node": "mcl_chests:chest_small", "lists": {}}]
    path.write_text(json.dumps(manifest))
    result = engine.run_raw(world, "circuit", conv.size, [])
    assert result["place_ok"] is False
    assert "outside the schematic" in result["place_message"]


def test_loader_warns_when_not_gradeable(engine):
    c = lever_lamp()
    c.block(0, 1, 0, "minecraft:dragon_egg")
    world, conv = engine.prepare(c, allow_unmapped=True)
    result = engine.run_raw(world, "circuit", conv.size, [])
    assert result["place_ok"] is True
    assert result["place_message"].startswith("WARNING: not gradeable")


def test_trace_reads_every_tick(engine):
    out = engine.run(lever_lamp(), [{"set": {"a": True}, "trace": 6, "read": ["lamp"]}])
    trace = out[0]["trace"]
    assert len(trace) == 7                    # tick 0 plus six ticks
    assert trace[-1]["lamp"]["on"] is True and out[0]["lamp"]["on"] is True
    assert [t["lamp"]["on"] for t in trace] == sorted(t["lamp"]["on"] for t in trace)   # off, then on
