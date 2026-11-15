import json
import pathlib

from craftpipe import mapper, nbt
from craftpipe.grid import BlockState, VoxelGrid

P = BlockState.parse
REGISTRY = json.loads((pathlib.Path(__file__).parent / "data/mineclonia_registry.json").read_text())


def item(slot, name, count, legacy=False):
    key = "Count" if legacy else "count"
    return {"Slot": nbt.Byte(slot), "id": name, key: nbt.Byte(count) if legacy else nbt.Int(count)}


def chest_grid(items, state="chest[facing=north,type=single]", ident="minecraft:chest"):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P(state))
    g.block_entities[(0, 0, 0)] = {"id": ident, "Items": items}
    return g


def containers(grid, **kw):
    return mapper.map_grid(grid, **kw).manifest["containers"]


def test_chest_slots_are_one_based():
    (entry,) = containers(chest_grid([item(0, "minecraft:redstone", 5), item(26, "minecraft:redstone", 64)]))
    assert entry["node"] == "mcl_chests:chest_small"
    assert entry["pos"] == [0, 0, 0]
    assert entry["sizes"] == {"main": 27}
    assert entry["lists"] == {"main": [
        {"slot": 1, "name": "mcl_redstone:redstone", "count": 5},
        {"slot": 27, "name": "mcl_redstone:redstone", "count": 64}]}
    assert entry["signal"] == 1


def test_legacy_count_field():
    (entry,) = containers(chest_grid([item(3, "minecraft:redstone", 7, legacy=True)]))
    assert entry["lists"]["main"] == [{"slot": 4, "name": "mcl_redstone:redstone", "count": 7}]


def test_unknown_item_becomes_filler_with_warning():
    conv = mapper.map_grid(chest_grid([item(0, "minecraft:nautilus_shell", 64)]))
    (entry,) = conv.manifest["containers"]
    stack = entry["lists"]["main"][0]
    assert REGISTRY["items"][stack["name"]] == 64 and stack["count"] == 64
    assert any("minecraft:nautilus_shell" in w for w in conv.report.warnings)
    assert len(conv.report.warnings) == 1


def test_sixteen_stack_item_keeps_signal():
    (entry,) = containers(chest_grid([item(i, "minecraft:ender_pearl", 16) for i in range(5)]))
    assert all(REGISTRY["items"][s["name"]] == 16 for s in entry["lists"]["main"])
    assert entry["signal"] == 3          # 5/27 full -> floor(1 + 14 * 5/27)


def test_unstackable_item_keeps_signal():
    (entry,) = containers(chest_grid([item(i, "minecraft:diamond_sword", 1) for i in range(4)]))
    assert all(REGISTRY["items"][s["name"]] == 1 for s in entry["lists"]["main"])
    assert entry["signal"] == 3


def test_every_mapped_item_and_filler_has_the_right_stack_size():
    from craftpipe import containers as mod
    table = mod.load_items()
    for mc, mcl in table["items"].items():
        assert mcl in REGISTRY["items"], (mc, mcl)
        assert REGISTRY["items"][mcl] == mod.mc_stack_size(mc), (mc, mcl)
    for size, filler in table["filler"].items():
        assert REGISTRY["items"][filler] == int(size)


def test_furnace_slots():
    g = chest_grid([item(0, "minecraft:redstone", 64), item(1, "minecraft:stick", 2),
                    item(2, "minecraft:redstone", 1)],
                   state="furnace[facing=north,lit=false]", ident="minecraft:furnace")
    (entry,) = containers(g)
    assert entry["node"] == "mcl_furnaces:furnace"
    assert set(entry["lists"]) == {"src", "fuel", "dst"}
    assert entry["lists"]["src"] == [{"slot": 1, "name": "mcl_redstone:redstone", "count": 64}]
    assert entry["lists"]["fuel"][0]["count"] == 2
    assert entry["signal"] == 5          # floor(1 + 14 * (1 + 2/64 + 1/64) / 3)


def test_hopper_and_dropper_sizes():
    g = chest_grid([item(0, "minecraft:redstone", 64), item(1, "minecraft:redstone", 64)],
                   state="hopper[enabled=true,facing=down]", ident="minecraft:hopper")
    (entry,) = containers(g)
    assert entry["node"] == "mcl_hoppers:hopper" and entry["signal"] == 6
    g = chest_grid([item(i, "minecraft:redstone", 64) for i in range(3)],
                   state="dropper[facing=up,triggered=false]", ident="minecraft:dropper")
    (entry,) = containers(g)
    assert entry["node"] == "mcl_dispensers:dropper_up" and entry["signal"] == 5


def test_out_of_range_slot_is_dropped_with_warning():
    conv = mapper.map_grid(chest_grid([item(40, "minecraft:redstone", 1), item(-1, "minecraft:redstone", 1)]))
    (entry,) = conv.manifest["containers"]
    assert entry["lists"]["main"] == []
    assert any("slot" in w for w in conv.report.warnings)


def test_double_chest_signal_spans_both_halves_after_mirror():
    # MC: a north-facing LEFT half has its partner to the east.
    g = VoxelGrid((2, 1, 2))
    g.set(0, 0, 0, P("chest[facing=north,type=left]"))
    g.set(1, 0, 0, P("chest[facing=north,type=right]"))
    g.block_entities[(0, 0, 0)] = {"id": "minecraft:chest",
                                   "Items": [item(i, "minecraft:redstone", 64) for i in range(27)]}
    g.block_entities[(1, 0, 0)] = {"id": "minecraft:chest", "Items": []}
    conv = mapper.map_grid(g)
    by_pos = {tuple(e["pos"]): e for e in conv.manifest["containers"]}
    full, empty = by_pos[conv.to_luanti((0, 0, 0))], by_pos[conv.to_luanti((1, 0, 0))]
    assert len(full["lists"]["main"]) == 27 and empty["lists"]["main"] == []
    assert full["signal"] == empty["signal"] == 8
    # Mirroring swaps handedness: the MC "left" half becomes Mineclonia's right.
    assert full["node"] == "mcl_chests:chest_right" and empty["node"] == "mcl_chests:chest_left"


def test_block_entity_on_non_container_is_ignored():
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("stone"))
    g.block_entities[(0, 0, 0)] = {"id": "minecraft:chest", "Items": [item(0, "minecraft:redstone", 1)]}
    assert containers(g) == []


def test_container_without_block_entity_is_listed_empty():
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("barrel[facing=up,open=false]"))
    (entry,) = containers(g)
    assert entry["node"] == "mcl_barrels:barrel_closed" and entry["signal"] == 0


def test_lectern_with_book_sets_page_meta():
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("lectern[facing=north,has_book=true,powered=false]"))
    g.block_entities[(0, 0, 0)] = {"id": "minecraft:lectern", "Page": nbt.Int(2), "Book": {
        "id": "minecraft:written_book", "count": nbt.Int(1),
        "components": {"minecraft:written_book_content": {"pages": [{"raw": "a"}] * 5}}}}
    conv = mapper.map_grid(g)
    assert conv.names[1] == "mcl_lectern:lectern_with_book"
    assert conv.manifest["meta"] == [{"pos": [0, 0, 0], "fields": {"pages": "5", "page": "3"}, "signal": 8}]
    g2 = VoxelGrid((1, 1, 1))
    g2.set(0, 0, 0, P("lectern[facing=north,has_book=false]"))
    conv2 = mapper.map_grid(g2)
    assert conv2.names[1] == "mcl_lectern:lectern" and conv2.manifest["meta"] == []
