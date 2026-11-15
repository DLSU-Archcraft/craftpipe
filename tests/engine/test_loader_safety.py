"""The loader must not let a hand-made schematic or manifest do anything a
converted build could not."""

import hashlib
import json

from craftpipe import mts
from circuits import Circuit


def simple() -> Circuit:
    c = Circuit((5, 2, 1))
    c.input("a", (0, 1, 0)).dust_line(1, 1, 0, 3, 0).output("lamp", (4, 1, 0))
    return c


def edit_manifest(world, fn):
    path = world / "schems/circuit.craftpipe.json"
    manifest = json.loads(path.read_text())
    fn(manifest)
    path.write_text(json.dumps(manifest))


def test_schematic_with_foreign_node_is_refused(engine):
    world, conv = engine.prepare(simple())
    names = ["air", "mcl_core:stone", "mcl_commandblock:commandblock_off"]
    ids = [1, 1, 2, 0, 0, 0]
    path = world / "schems/circuit.mts"
    mts.write_mts(path, (3, 2, 1), names, ids, [0] * 6)
    edit_manifest(world, lambda m: m.update(
        size=[3, 2, 1], containers=[], cross_dust=[],
        mts_sha1=hashlib.sha1(path.read_bytes()).hexdigest(),
        meta=[{"pos": [2, 0, 0], "fields": {"commander": "singleplayer", "commands": "grant singleplayer all"}}]))
    result = engine.run_raw(world, "circuit", (3, 2, 1), [{"read": [[2, 0, 0]]}])
    assert result["place_ok"] is False
    assert "mcl_commandblock:commandblock_off" in result["place_message"]


def test_manifest_cannot_set_arbitrary_metadata_or_inventories(engine):
    world, conv = engine.prepare(simple())
    lamp = [4, 1, 0]
    edit_manifest(world, lambda m: m.update(
        meta=[{"pos": lamp, "fields": {"commander": "x", "commands": "y", "formspec": "z", "pages": "9"}}],
        containers=[{"pos": lamp, "node": "mcl_chests:chest_small", "sizes": {"main": 27, "evil": 5},
                     "lists": {"main": [{"slot": 1, "name": "mcl_core:cobble", "count": 1}]}}]))
    result = engine.run_raw(world, "circuit", conv.size, [{"read": [lamp]}])
    assert result["place_ok"] is True
    read = result["steps"][0][0]
    assert read["name"] == "mcl_redstone_lamp:lamp_off"
    assert not read["meta"]                   # nothing was written (empty table arrives as null)
    assert read["main_size"] == 0
    assert result["place_stats"]["containers"] == 0


def test_manifest_from_another_conversion_is_refused(engine):
    world, conv = engine.prepare(simple())
    edit_manifest(world, lambda m: m.update(mts_sha1="0" * 40))
    result = engine.run_raw(world, "circuit", conv.size, [])
    assert result["place_ok"] is False
    assert "does not belong" in result["place_message"]


def test_reconverted_build_replaces_the_old_one_in_the_same_session(engine):
    """Luanti caches schematics by file name; a re-converted build of the
    same size must not be silently replaced by the stale copy."""
    first = simple()
    world, conv = engine.prepare(first)
    second = simple()
    second.block(2, 1, 0, "minecraft:white_wool")           # same size, different blocks
    import craftpipe
    src = engine.tmp / "second.schem"
    second.save(src)
    craftpipe.convert(src, world / "schems/second.mts")
    result = engine.run_raw(world, "circuit", conv.size, [
        {"read": [[2, 1, 0]]},
        {"replace_with": "second", "wait": 5, "read": [[2, 1, 0]]},
    ])
    assert result["place_ok"] and result["second_place_ok"], result
    assert result["steps"][0][0]["name"].startswith("mcl_redstone:wire_")
    assert result["steps"][1][0]["name"] == "mcl_wool:white"


def test_unregistered_item_is_reported_not_silently_skipped(engine):
    c = Circuit((1, 2, 1))
    c.block(0, 1, 0, "minecraft:chest[facing=north,type=single]")
    c.grid.block_entities[(0, 1, 0)] = {"id": "minecraft:chest", "Items": []}
    world, conv = engine.prepare(c)
    edit_manifest(world, lambda m: m["containers"][0]["lists"].update(
        main=[{"slot": 1, "name": "nosuchmod:item", "count": 1},
              {"slot": 99, "name": "mcl_core:cobble", "count": 1},
              {"slot": 2, "name": "mcl_core:cobble", "count": 3}]))
    result = engine.run_raw(world, "circuit", conv.size, [])
    assert result["place_ok"] is True
    assert result["place_stats"]["skipped_stacks"] == 2
    assert "2 item stack(s) could not be placed" in result["place_message"]
