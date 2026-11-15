import json
import pathlib

import pytest

from craftpipe import mapper, mts
from craftpipe.errors import UnmappedBlocksError
from craftpipe.grid import BlockState, VoxelGrid

P = BlockState.parse
REGISTRY = json.loads((pathlib.Path(__file__).parent / "data/mineclonia_registry.json").read_text())
NODES = REGISTRY["nodes"]


def grid_of(*states, size=None):
    g = VoxelGrid(size or (len(states), 1, 1))
    for i, s in enumerate(states):
        g.set(i, 0, 0, P(s))
    return g


def node_at(conv, src_pos):
    i = mts.index(conv.size, *conv.to_luanti(src_pos))
    return conv.names[conv.node_ids[i]], conv.param2[i]


def all_states_for(name):
    """A few representative states so rule rows can be exercised."""
    return [name]


def test_every_plain_target_exists_in_mineclonia():
    table = mapper.load_table()
    missing = {mc: t for mc, t in table["blocks"].items()
               if isinstance(t, str) and t != "air" and t not in NODES}
    assert not missing


def test_every_rule_row_names_a_known_rule():
    from craftpipe import rules
    table = mapper.load_table()
    unknown = {mc: t["rule"] for mc, t in table["blocks"].items()
               if isinstance(t, dict) and t["rule"] not in rules.RULES}
    assert not unknown


def test_placeholder_exists():
    assert mapper.PLACEHOLDER in NODES


def test_maps_and_mirrors():
    g = VoxelGrid((1, 1, 2))
    g.set(0, 0, 0, P("stone"))
    g.set(0, 0, 1, P("white_wool"))
    conv = mapper.map_grid(g)
    assert conv.names[conv.node_ids[mts.index(conv.size, 0, 0, 1)]] == "mcl_core:stone"
    assert conv.names[conv.node_ids[mts.index(conv.size, 0, 0, 0)]] == "mcl_wool:white"
    assert conv.report.counts == {"mcl_core:stone": 1, "mcl_wool:white": 1}
    assert conv.manifest["complete"] is True
    assert conv.manifest["size"] == [1, 1, 2]


def test_air_is_air_and_first_name():
    conv = mapper.map_grid(grid_of("air", "cave_air", "stone"))
    assert conv.names[0] == "air"
    assert node_at(conv, (0, 0, 0)) == ("air", 0)
    assert node_at(conv, (1, 0, 0)) == ("air", 0)


def test_extra_properties_ignored():
    conv = mapper.map_grid(grid_of("stone[waterlogged=false]", "gray_concrete[foo=bar]"))
    assert node_at(conv, (0, 0, 0))[0] == "mcl_core:stone"
    assert node_at(conv, (1, 0, 0))[0] == "mcl_colorblocks:concrete_grey"


def test_unmapped_raises_with_report():
    g = grid_of(*["dragon_egg"] * 7)
    with pytest.raises(UnmappedBlocksError) as info:
        mapper.map_grid(g)
    entry = info.value.report.unmapped["minecraft:dragon_egg"]
    assert entry.count == 7
    assert entry.positions == [(i, 0, 0) for i in range(5)]
    assert entry.reason is None


def test_unmapped_positions_are_source_coordinates():
    g = VoxelGrid((1, 1, 3))
    g.set(0, 0, 0, P("dragon_egg"))
    with pytest.raises(UnmappedBlocksError) as info:
        mapper.map_grid(g)
    assert info.value.report.unmapped["minecraft:dragon_egg"].positions == [(0, 0, 0)]


def test_unsupported_reason():
    with pytest.raises(UnmappedBlocksError) as info:
        mapper.map_grid(grid_of("piston[facing=up,extended=false]"))
    (entry,) = info.value.report.unmapped.values()
    assert entry.reason == "pistons are not supported"


def test_allow_unmapped_marks_incomplete():
    conv = mapper.map_grid(grid_of("dragon_egg", "stone"), allow_unmapped=True)
    assert node_at(conv, (0, 0, 0))[0] == mapper.PLACEHOLDER
    assert conv.manifest["complete"] is False
    assert conv.manifest["substituted"] == {"minecraft:dragon_egg": 1}
    assert "minecraft:dragon_egg" in conv.report.unmapped


