"""Mineclonia -> Minecraft.

The reverse mapping is not a second table. It is derived from the forward
one: every Minecraft state the forward rules understand is run through
them once, and the node it produces is remembered as mapping back to that
state. So the two directions cannot drift apart, and anything the forward
converter could never have produced is reported as unmapped.

Three things need their own handling because the forward direction folds
information away: redstone dust (its shape is in the node name, its power
in param2), comparators (output strength in param2) and a few nodes that
only exist while the game runs (a lit furnace, an open barrel ...).
"""

from __future__ import annotations

import functools
import hashlib
import itertools
import json
import os
import re
import struct
import zlib

from . import containers, mts, nbt, rules
from .errors import CraftpipeError, UnmappedBlocksError
from .grid import AIR, BlockState, VoxelGrid, check_size
from .mapper import MAX_POSITIONS, Report, UnmappedEntry, load_table

DATA_VERSION = 3955                         # Java Edition 1.21.1
PLACEHOLDER = BlockState("minecraft:bedrock")
_WIRE = re.compile(r"mcl_redstone:wire_([0-9a-f]{2})$")
_DOT = "mcl_redstone:redstone"

# Nodes Mineclonia switches to while running. They map to the same block
# as their resting form, with the extra properties given here.
_RUNTIME = {
    "mcl_furnaces:furnace_active": ("mcl_furnaces:furnace", {"lit": "true"}),
    "mcl_blast_furnace:blast_furnace_active": ("mcl_blast_furnace:blast_furnace", {"lit": "true"}),
    "mcl_smoker:smoker_active": ("mcl_smoker:smoker", {"lit": "true"}),
    "mcl_barrels:barrel_open": ("mcl_barrels:barrel_closed", {"open": "true"}),
    "mcl_chests:trapped_chest_on_small": ("mcl_chests:trapped_chest_small", {}),
    "mcl_chests:trapped_chest_on_left": ("mcl_chests:trapped_chest_left", {}),
    "mcl_chests:trapped_chest_on_right": ("mcl_chests:trapped_chest_right", {}),
    "mcl_target:target_on": ("mcl_target:target_off", {}),
}
# Minecraft filler items by stack size, for items with no equivalent.
_FILLER = {64: "minecraft:cobblestone", 16: "minecraft:snowball", 1: "minecraft:wooden_shovel"}


@functools.lru_cache(maxsize=None)
def _lookup() -> dict:
    """(node name, param2) -> BlockState in mirrored space. Where several
    Minecraft states give the same node (a floor lever's facing, say), the
    first in the rule's declared order is used."""
    table = load_table()
    out: dict = {}
    for mc, row in table["blocks"].items():
        if isinstance(row, str):
            if row != "air":
                out.setdefault((row, 0), BlockState(mc))
            continue
        domain = rules.DOMAINS[row["rule"]]
        extra = {k: v for k, v in row.items() if k != "rule"}
        keys = list(domain)
        for values in itertools.product(*(domain[k] for k in keys)):
            state = BlockState(mc, tuple(zip(keys, values)))
            node = rules.RULES[row["rule"]](state, **extra)
            if node is not None and not node.name.startswith("mcl_redstone:"):
                out.setdefault((node.name, node.param2), state)
    return out


@functools.lru_cache(maxsize=None)
def _names() -> frozenset:
    return frozenset(name for name, _ in _lookup())


def _dust_state(flags: int, param2: int) -> BlockState:
    sides = {}
    for side, bit in rules.DUST_BITS.items():
        if flags & bit:
            sides[side] = "up" if (flags >> 4) & bit else "side"
        else:
            sides[side] = "none"
    return BlockState("minecraft:redstone_wire", (("power", str(param2 & 15)), *sides.items()))


