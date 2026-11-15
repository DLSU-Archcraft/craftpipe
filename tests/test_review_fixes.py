"""Regression tests for the whole-branch review findings."""

import hashlib
import json
import pathlib
import subprocess
import sys

import pytest

import craftpipe
from craftpipe import litematic, mapper, nbt, schem
from craftpipe.errors import UnsupportedFormatError
from craftpipe.grid import BlockState, VoxelGrid
from craftpipe.reader import read_schematic

P = BlockState.parse
REPO = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = json.loads((REPO / "tests/data/mineclonia_registry.json").read_text())
CROSS = "redstone_wire[east=side,north=side,power=0,south=side,west=side]"
DOT = "redstone_wire[east=none,north=none,power=0,south=none,west=none]"


# ---- Critical 1: dust keeps the shape Minecraft saved ------------------------

def dust_node(state, data_version=3953):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P(state))
    g.data_version = data_version
    conv = mapper.map_grid(g)
    return conv.names[1]


def test_lone_cross_and_dot_are_different_nodes():
    assert dust_node(CROSS) == "mcl_redstone:wire_0f"
    assert dust_node(DOT) == "mcl_redstone:redstone"


def test_dust_shape_follows_saved_sides_after_mirror():
    # Mineclonia bits: 1 = -Z, 2 = -X, 4 = +Z, 8 = +X. MC north (-Z) becomes +Z.
    assert dust_node("redstone_wire[east=none,north=side,south=side,west=none]") == "mcl_redstone:wire_05"
    assert dust_node("redstone_wire[east=side,north=side,south=none,west=none]") == "mcl_redstone:wire_0c"
    assert dust_node("redstone_wire[east=up,north=none,south=side,west=none]") == "mcl_redstone:wire_09"
    assert dust_node("redstone_wire[east=side,north=none,south=none,west=none]") == "mcl_redstone:wire_0a"


def test_pre_1_16_unconnected_dust_is_a_cross():
    assert dust_node(DOT, data_version=2230) == "mcl_redstone:wire_0f"      # 1.15.2
    assert dust_node("redstone_wire[east=none,north=side,south=side,west=none]",
                     data_version=2230) == "mcl_redstone:wire_05"


def test_warns_when_a_lever_can_reshape_dust_onto_a_lamp():
    # lever - dust - (lamp to the side, not connected in Minecraft)
    g = VoxelGrid((2, 1, 2))
    g.set(0, 0, 0, P("lever[face=floor,facing=north,powered=false]"))
    g.set(1, 0, 0, P("redstone_wire[east=side,north=none,south=none,west=side]"))
    g.set(1, 0, 1, P("redstone_lamp[lit=false]"))
    conv = mapper.map_grid(g)
    (warning,) = conv.report.warnings
    assert "lamp" in warning and "(1, 0, 0)" in warning
    # Same wire pointing at the lamp, or with no lever beside it: nothing to warn about.
    g.set(1, 0, 0, P("redstone_wire[east=side,north=side,south=side,west=side]"))
    assert mapper.map_grid(g).report.warnings == []
    g.set(1, 0, 0, P("redstone_wire[east=side,north=none,south=none,west=side]"))
    g.set(0, 0, 0, P("stone"))
    assert mapper.map_grid(g).report.warnings == []


@pytest.mark.parametrize("writer,ext", [(schem.write_schem, "schem"), (litematic.write_litematic, "litematic")])
def test_readers_keep_data_version(tmp_path, writer, ext):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("stone"))
    writer(g, tmp_path / f"a.{ext}", data_version=2230)
    assert read_schematic(tmp_path / f"a.{ext}").data_version == 2230


# ---- Critical 2 / Important 6: loader vocabulary --------------------------

def test_output_vocabulary_is_registered_and_complete():
    vocab = mapper.output_vocabulary()
    assert "air" in vocab and mapper.PLACEHOLDER in vocab
    assert not {n for n in vocab if n != "air" and n not in REGISTRY["nodes"]}
    for name in ["mcl_redstone:redstone", "mcl_repeaters:repeater_on_locked",
                 "mcl_comparators:comparator_on_sub", "mcl_redstone_torch:redstone_torch_off_wall",
                 "mcl_chests:trapped_chest_left", "mcl_hoppers:hopper_side_disabled",
                 "mcl_dispensers:dropper_down", "mcl_lectern:lectern_with_book",
                 "mcl_stairs:slab_stone_double", "mcl_buttons:button_oak_on", "mcl_lever:lever_on"]:
        assert name in vocab, name
    assert "mcl_commandblock:commandblock_off" not in vocab


def test_loader_allow_list_file_matches_vocabulary():
    text = (REPO / "mod/craftpipe_loader/allowed_nodes.lua").read_text()
    import re
    listed = set(re.findall(r'\["([^"]+)"\] = true', text))
    assert listed == mapper.output_vocabulary()


def test_every_conversion_stays_inside_the_vocabulary():
    table = mapper.load_table()
    vocab = mapper.output_vocabulary()
    for mc in table["blocks"]:
        g = VoxelGrid((1, 1, 1))
        g.set(0, 0, 0, P(mc))
        assert set(mapper.map_grid(g).names) <= vocab, mc


