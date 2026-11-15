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
