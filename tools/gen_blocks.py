"""Regenerate the simple one-to-one rows of src/craftpipe/data/blocks.json.

Rows that need a rule (redstone components, containers) are in
RULE_ROWS below. Run:  python tools/gen_blocks.py
"""

import json
import pathlib

COLOURS = {  # Minecraft colour -> Mineclonia colour
    "white": "white", "orange": "orange", "magenta": "magenta", "light_blue": "light_blue",
    "yellow": "yellow", "lime": "lime", "pink": "pink", "gray": "grey", "light_gray": "silver",
    "cyan": "cyan", "purple": "purple", "blue": "blue", "brown": "brown", "green": "green",
    "red": "red", "black": "black",
}
WOODS = {
    "oak": "oak", "spruce": "spruce", "birch": "birch", "jungle": "jungle", "acacia": "acacia",
    "dark_oak": "dark_oak", "mangrove": "mangrove", "cherry": "cherry_blossom",
    "bamboo": "bamboo", "crimson": "crimson", "warped": "warped", "pale_oak": "pale_oak",
}

blocks = {
    "minecraft:air": "air", "minecraft:cave_air": "air", "minecraft:void_air": "air",
    "minecraft:stone": "mcl_core:stone",
    "minecraft:cobblestone": "mcl_core:cobble",
    "minecraft:smooth_stone": "mcl_core:stone_smooth",
    "minecraft:stone_bricks": "mcl_core:stonebrick",
    "minecraft:cracked_stone_bricks": "mcl_core:stonebrickcracked",
    "minecraft:mossy_stone_bricks": "mcl_core:stonebrickmossy",
    "minecraft:chiseled_stone_bricks": "mcl_core:stonebrickcarved",
    "minecraft:granite": "mcl_core:granite", "minecraft:polished_granite": "mcl_core:granite_smooth",
    "minecraft:diorite": "mcl_core:diorite", "minecraft:polished_diorite": "mcl_core:diorite_smooth",
    "minecraft:andesite": "mcl_core:andesite", "minecraft:polished_andesite": "mcl_core:andesite_smooth",
    "minecraft:deepslate": "mcl_deepslate:deepslate",
    "minecraft:polished_deepslate": "mcl_deepslate:deepslate_polished",
    "minecraft:deepslate_bricks": "mcl_deepslate:deepslate_bricks",
    "minecraft:deepslate_tiles": "mcl_deepslate:deepslate_tiles",
    "minecraft:bricks": "mcl_core:brick_block",
    "minecraft:sandstone": "mcl_core:sandstone", "minecraft:smooth_sandstone": "mcl_core:sandstonesmooth2",
    "minecraft:cut_sandstone": "mcl_core:sandstonesmooth",
    "minecraft:dirt": "mcl_core:dirt", "minecraft:grass_block": "mcl_core:dirt_with_grass",
    "minecraft:obsidian": "mcl_core:obsidian", "minecraft:bedrock": "mcl_core:bedrock",
    "minecraft:iron_block": "mcl_core:ironblock", "minecraft:gold_block": "mcl_core:goldblock",
    "minecraft:diamond_block": "mcl_core:diamondblock", "minecraft:emerald_block": "mcl_core:emeraldblock",
    "minecraft:lapis_block": "mcl_core:lapisblock", "minecraft:coal_block": "mcl_core:coalblock",
    "minecraft:quartz_block": "mcl_nether:quartz_block", "minecraft:smooth_quartz": "mcl_nether:quartz_smooth",
    "minecraft:glowstone": "mcl_nether:glowstone", "minecraft:sea_lantern": "mcl_ocean:sea_lantern",
    "minecraft:glass": "mcl_core:glass", "minecraft:tinted_glass": "mcl_amethyst:tinted_glass",
    "minecraft:terracotta": "mcl_colorblocks:hardened_clay",
    "minecraft:barrier": "mcl_core:barrier",
}
slabs = {  # Minecraft slab -> Mineclonia base slab name
    "smooth_stone": "stone", "stone": "stone_rough", "cobblestone": "cobble",
    "stone_brick": "stonebrick", "sandstone": "sandstone", "quartz": "quartzblock",
    "smooth_quartz": "quartz_smooth", "brick": "brick_block",
    "andesite": "andesite", "polished_andesite": "andesite_smooth",
    "diorite": "diorite", "polished_diorite": "diorite_smooth",
    "granite": "granite", "polished_granite": "granite_smooth",
    "polished_deepslate": "deepslate_polished", "deepslate_brick": "deepslate_bricks",
    "deepslate_tile": "deepslate_tiles",
}
for mc, mcl in COLOURS.items():
    blocks[f"minecraft:{mc}_wool"] = f"mcl_wool:{mcl}"
    blocks[f"minecraft:{mc}_concrete"] = f"mcl_colorblocks:concrete_{mcl}"
    blocks[f"minecraft:{mc}_terracotta"] = f"mcl_colorblocks:hardened_clay_{mcl}"
    blocks[f"minecraft:{mc}_stained_glass"] = f"mcl_core:glass_{mcl}"