def test_slab_rule():
    conv = mapper.map_grid(grid_of("smooth_stone_slab[type=bottom]", "smooth_stone_slab[type=top]",
                                   "smooth_stone_slab[type=double]", "oak_slab"))
    got = [node_at(conv, (i, 0, 0))[0] for i in range(4)]
    assert got == ["mcl_stairs:slab_stone", "mcl_stairs:slab_stone_top",
                   "mcl_stairs:slab_stone_double", "mcl_stairs:slab_oak"]
    assert all(n in NODES for n in got)


def test_all_slab_rows_resolve_to_registered_nodes():
    table = mapper.load_table()
    for mc, row in table["blocks"].items():
        if isinstance(row, dict) and row["rule"] == "slab":
            for kind in ("bottom", "top", "double"):
                conv = mapper.map_grid(grid_of(f"{mc}[type={kind}]"))
                assert node_at(conv, (0, 0, 0))[0] in NODES, (mc, kind)


def test_to_luanti():
    conv = mapper.map_grid(VoxelGrid((3, 2, 4)))
    assert conv.to_luanti((1, 0, 0)) == (1, 0, 3)
    assert conv.to_luanti((2, 1, 3)) == (2, 1, 0)


def test_report_json_shape():
    conv = mapper.map_grid(grid_of("dragon_egg", "stone"), allow_unmapped=True)
    data = conv.report.to_json()
    assert data["unmapped"]["minecraft:dragon_egg"] == {
        "count": 1, "positions": [[0, 0, 0]], "reason": None}
    assert data["counts"]["mcl_core:stone"] == 1
    assert data["warnings"] == []
    json.dumps(data)


def test_lever_rule():
    conv = mapper.map_grid(grid_of("lever[face=floor,facing=north,powered=false]",
                                   "lever[face=floor,facing=north,powered=true]"))
    assert node_at(conv, (0, 0, 0))[0] == "mcl_lever:lever_off"
    assert node_at(conv, (1, 0, 0))[0] == "mcl_lever:lever_on"


def test_lever_wall_facings_are_distinct_and_mirrored():
    seen = {}
    for facing in ("north", "south", "east", "west"):
        conv = mapper.map_grid(grid_of(f"lever[face=wall,facing={facing},powered=false]"))
        seen[facing] = node_at(conv, (0, 0, 0))[1]
    assert len(set(seen.values())) == 4
    # Luanti facedir of the support block's direction: 0=+Z 1=+X 2=-Z 3=-X.
    # MC facing=north (lever sticks out to -Z, support at +Z) mirrors to
    # support at -Z -> facedir 2.
    assert seen == {"north": 2, "south": 0, "east": 3, "west": 1}


def test_dust_rule_carries_power():
    conv = mapper.map_grid(grid_of("redstone_wire[power=7,north=side,south=none,east=none,west=up]",
                                   "redstone_wire[power=0]"))
    assert node_at(conv, (0, 0, 0)) == ("mcl_redstone:wire_06", 0x77)
    assert node_at(conv, (1, 0, 0)) == ("mcl_redstone:redstone", 0)


def test_lamp_rule():
    conv = mapper.map_grid(grid_of("redstone_lamp[lit=false]", "redstone_lamp[lit=true]", "redstone_lamp"))
    assert [node_at(conv, (i, 0, 0))[0] for i in range(3)] == [
        "mcl_redstone_lamp:lamp_off", "mcl_redstone_lamp:lamp_on", "mcl_redstone_lamp:lamp_off"]


FACINGS = ("north", "south", "east", "west")


def one(state):
    conv = mapper.map_grid(grid_of(state))
    return node_at(conv, (0, 0, 0))


@pytest.mark.parametrize("delay", [1, 2, 3, 4])
@pytest.mark.parametrize("powered", ["true", "false"])
def test_repeater_names(delay, powered):
    name, _ = one(f"repeater[delay={delay},facing=north,locked=false,powered={powered}]")
    assert name == f"mcl_repeaters:repeater_{'on' if powered == 'true' else 'off'}_{delay}"
    assert name in NODES


def test_repeater_param2_is_output_direction():
    # MC `facing` names the input side; output is opposite. After the Z
    # mirror MC north (-Z) becomes Luanti +Z. 4dir: 0=+Z 1=+X 2=-Z 3=-X.
    got = {f: one(f"repeater[delay=1,facing={f}]")[1] for f in FACINGS}
    assert got == {"north": 2, "south": 0, "east": 3, "west": 1}


