"""Mineclonia -> Minecraft. The main property: converting a build to
Mineclonia, back, and to Mineclonia again gives exactly the first result."""

import itertools
import json

import pytest

import craftpipe
import suites
from circuits import java_dust_shapes
from craftpipe import mapper, mts, nbt, reverse, rules, schem
from craftpipe.errors import UnmappedBlocksError
from craftpipe.grid import AIR, BlockState, VoxelGrid
from craftpipe.reader import read_schematic

P = BlockState.parse


def back(conv, **kw):
    return reverse.to_grid(conv.size, conv.names, conv.node_ids, conv.param2, conv.manifest, **kw)


def assert_round_trip(grid):
    first = mapper.map_grid(grid)
    again, report = back(first)
    second = mapper.map_grid(again)
    assert second.size == first.size
    cells_a = [(first.names[i], p) for i, p in zip(first.node_ids, first.param2)]
    cells_b = [(second.names[i], p) for i, p in zip(second.node_ids, second.param2)]
    assert cells_a == cells_b
    key = lambda e: tuple(e["pos"])                                       # noqa: E731
    assert sorted(second.manifest["containers"], key=key) == sorted(first.manifest["containers"], key=key)
    assert sorted(second.manifest["meta"], key=key) == sorted(first.manifest["meta"], key=key)
    return again, report


@pytest.mark.parametrize("name", ["orientation", "logic", "comparator", "rom", "adder_fast", "timing"])
def test_suites_round_trip(name):
    suite = (suites.timing if name == "timing" else suites.ALL[name])()
    java_dust_shapes(suite.circuit.grid)
    again, report = assert_round_trip(suite.circuit.grid)
    assert not report.unmapped
    # and the Minecraft block at every position is the same kind of block
    for (pos, a), (_, b) in zip(suite.circuit.grid.cells(), again.cells()):
        assert a.name == b.name, pos


def _states_for(mc, row):
    if isinstance(row, str):
        return [BlockState(mc)]
    domain = rules.DOMAINS[row["rule"]]
    keys = list(domain)
    return [BlockState(mc, tuple(zip(keys, values)))
            for values in itertools.product(*(domain[k] for k in keys))]


def test_every_supported_block_state_round_trips():
    table = mapper.load_table()
    checked = 0
    for mc, row in table["blocks"].items():
        for state in _states_for(mc, row):
            g = VoxelGrid((1, 1, 1))
            g.set(0, 0, 0, state)
            if "pale_oak" in mc:
                continue                    # newer than 1.21.1; covered separately
            if mc.endswith("_button") and state.get("powered") == "true":
                # by design: a pressed button comes back released
                again, _ = back(mapper.map_grid(g))
                assert again.get(0, 0, 0).get("powered") == "false"
                continue
            try:
                again, _ = assert_round_trip(g)
            except UnmappedBlocksError:
                continue                    # a state the forward rules reject (none today)
            want = "minecraft:air" if mc.endswith("air") else mc
            assert again.get(0, 0, 0).name == want, state
            checked += 1
    assert checked >= 600       # every remaining state of every supported block (634 today)


def one(state, entity=None):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P(state))
    if entity:
        g.block_entities[(0, 0, 0)] = entity
    again, report = back(mapper.map_grid(g))
    return again.get(0, 0, 0), again.block_entities.get((0, 0, 0)), report


def test_dust_sides_power_and_dots_survive():
    state, _, _ = one("redstone_wire[east=side,north=none,power=7,south=side,west=none]")
    assert state == P("redstone_wire[east=side,north=none,power=7,south=side,west=none]")
    state, _, _ = one("redstone_wire[east=none,north=none,power=0,south=none,west=none]")
    assert state == P("redstone_wire[east=none,north=none,power=0,south=none,west=none]")
    state, _, _ = one("redstone_wire[east=side,north=side,power=15,south=side,west=side]")
    assert state == P("redstone_wire[east=side,north=side,power=15,south=side,west=side]")