def node_to_state(name: str, param2: int) -> BlockState | None:
    """The Minecraft state (in mirrored space) for a Mineclonia node."""
    if name == "air":
        return AIR
    if name == _DOT:
        return _dust_state(0, param2)
    wire = _WIRE.match(name)
    if wire:
        return _dust_state(int(wire.group(1), 16), param2)
    extra = {}
    if name in _RUNTIME:
        name, extra = _RUNTIME[name]
    table = _lookup()
    if name not in _names():
        return None
    candidates = [param2]
    if name.startswith("mcl_comparators:"):
        candidates = [param2 % 4]                   # the rest is output strength
    candidates += [param2 % 128, param2 % 32, param2 % 4, 0]
    for p in candidates:
        state = table.get((name, p))
        if state is not None:
            return state.with_props(**extra) if extra else state
    return None


@functools.lru_cache(maxsize=None)
def _items() -> dict:
    return {mcl: mc for mc, mcl in containers.load_items()["items"].items()}


def _item(stack: dict, where, report: Report) -> dict | None:
    try:
        name, count = str(stack["name"]), int(stack["count"])
    except (KeyError, TypeError, ValueError):
        report.warn(f"container at {where} has an unreadable item entry; skipped")
        return None
    if count <= 0:
        return None
    mc = _items().get(name)
    try:
        size = int(stack.get("max") or (containers.mc_stack_size(mc) if mc else 64))
    except (TypeError, ValueError):
        size = 64
    size = max(1, size)
    count = min(count, size)
    if mc is None or containers.mc_stack_size(mc) != size:
        filler = _FILLER.get(size)
        if filler is None:
            filler, scaled = _FILLER[64], max(1, min(64, round(count * 64 / size)))
            report.warn(f"item {name} (stack size {size}) has no Minecraft equivalent; replaced "
                        f"with {filler} filling the same share of the slot")
            count = scaled
        else:
            report.warn(f"item {name} has no Minecraft equivalent; replaced with {filler}, "
                        f"which has the same stack size ({size})")
        mc = filler
    return {"id": mc, "count": nbt.Int(count)}


def _container_entity(block: str, entry: dict | None, where, report: Report) -> dict:
    slots, lists = containers.LAYOUTS[block]
    items = []
    for list_name, mc_slots in lists.items():
        stacks = (entry or {}).get("lists", {}).get(list_name, [])
        for stack in stacks if isinstance(stacks, list) else []:
            try:
                index = int(stack["slot"]) - 1
            except (KeyError, TypeError, ValueError):
                continue
            if not 0 <= index < len(mc_slots):
                report.warn(f"{block} at {where}: an item in slot {index + 1} of '{list_name}' "
                            "does not fit and was dropped")
                continue
            item = _item(stack, where, report)
            if item:
                items.append({"Slot": nbt.Byte(mc_slots[index]), **item})
    items.sort(key=lambda i: int(i["Slot"]))
    return {"id": block, "Items": items}


def _lectern_entity(fields: dict) -> dict:
    try:
        pages = max(1, min(1000, int(fields.get("pages", 1))))
        page = max(1, min(pages, int(fields.get("page", 1))))
    except (TypeError, ValueError):
        pages = page = 1
    return {
        "id": "minecraft:lectern", "Page": nbt.Int(page - 1),
        "Book": {"id": "minecraft:written_book", "count": nbt.Int(1), "components": {
            "minecraft:written_book_content": {
                "title": {"raw": "Book"}, "author": "craftpipe",
                "pages": [{"raw": '""'} for _ in range(pages)]}}},
    }