for mc, mcl in WOODS.items():
    blocks[f"minecraft:{mc}_planks"] = f"mcl_trees:wood_{mcl}"
    slabs[mc] = mcl
for mc, mcl in slabs.items():
    blocks[f"minecraft:{mc}_slab"] = {"rule": "slab", "base": f"mcl_stairs:slab_{mcl}"}

RULE_ROWS = {
    "minecraft:redstone_wire": {"rule": "dust"},
    "minecraft:redstone_lamp": {"rule": "lamp"},
    "minecraft:lever": {"rule": "lever"},
    "minecraft:repeater": {"rule": "repeater"},
    "minecraft:comparator": {"rule": "comparator"},
    "minecraft:redstone_torch": {"rule": "torch"},
    "minecraft:redstone_wall_torch": {"rule": "wall_torch"},
    "minecraft:redstone_block": "mcl_redstone_torch:redstoneblock",
    "minecraft:target": "mcl_target:target_off",
    "minecraft:stone_button": {"rule": "button", "material": "stone"},
    "minecraft:polished_blackstone_button": {"rule": "button", "material": "polished_blackstone"},
}
RULE_ROWS.update({
    "minecraft:chest": {"rule": "chest", "base": "mcl_chests:chest"},
    "minecraft:trapped_chest": {"rule": "chest", "base": "mcl_chests:trapped_chest"},
    "minecraft:barrel": {"rule": "front_facing", "node": "mcl_barrels:barrel_closed"},
    "minecraft:furnace": {"rule": "front_facing", "node": "mcl_furnaces:furnace"},
    "minecraft:blast_furnace": {"rule": "front_facing", "node": "mcl_blast_furnace:blast_furnace"},
    "minecraft:smoker": {"rule": "front_facing", "node": "mcl_smoker:smoker"},
    "minecraft:hopper": {"rule": "hopper"},
    "minecraft:dropper": {"rule": "dropper", "base": "mcl_dispensers:dropper"},
    "minecraft:dispenser": {"rule": "dropper", "base": "mcl_dispensers:dispenser"},
    "minecraft:lectern": {"rule": "lectern"},
})
for mc, mcl in WOODS.items():
    RULE_ROWS[f"minecraft:{mc}_button"] = {"rule": "button", "material": mcl}
blocks.update(RULE_ROWS)

unsupported = {
    **{f"minecraft:{n}": "pistons are not supported"
       for n in ("piston", "sticky_piston", "piston_head", "moving_piston")},
    "minecraft:observer": "observers are not supported",
    "minecraft:slime_block": "slime and honey contraptions are not supported",
    "minecraft:honey_block": "slime and honey contraptions are not supported",
}

# Blocks that convert cleanly but are known to behave differently in
# Mineclonia. The mapper adds the message to the report once per conversion.
WOODEN_BUTTON = ("wooden buttons stay pressed for 10 redstone ticks in Mineclonia "
                 "(15 in Minecraft Java); timing that depends on the pulse length will differ")
warnings = {f"minecraft:{mc}_button": WOODEN_BUTTON for mc in WOODS}
warnings["minecraft:lectern"] = ("lecterns keep their comparator page signal, but the book's "
                                 "text is not carried over")

path = pathlib.Path(__file__).resolve().parent.parent / "src/craftpipe/data/blocks.json"
existing = json.loads(path.read_text()) if path.exists() else {"blocks": {}, "unsupported": {}}
merged = {**existing.get("blocks", {}), **blocks}
out = {"blocks": dict(sorted(merged.items())),
       "unsupported": dict(sorted({**existing.get("unsupported", {}), **unsupported}.items())),
       "warnings": dict(sorted({**existing.get("warnings", {}), **warnings}.items()))}
path.write_text(json.dumps(out, indent=1) + "\n")
print(len(out["blocks"]), "rows")

# The loader refuses schematics containing any node the converter cannot
# produce, so a hand-made .mts cannot smuggle in e.g. a command block.
from craftpipe import mapper  # noqa: E402  (after blocks.json is written)

mapper.load_table.cache_clear()
mapper.output_vocabulary.cache_clear()
lua = ["-- Generated by tools/gen_blocks.py. Do not edit.",
       "-- Every node name craftpipe can write into an .mts.",
       "return {"]
lua += [f'\t["{name}"] = true,' for name in sorted(mapper.output_vocabulary())]
lua.append("}")
allow = path.parents[3] / "mod/craftpipe_loader/allowed_nodes.lua"
allow.write_text("\n".join(lua) + "\n")
print(len(lua) - 4, "allowed nodes")
