"""Container contents and lectern pages for the manifest.

.mts cannot carry inventories, and comparator-based ROM is nothing but
inventories. What matters for the circuit is the comparator signal, which
depends only on how full each slot is, so an item with no Mineclonia
equivalent is replaced by a filler item of the same maximum stack size.
"""

from __future__ import annotations

import fnmatch
import functools
import json
from importlib import resources

from .grid import BlockState, Pos, VoxelGrid
from .signal import container_signal, lectern_signal

# Minecraft block -> (slot count, {mineclonia list: [minecraft slot numbers]})
_MAIN27 = (27, {"main": list(range(27))})
_FURNACE = (3, {"src": [0], "fuel": [1], "dst": [2]})
LAYOUTS = {
    "minecraft:chest": _MAIN27,
    "minecraft:trapped_chest": _MAIN27,
    "minecraft:barrel": _MAIN27,
    "minecraft:hopper": (5, {"main": list(range(5))}),
    "minecraft:dropper": (9, {"main": list(range(9))}),
    "minecraft:dispenser": (9, {"main": list(range(9))}),
    "minecraft:furnace": _FURNACE,
    "minecraft:blast_furnace": _FURNACE,
    "minecraft:smoker": _FURNACE,
}
_DIR = {"north": (0, 0, -1), "south": (0, 0, 1), "east": (1, 0, 0), "west": (-1, 0, 0)}
_CLOCKWISE = {"north": "east", "east": "south", "south": "west", "west": "north"}
_COUNTER = {v: k for k, v in _CLOCKWISE.items()}


@functools.lru_cache(maxsize=None)
def load_items() -> dict:
    text = resources.files("craftpipe").joinpath("data/items.json").read_text(encoding="utf-8")
    return json.loads(text)


@functools.lru_cache(maxsize=None)
def mc_stack_size(item: str) -> int:
    sizes = load_items()["stack_size"]
    if item in sizes:
        return sizes[item]
    for pattern, size in sizes.items():
        if "*" in pattern and fnmatch.fnmatchcase(item, pattern):
            return size
    return 64


def _to_mineclonia(item: str, report) -> str:
    table = load_items()
    mapped = table["items"].get(item)
    if mapped is not None:
        return mapped
    filler = table["filler"][str(mc_stack_size(item))]
    if report is not None:
        report.warn(f"item {item} has no Mineclonia equivalent; replaced with {filler} "
                    "(same stack size, so comparator signals are unchanged)")
    return filler


def _stacks(entity: dict, where: Pos, report):
    """Valid (slot, item id, count) triples from a block entity."""
    out = []
    items = entity.get("Items", [])
    for raw in items if isinstance(items, list) else []:
        try:
            slot = int(raw["Slot"])
            name = str(raw["id"])
            count = int(raw.get("count", raw.get("Count", 1)))
        except (KeyError, TypeError, ValueError, AttributeError):
            if report is not None:
                report.warn(f"container at {where} has an unreadable item entry; skipped")
            continue
        if count > 0:
            out.append((slot, name if ":" in name else "minecraft:" + name, count))
    return out


def double_chest_partner(pos: Pos, state: BlockState) -> Pos | None:
    """Position of the other half, for a (mirrored) chest state."""
    kind, facing = state.get("type", "single"), state.get("facing")
    if kind not in ("left", "right") or facing not in _DIR:
        return None
    side = _CLOCKWISE[facing] if kind == "left" else _COUNTER[facing]
    dx, dy, dz = _DIR[side]
    return (pos[0] + dx, pos[1] + dy, pos[2] + dz)


def extract(grid: VoxelGrid, node_at, report=None) -> list[dict]:
    """Manifest entries for every container in an already mirrored grid.

    ``node_at(pos)`` returns the Mineclonia node name placed there.
    """
    found = {}
    for pos, state in grid.cells():
        layout = LAYOUTS.get(state.name)
        if layout is None:
            continue
        slots, lists = layout
        entity = grid.block_entities.get(pos, {})
        by_slot = {}
        dropped = 0
        for slot, item, count in _stacks(entity, pos, report):
            if 0 <= slot < slots:
                by_slot[slot] = (item, min(count, mc_stack_size(item)))
            else:
                dropped += 1
        if dropped and report is not None:
            report.warn(f"{state.name} at {pos}: {dropped} item(s) in a slot outside the "
                        f"container's {slots} slots were dropped")
        out_lists = {}
        for list_name, mc_slots in lists.items():
            out_lists[list_name] = [
                {"slot": i + 1, "name": _to_mineclonia(by_slot[s][0], report), "count": by_slot[s][1]}
                for i, s in enumerate(mc_slots) if s in by_slot
            ]
        measure = [(count, mc_stack_size(item)) for item, count in by_slot.values()]
        found[pos] = (state, slots, measure, {
            "pos": list(pos), "node": node_at(pos),
            "sizes": {name: len(mc_slots) for name, mc_slots in lists.items()},
            "lists": out_lists, "signal": 0})

    for pos, (state, slots, measure, entry) in found.items():
        partner = double_chest_partner(pos, state) if state.name.endswith("chest") else None
        if partner in found and found[partner][0].name == state.name:
            entry["signal"] = container_signal(slots * 2, measure + found[partner][2])
        else:
            entry["signal"] = container_signal(slots, measure)
    return [entry for _, _, _, entry in found.values()]


def _page_count(book) -> int:
    if not isinstance(book, dict):
        return 1
    holders = []
    components = book.get("components")
    if isinstance(components, dict):
        holders += [components.get("minecraft:written_book_content"),
                    components.get("minecraft:writable_book_content")]
    holders.append(book.get("tag"))
    for holder in holders:
        if isinstance(holder, dict) and isinstance(holder.get("pages"), list):
            return max(1, len(holder["pages"]))
    return 1


def lectern_meta(grid: VoxelGrid) -> list[dict]:
    """Metadata that makes Mineclonia's lectern give the same page signal."""
    out = []
    for pos, entity in grid.block_entities.items():
        state = grid.get(*pos)
        if state.name != "minecraft:lectern" or state.get("has_book") != "true":
            continue
        pages = _page_count(entity.get("Book"))
        try:
            page = int(entity.get("Page", 0)) + 1
        except (TypeError, ValueError):
            page = 1
        page = max(1, min(pages, page))
        out.append({"pos": list(pos), "fields": {"pages": str(pages), "page": str(page)},
                    "signal": lectern_signal(page, pages)})
    return out