def test_locked_repeater_keeps_delay_in_param2():
    assert one("repeater[delay=3,facing=south,locked=true,powered=true]") == \
        ("mcl_repeaters:repeater_on_locked", 3 * 4 + 0)
    assert one("repeater[delay=2,facing=east,locked=true,powered=false]") == \
        ("mcl_repeaters:repeater_off_locked", 2 * 4 + 3)


@pytest.mark.parametrize("mode,suffix", [("compare", "comp"), ("subtract", "sub")])
@pytest.mark.parametrize("powered", ["true", "false"])
def test_comparator_names(mode, suffix, powered):
    name, _ = one(f"comparator[facing=north,mode={mode},powered={powered}]")
    assert name == f"mcl_comparators:comparator_{'on' if powered == 'true' else 'off'}_{suffix}"
    assert name in NODES


def test_comparator_param2():
    got = {f: one(f"comparator[facing={f},mode=compare,powered=false]")[1] for f in FACINGS}
    assert got == {"north": 2, "south": 0, "east": 3, "west": 1}


def test_comparator_output_signal_from_block_entity():
    g = grid_of("comparator[facing=south,mode=compare,powered=true]")
    g.block_entities[(0, 0, 0)] = {"id": "minecraft:comparator", "OutputSignal": 9}
    conv = mapper.map_grid(g)
    assert node_at(conv, (0, 0, 0)) == ("mcl_comparators:comparator_on_comp", 9 * 4 + 0)


def test_torch_rules():
    assert one("redstone_torch[lit=true]") == ("mcl_redstone_torch:redstone_torch_on", 1)
    assert one("redstone_torch[lit=false]") == ("mcl_redstone_torch:redstone_torch_off", 1)
    # wallmounted: 2=+X 3=-X 4=+Z 5=-Z names the direction of the support block.
    got = {f: one(f"redstone_wall_torch[facing={f},lit=true]") for f in FACINGS}
    assert {f: n for f, (n, _) in got.items()} == dict.fromkeys(
        FACINGS, "mcl_redstone_torch:redstone_torch_on_wall")
    assert {f: p for f, (_, p) in got.items()} == {"north": 5, "south": 4, "east": 3, "west": 2}
    assert one("redstone_wall_torch[facing=east,lit=false]")[0] == \
        "mcl_redstone_torch:redstone_torch_off_wall"


def test_button_rules():
    assert one("stone_button[face=floor,facing=north,powered=false]") == \
        ("mcl_buttons:button_stone_off", 1)
    assert one("stone_button[face=ceiling,facing=north,powered=true]") == \
        ("mcl_buttons:button_stone_on", 0)
    got = {f: one(f"oak_button[face=wall,facing={f},powered=false]") for f in FACINGS}
    assert {f: p for f, (_, p) in got.items()} == {"north": 5, "south": 4, "east": 3, "west": 2}
    assert got["north"][0] == "mcl_buttons:button_oak_off"


def test_every_button_material_resolves():
    table = mapper.load_table()
    buttons = [mc for mc, row in table["blocks"].items()
               if isinstance(row, dict) and row["rule"] == "button"]
    assert len(buttons) >= 13
    for mc in buttons:
        for powered in ("true", "false"):
            assert one(f"{mc}[face=wall,facing=east,powered={powered}]")[0] in NODES, mc


def test_simple_redstone_rows():
    assert one("redstone_block")[0] == "mcl_redstone_torch:redstoneblock"
    assert one("target")[0] == "mcl_target:target_off"


def test_known_difference_warnings():
    conv = mapper.map_grid(grid_of("oak_button[face=floor,facing=north,powered=false]",
                                   "birch_button[face=floor,facing=north,powered=false]",
                                   "stone_button[face=floor,facing=north,powered=false]",
                                   "stone"))
    # Buttons behave the same in both games (measured by the parity rig).
    assert conv.report.warnings == []

    conv = mapper.map_grid(grid_of("lectern[facing=north,has_book=true,powered=false]"))
    assert any("lectern" in w.lower() and "text" in w.lower() for w in conv.report.warnings)


def test_warnings_do_not_fail_the_conversion(tmp_path):
    from craftpipe import schem
    from craftpipe.cli import main
    g = grid_of("oak_button[face=floor,facing=north,powered=false]")
    schem.write_schem(g, tmp_path / "b.schem")
    assert main(["convert", str(tmp_path / "b.schem")]) == 0