def to_grid(size, names, node_ids, param2, manifest: dict | None, *,
            allow_unmapped: bool = False) -> tuple[VoxelGrid, Report]:
    """Build the Minecraft VoxelGrid for a Mineclonia schematic."""
    check_size(size)
    sx, sy, sz = size
    report = Report()
    mirrored = VoxelGrid(size)          # Luanti positions, states as the forward rules see them
    mirrored.data_version = DATA_VERSION
    cache: dict = {}
    comparators = []
    for z in range(sz):
        for y in range(sy):
            base = mts.index(size, 0, y, z)
            for x in range(sx):
                node_id, p2 = node_ids[base + x], param2[base + x]
                if node_id == 0 and names[0] == "air":
                    continue
                key = (node_id, p2)
                state = cache.get(key, False)
                if state is False:
                    state = cache[key] = node_to_state(names[node_id], p2)
                if state is None:
                    entry = report.unmapped.setdefault(names[node_id], UnmappedEntry())
                    entry.count += 1
                    if len(entry.positions) < MAX_POSITIONS:
                        entry.positions.append((x, y, z))
                    state = PLACEHOLDER
                if state == AIR:
                    continue
                mirrored.set(x, y, z, state)
                if state.name == "minecraft:comparator":
                    comparators.append(((x, y, z), p2 >> 2))
    for entry in report.unmapped.values():
        entry.positions.sort()
    if report.unmapped and not allow_unmapped:
        raise UnmappedBlocksError(report)

    if manifest is None:
        has_containers = any(s.name in containers.LAYOUTS for s in mirrored.counts())
        if has_containers:
            report.warn("no .craftpipe.json manifest was found next to the .mts, so containers "
                        "are empty; export with /craftpipe_export to keep their contents")
        manifest = {}

    def at(entry):
        try:
            pos = tuple(int(v) for v in entry["pos"])
            mirrored._index(*pos)
            return pos
        except (KeyError, TypeError, ValueError, IndexError):
            return None

    by_pos = {}
    for entry in manifest.get("containers") or []:
        if isinstance(entry, dict) and at(entry) is not None:
            by_pos[at(entry)] = entry
    for pos, state in list(mirrored.cells()):
        if state.name in containers.LAYOUTS:
            mirrored.block_entities[pos] = _container_entity(state.name, by_pos.get(pos), pos, report)
    for entry in manifest.get("meta") or []:
        pos = at(entry) if isinstance(entry, dict) else None
        if pos is not None and mirrored.get(*pos).name == "minecraft:lectern" \
                and mirrored.get(*pos).get("has_book") == "true":
            fields = entry.get("fields")
            mirrored.block_entities[pos] = _lectern_entity(fields if isinstance(fields, dict) else {})
    for pos, signal in comparators:
        mirrored.block_entities[pos] = {"id": "minecraft:comparator",
                                        "OutputSignal": nbt.Int(max(0, min(15, signal)))}
    grid = mirrored.mirror_z()
    for state, count in grid.counts().items():
        if state != AIR:
            report.counts[state.name] = report.counts.get(state.name, 0) + count
    return grid, report


def read_export(mts_path) -> tuple[tuple, list, list, list, dict | None]:
    """Read an .mts and the manifest beside it (None when there is none)."""
    label = os.path.basename(os.fspath(mts_path))
    try:
        size, names, node_ids, param2 = mts.read_mts(mts_path)
    except (OSError, struct.error, zlib.error, IndexError, UnicodeDecodeError, ValueError) as exc:
        raise CraftpipeError(f"{label}: not a readable .mts schematic ({exc.__class__.__name__})") from None
    except CraftpipeError as exc:
        raise CraftpipeError(f"{label}: {exc}") from None
    manifest_path = os.path.splitext(os.fspath(mts_path))[0] + ".craftpipe.json"
    manifest = None
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        except (OSError, ValueError) as exc:
            raise CraftpipeError(f"{os.path.basename(manifest_path)}: not readable JSON ({exc})") from None
        if not isinstance(manifest, dict):
            raise CraftpipeError(f"{os.path.basename(manifest_path)}: not a craftpipe manifest")
        recorded = manifest.get("mts_sha1")
        with open(mts_path, "rb") as fh:
            actual = hashlib.sha1(fh.read()).hexdigest()
        if recorded is not None and recorded != actual:
            raise CraftpipeError(
                f"{os.path.basename(manifest_path)} does not belong to {label}; use the .mts and "
                "the .craftpipe.json from the same export")
    return size, names, node_ids, param2, manifest