def test_climbing_dust_becomes_up():
    # wire_8a: connected east (climbing) and west. Power 9.
    grid, _ = reverse.to_grid((1, 1, 1), ["air", "mcl_redstone:wire_8a"], [1], [0x99], None)
    assert grid.get(0, 0, 0) == P("redstone_wire[east=up,north=none,power=9,south=none,west=side]")
    # Z is mirrored: Mineclonia -Z (bit 1) is Minecraft south.
    grid, _ = reverse.to_grid((1, 1, 1), ["air", "mcl_redstone:wire_15"], [1], [0], None)
    assert grid.get(0, 0, 0) == P("redstone_wire[east=none,north=side,power=0,south=up,west=none]")


def test_component_states_come_back_exactly():
    for text in [
        "repeater[delay=3,facing=west,locked=false,powered=true]",
        "repeater[delay=2,facing=north,locked=true,powered=false]",
        "comparator[facing=east,mode=subtract,powered=false]",
        "lever[face=wall,facing=south,powered=true]",
        "lever[face=ceiling,facing=east,powered=false]",
        "redstone_wall_torch[facing=north,lit=false]",
        "redstone_torch[lit=true]",
        "stone_button[face=wall,facing=west,powered=false]",
        "redstone_lamp[lit=true]",
        "smooth_stone_slab[type=top]",
        "hopper[enabled=false,facing=east]",
        "dropper[facing=down]",
        "chest[facing=east,type=left]",
        "trapped_chest[facing=north,type=single]",
        "lectern[facing=west,has_book=false]",
    ]:
        state, _, _ = one(text)
        assert state == P(text), text


def test_comparator_output_goes_back_into_the_block_entity():
    state, entity, _ = one("comparator[facing=south,mode=compare,powered=true]",
                           {"id": "minecraft:comparator", "OutputSignal": nbt.Int(9)})
    assert state == P("comparator[facing=south,mode=compare,powered=true]")
    assert entity["id"] == "minecraft:comparator" and entity["OutputSignal"] == 9
    assert type(entity["OutputSignal"]) is nbt.Int


def test_double_chest_halves_keep_their_sides_and_contents():
    g = VoxelGrid((2, 1, 2))
    g.set(0, 0, 0, P("chest[facing=north,type=left]"))
    g.set(1, 0, 0, P("chest[facing=north,type=right]"))
    g.block_entities[(0, 0, 0)] = {"id": "minecraft:chest", "Items": [
        {"Slot": nbt.Byte(i), "id": "minecraft:redstone", "count": nbt.Int(64)} for i in range(27)]}
    g.block_entities[(1, 0, 0)] = {"id": "minecraft:chest", "Items": []}
    again, _ = assert_round_trip(g)
    assert again.get(0, 0, 0) == P("chest[facing=north,type=left]")
    assert again.get(1, 0, 0) == P("chest[facing=north,type=right]")
    assert len(again.block_entities[(0, 0, 0)]["Items"]) == 27
    assert again.block_entities[(1, 0, 0)]["Items"] == []


def test_container_items_and_furnace_slots():
    _, entity, _ = one("chest[facing=north,type=single]", {"id": "minecraft:chest", "Items": [
        {"Slot": nbt.Byte(0), "id": "minecraft:redstone", "count": nbt.Int(5)},
        {"Slot": nbt.Byte(26), "id": "minecraft:ender_pearl", "count": nbt.Int(16)}]})
    assert entity["id"] == "minecraft:chest"
    assert [(int(i["Slot"]), i["id"], int(i["count"])) for i in entity["Items"]] == [
        (0, "minecraft:redstone", 5), (26, "minecraft:ender_pearl", 16)]
    assert type(entity["Items"][0]["Slot"]) is nbt.Byte
    _, entity, _ = one("furnace[facing=north,lit=false]", {"id": "minecraft:furnace", "Items": [
        {"Slot": nbt.Byte(0), "id": "minecraft:redstone", "count": nbt.Int(64)},
        {"Slot": nbt.Byte(1), "id": "minecraft:stick", "count": nbt.Int(2)},
        {"Slot": nbt.Byte(2), "id": "minecraft:stone", "count": nbt.Int(1)}]})
    assert [(int(i["Slot"]), i["id"]) for i in entity["Items"]] == [
        (0, "minecraft:redstone"), (1, "minecraft:stick"), (2, "minecraft:stone")]