# ---- Important 3: manifest is tied to its .mts -----------------------------

def test_manifest_records_mts_hash(tmp_path):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("stone"))
    schem.write_schem(g, tmp_path / "a.schem")
    craftpipe.convert(tmp_path / "a.schem")
    manifest = json.loads((tmp_path / "a.craftpipe.json").read_text())
    assert manifest["mts_sha1"] == hashlib.sha1((tmp_path / "a.mts").read_bytes()).hexdigest()


# ---- Important 4: stack sizes ----------------------------------------------

def chest(items):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("chest[facing=north,type=single]"))
    g.block_entities[(0, 0, 0)] = {"id": "minecraft:chest", "Items": items}
    return g


@pytest.mark.parametrize("item", ["carrot_on_a_stick", "suspicious_stew", "iron_horse_armor",
                                  "goat_horn", "bundle", "mace", "flower_banner_pattern",
                                  "music_disc_cat", "oak_chest_boat", "axolotl_bucket",
                                  "warped_fungus_on_a_stick", "red_bundle", "wolf_armor"])
def test_unstackable_items_fill_a_slot(item):
    items = [{"Slot": nbt.Byte(i), "id": f"minecraft:{item}", "count": nbt.Int(1)} for i in range(27)]
    (entry,) = mapper.map_grid(chest(items)).manifest["containers"]
    assert entry["signal"] == 15
    assert REGISTRY["items"][entry["lists"]["main"][0]["name"]] == 1


@pytest.mark.parametrize("item,size", [("wind_charge", 64), ("oak_hanging_sign", 16),
                                       ("white_banner", 16), ("honey_bottle", 16),
                                       ("flower_banner_pattern", 1), ("netherite_upgrade_smithing_template", 64)])
def test_stack_size_table(item, size):
    from craftpipe.containers import mc_stack_size
    assert mc_stack_size(f"minecraft:{item}") == size


def test_max_stack_size_component_is_honoured():
    items = [{"Slot": nbt.Byte(0), "id": "minecraft:stick", "count": nbt.Int(16),
              "components": {"minecraft:max_stack_size": nbt.Int(16)}}]
    (entry,) = mapper.map_grid(chest(items)).manifest["containers"]
    assert entry["signal"] == 1 + int(14 * 1 / 27)          # one full slot of 27
    assert REGISTRY["items"][entry["lists"]["main"][0]["name"]] == 16
    assert entry["lists"]["main"][0]["count"] == 16


def test_unknown_item_warning_states_the_assumed_stack_size():
    items = [{"Slot": nbt.Byte(0), "id": "minecraft:some_future_item", "count": nbt.Int(3)}]
    conv = mapper.map_grid(chest(items))
    (warning,) = conv.report.warnings
    assert "minecraft:some_future_item" in warning and "assumed" in warning and "64" in warning
    assert "unchanged" not in warning


# ---- Important 5: pre-1.13 inputs ------------------------------------------

@pytest.mark.parametrize("writer,ext", [(schem.write_schem, "schem"), (litematic.write_litematic, "litematic")])
def test_pre_flattening_data_version_rejected(tmp_path, writer, ext):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("redstone_torch[facing=west]"))
    writer(g, tmp_path / f"old.{ext}", data_version=1343)       # 1.12.2
    with pytest.raises(UnsupportedFormatError, match="1.13"):
        read_schematic(tmp_path / f"old.{ext}")


# ---- Important 7: absurd dimensions ----------------------------------------

def test_huge_schem_rejected_cleanly(tmp_path):
    root = {"Version": nbt.Int(2), "DataVersion": nbt.Int(3953), "Width": nbt.Short(-1),
            "Height": nbt.Short(-1), "Length": nbt.Short(-1),
            "Palette": {"minecraft:air": nbt.Int(0)}, "BlockData": nbt.ByteArray([0])}
    path = tmp_path / "huge.schem"
    path.write_bytes(nbt.dumps(root, name="Schematic"))
    with pytest.raises(UnsupportedFormatError, match="too large"):
        read_schematic(path)
    r = subprocess.run([sys.executable, "-m", "craftpipe", "convert", str(path)],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "Traceback" not in r.stderr


def test_far_apart_litematic_regions_rejected_cleanly(tmp_path):
    a = VoxelGrid((1, 1, 1))
    a.set(0, 0, 0, P("stone"))
    path = tmp_path / "far.litematic"
    litematic.write_litematic([((0, 0, 0), a), ((2_000_000, 0, 2_000_000), a)], path)
    with pytest.raises(UnsupportedFormatError, match="too large"):
        read_schematic(path)


# ---- Output names the loader will accept -----------------------------------

@pytest.mark.parametrize("name,warns", [("my build", True), ("cpu.v2", True), ("cpu_v2-final", False)])
def test_convert_warns_about_names_the_loader_refuses(tmp_path, name, warns):
    g = VoxelGrid((1, 1, 1))
    g.set(0, 0, 0, P("stone"))
    schem.write_schem(g, tmp_path / f"{name}.schem")
    conv = craftpipe.convert(tmp_path / f"{name}.schem")
    assert any("craftpipe_place" in w for w in conv.report.warnings) is warns