def test_lectern_pages():
    state, entity, _ = one("lectern[facing=north,has_book=true,powered=false]", {
        "id": "minecraft:lectern", "Page": nbt.Int(2), "Book": {
            "id": "minecraft:written_book", "count": nbt.Int(1),
            "components": {"minecraft:written_book_content": {
                "title": {"raw": "t"}, "author": "a", "pages": [{"raw": '"x"'}] * 5}}}})
    assert state.get("has_book") == "true"
    assert entity["Page"] == 2
    assert len(entity["Book"]["components"]["minecraft:written_book_content"]["pages"]) == 5


def manifest_for(node, lists, sizes=None):
    return {"format": 1, "size": [1, 1, 1], "meta": [],
            "containers": [{"pos": [0, 0, 0], "node": node, "lists": lists}]}


def test_unknown_item_becomes_a_filler_of_the_same_stack_size():
    m = manifest_for("mcl_chests:chest_small", {"main": [
        {"slot": 1, "name": "mcl_farming:carrot_item", "count": 40, "max": 64},
        {"slot": 2, "name": "mcl_honey:honey_bottle", "count": 9, "max": 16},
        {"slot": 3, "name": "mcl_tools:pick_iron", "count": 1, "max": 1}]})
    grid, report = reverse.to_grid((1, 1, 1), ["air", "mcl_chests:chest_small"], [1], [0], m)
    items = [(i["id"], int(i["count"])) for i in grid.block_entities[(0, 0, 0)]["Items"]]
    assert items == [("minecraft:cobblestone", 40), ("minecraft:snowball", 9), ("minecraft:wooden_shovel", 1)]
    assert len(report.warnings) == 3 and "mcl_farming:carrot_item" in " ".join(report.warnings)


def test_item_count_is_capped_at_its_stack_size():
    m = manifest_for("mcl_chests:chest_small", {"main": [
        {"slot": 1, "name": "mcl_redstone:redstone", "count": 99, "max": 64}]})
    grid, _ = reverse.to_grid((1, 1, 1), ["air", "mcl_chests:chest_small"], [1], [0], m)
    assert int(grid.block_entities[(0, 0, 0)]["Items"][0]["count"]) == 64


def test_unknown_node_fails_with_a_report():
    names = ["air", "mcl_core:lava_source", "mcl_core:stone"]
    with pytest.raises(UnmappedBlocksError) as info:
        reverse.to_grid((3, 1, 1), names, [1, 1, 2], [0, 0, 0], None)
    entry = info.value.report.unmapped["mcl_core:lava_source"]
    assert entry.count == 2 and entry.positions == [(0, 0, 0), (1, 0, 0)]
    grid, report = reverse.to_grid((3, 1, 1), names, [1, 1, 2], [0, 0, 0], None, allow_unmapped=True)
    assert grid.get(0, 0, 0).name == "minecraft:bedrock" and "mcl_core:lava_source" in report.unmapped


@pytest.mark.parametrize("node,param2,want", [
    ("mcl_furnaces:furnace_active", 0, "minecraft:furnace"),
    ("mcl_barrels:barrel_open", 1, "minecraft:barrel"),
    ("mcl_chests:trapped_chest_on_small", 2, "minecraft:trapped_chest"),
    ("mcl_dispensers:dispenser", 32 + 1, "minecraft:dispenser"),
    ("mcl_lectern:lectern_with_book", 128 + 2, "minecraft:lectern"),
    ("mcl_target:target_on", 7, "minecraft:target"),
])
def test_nodes_that_only_exist_at_run_time(node, param2, want):
    grid, report = reverse.to_grid((1, 1, 1), ["air", node], [1], [param2], None)
    assert grid.get(0, 0, 0).name == want and not report.unmapped


def test_missing_manifest_warns_that_containers_are_empty():
    grid, report = reverse.to_grid((1, 1, 1), ["air", "mcl_chests:chest_small"], [1], [0], None)
    assert grid.block_entities[(0, 0, 0)] == {"id": "minecraft:chest", "Items": []}
    assert any("manifest" in w for w in report.warnings)


@pytest.mark.parametrize("ext", ["litematic", "schem"])
def test_to_minecraft_writes_both_formats_and_reads_them_back(tmp_path, ext):
    g = VoxelGrid((2, 1, 3))
    g.set(0, 0, 0, P("repeater[delay=2,facing=north,locked=false,powered=false]"))
    g.set(1, 0, 2, P("white_wool"))
    schem.write_schem(g, tmp_path / "a.schem")
    craftpipe.convert(tmp_path / "a.schem", tmp_path / "m" / "build.mts")
    report = craftpipe.to_minecraft(tmp_path / "m" / "build.mts", tmp_path / f"back.{ext}")
    again = read_schematic(tmp_path / f"back.{ext}")
    assert again.size == (2, 1, 3) and again.data_version == 3955
    assert again.get(0, 0, 0) == P("repeater[delay=2,facing=north,locked=false,powered=false]")
    assert again.get(1, 0, 2) == P("white_wool") and again.get(1, 0, 0) == AIR
    assert not report.unmapped


def test_to_minecraft_default_output_and_manifest_mismatch(tmp_path):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("stone"))
    schem.write_schem(g, tmp_path / "a.schem")
    craftpipe.convert(tmp_path / "a.schem", tmp_path / "build.mts")
    craftpipe.to_minecraft(tmp_path / "build.mts")
    assert (tmp_path / "build.litematic").exists()
    manifest = json.loads((tmp_path / "build.craftpipe.json").read_text())
    manifest["mts_sha1"] = "0" * 40
    (tmp_path / "build.craftpipe.json").write_text(json.dumps(manifest))
    with pytest.raises(craftpipe.CraftpipeError, match="does not belong"):
        craftpipe.to_minecraft(tmp_path / "build.mts")


def test_manifest_written_by_lua_with_null_for_empty_tables():
    # Luanti writes an empty table as null.
    m = {"format": 1, "size": [1, 1, 1], "meta": None,
         "containers": [{"pos": [0, 0, 0], "node": "mcl_chests:chest_small", "lists": None}]}
    grid, _ = reverse.to_grid((1, 1, 1), ["air", "mcl_chests:chest_small"], [1], [0], m)
    assert grid.block_entities[(0, 0, 0)]["Items"] == []
    m["containers"] = None
    reverse.to_grid((1, 1, 1), ["air", "mcl_chests:chest_small"], [1], [0], m)


# ---- found by review ---------------------------------------------------------

import pathlib      # noqa: E402

MC_BLOCKS = json.loads((pathlib.Path(__file__).parent / "data/minecraft_1_21_1_blocks.json").read_text())["blocks"]


def test_every_reverse_state_exists_in_minecraft_1_21_1():
    """The output is a 1.21.1 file: every block and property value written
    must be one that version has (a block it lacks loads as air)."""
    table = reverse._lookup()
    assert len(table) > 300
    for (node, param2), state in table.items():
        assert state.name in MC_BLOCKS, (node, state.name)
        for key, value in state.props:
            assert value in MC_BLOCKS[state.name].get(key, []), (node, str(state))
    dust = reverse.node_to_state("mcl_redstone:wire_8a", 0x99)
    for key, value in dust.props:
        assert value in MC_BLOCKS[dust.name][key]


@pytest.mark.parametrize("node", ["mcl_trees:wood_pale_oak", "mcl_stairs:slab_pale_oak",
                                  "mcl_buttons:button_pale_oak_off"])
def test_blocks_newer_than_1_21_1_are_reported_not_written(node):
    with pytest.raises(UnmappedBlocksError) as info:
        reverse.to_grid((1, 1, 1), ["air", node], [1], [0], None)
    assert node in info.value.report.unmapped
    assert "1.21.1" in info.value.report.unmapped[node].reason


def test_forward_direction_still_accepts_pale_oak():
    conv = mapper.map_grid(_grid("pale_oak_planks"))
    assert conv.names[1] == "mcl_trees:wood_pale_oak"


def _grid(state):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P(state))
    return g


def test_pressed_button_is_exported_released_with_a_warning():
    grid, report = reverse.to_grid((2, 1, 1), ["air", "mcl_buttons:button_stone_on"], [1, 1], [1, 1], None)
    assert grid.get(0, 0, 0).get("powered") == "false"
    (warning,) = report.warnings
    assert "button" in warning and "2" in warning


@pytest.mark.parametrize("node,param2", [
    ("mcl_lever:lever_off", 5), ("mcl_lever:lever_on", 14), ("mcl_buttons:button_stone_off", 6),
    ("mcl_redstone_torch:redstone_torch_on", 5), ("mcl_repeaters:repeater_off_1", 7),
])
def test_unknown_orientation_is_unmapped_not_guessed(node, param2):
    assert reverse.node_to_state(node, param2) is None
    with pytest.raises(UnmappedBlocksError) as info:
        reverse.to_grid((1, 1, 1), ["air", node], [1], [param2], None)
    assert "orientation" in info.value.report.unmapped[node].reason


def test_param2_is_ignored_where_it_carries_no_orientation():
    assert reverse.node_to_state("mcl_core:glass", 3).name == "minecraft:glass"
    assert reverse.node_to_state("mcl_core:dirt_with_grass", 17).name == "minecraft:grass_block"
    assert reverse.node_to_state("mcl_redstone_lamp:lamp_on", 9) == P("redstone_lamp[lit=true]")
    assert reverse.node_to_state("mcl_dispensers:dispenser", 32 + 1) == \
        reverse.node_to_state("mcl_dispensers:dispenser", 1)
    assert reverse.node_to_state("mcl_lectern:lectern_with_book", 128 + 2) == \
        reverse.node_to_state("mcl_lectern:lectern_with_book", 2)
    assert reverse.node_to_state("mcl_comparators:comparator_on_sub", 4 * 9 + 3) == \
        reverse.node_to_state("mcl_comparators:comparator_on_sub", 3)


def test_run_time_nodes_come_back_as_the_resting_block():
    assert reverse.node_to_state("mcl_furnaces:furnace_active", 1) == \
        reverse.node_to_state("mcl_furnaces:furnace", 1)
    assert reverse.node_to_state("mcl_barrels:barrel_open", 1) == \
        reverse.node_to_state("mcl_barrels:barrel_closed", 1)
    assert reverse.node_to_state("mcl_chests:trapped_chest_on_left", 2) == \
        reverse.node_to_state("mcl_chests:trapped_chest_left", 2)


def test_missing_manifest_warning_mentions_lectern_books():
    _, report = reverse.to_grid((1, 1, 1), ["air", "mcl_lectern:lectern_with_book"], [1], [0], None)
    assert any("lectern" in w for w in report.warnings)


def test_unknown_output_extension_is_refused(tmp_path):
    g = _grid("stone")
    schem.write_schem(g, tmp_path / "a.schem")
    craftpipe.convert(tmp_path / "a.schem", tmp_path / "build.mts")
    with pytest.raises(craftpipe.CraftpipeError, match="litematic"):
        craftpipe.to_minecraft(tmp_path / "build.mts", tmp_path / "out.nbt")
    assert not (tmp_path / "out.nbt").exists()


def test_large_litematic_is_written_in_reasonable_time(tmp_path):
    import time
    from craftpipe import litematic
    g = VoxelGrid((100, 30, 100))            # 300,000 cells
    for x in range(0, 100, 3):
        for z in range(100):
            g.set(x, 0, z, P("stone") if (x + z) % 2 else P("white_wool"))
    started = time.time()
    litematic.write_litematic(g, tmp_path / "big.litematic")
    assert time.time() - started < 5
    again = read_schematic(tmp_path / "big.litematic")
    assert again.get(3, 0, 1) == g.get(3, 0, 1) and again.get(99, 29, 99) == AIR
    assert again.counts() == g.counts()
