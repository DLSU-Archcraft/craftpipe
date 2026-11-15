"""Turn a Minecraft VoxelGrid into Mineclonia node names and param2."""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from importlib import resources

from . import __version__, containers, mts, rules
from .errors import UnmappedBlocksError
from .grid import CROSS_DUST_DATA_VERSION, BlockState, Pos, VoxelGrid, mirror_state

PLACEHOLDER = "mcl_core:bedrock"
MAX_POSITIONS = 5
MANIFEST_FORMAT = 1


@functools.lru_cache(maxsize=None)
def load_table() -> dict:
    text = resources.files("craftpipe").joinpath("data/blocks.json").read_text(encoding="utf-8")
    return json.loads(text)


@functools.lru_cache(maxsize=None)
def output_vocabulary() -> frozenset:
    """Every node name a conversion can put in an .mts. The loader refuses
    schematics that contain anything else."""
    table = load_table()
    names = {"air", PLACEHOLDER}
    for row in table["blocks"].values():
        if isinstance(row, str):
            names.add(row)
        else:
            extra = {k: v for k, v in row.items() if k != "rule"}
            names |= rules.possible_nodes(row["rule"], **extra)
    return frozenset(names)


_DUST = "minecraft:redstone_wire"
_ALL_SIDES = (("east", "side"), ("north", "side"), ("south", "side"), ("west", "side"))
# Dust connects to these in Mineclonia but not in Java ...
_MINECLONIA_ONLY_CONNECTS = ("mcl_redstone_lamp:", "mcl_dispensers:")
# ... and these re-run Mineclonia's dust-shape code on their neighbours
# every time they are used.
_RESHAPES_NEIGHBOURS = ("mcl_lever:", "mcl_buttons:")
_SIDES = {"north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}


def _legacy_dust(state: BlockState) -> BlockState:
    """Before Java 1.16 an unconnected dust was saved with no sides but
    behaved as a cross."""
    if all(state.get(k, "none") == "none" for k in ("north", "east", "south", "west")):
        return state.with_props(**dict(_ALL_SIDES))
    return state


@dataclass
class UnmappedEntry:
    count: int = 0
    positions: list[Pos] = field(default_factory=list)
    reason: str | None = None


@dataclass
class Report:
    unmapped: dict[str, UnmappedEntry] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def to_json(self) -> dict:
        return {
            "unmapped": {
                state: {"count": e.count, "positions": [list(p) for p in e.positions],
                        "reason": e.reason}
                for state, e in self.unmapped.items()
            },
            "warnings": list(self.warnings),
            "counts": dict(sorted(self.counts.items())),
        }


@dataclass
class Conversion:
    size: Pos
    names: list[str]
    node_ids: list[int]
    param2: list[int]
    manifest: dict
    report: Report

    def to_luanti(self, pos) -> Pos:
        """Source (Minecraft) position -> position inside the .mts."""
        x, y, z = pos
        return (x, y, self.size[2] - 1 - z)


def map_state(state: BlockState):
    """Returns (Node, None) on success or (None, reason-or-None) when unmapped.

    ``state`` must already be mirrored.
    """
    table = load_table()
    reason = table["unsupported"].get(state.name)
    if reason is not None:
        return None, reason
    row = table["blocks"].get(state.name)
    if row is None:
        return None, None
    if isinstance(row, str):
        return rules.Node(row, 0), None
    extra = {k: v for k, v in row.items() if k != "rule"}
    node = rules.RULES[row["rule"]](state, **extra)
    if node is None:
        return None, f"no Mineclonia equivalent for this state of {state.name}"
    return node, None


def _warn_about_unstable_dust(dust_cells, size, names, node_ids, report: Report) -> None:
    """Dust keeps the shape Minecraft saved, except that using a lever or
    button makes Mineclonia re-shape the dust beside it by its own rules.
    That only changes behaviour when the same dust also touches a lamp,
    dropper or dispenser it was not connected to."""
    sx, sy, sz = size
    affected = []
    for (x, y, z), state in dust_cells:
        beside = {}
        for side, (dx, dz) in _SIDES.items():
            nx, nz = x + dx, z + dz
            if 0 <= nx < sx and 0 <= nz < sz:
                beside[side] = names[node_ids[mts.index(size, nx, y, nz)]]
        if not any(n.startswith(_RESHAPES_NEIGHBOURS) for n in beside.values()):
            continue
        mask = rules.dust_mask(state)
        if any(n.startswith(_MINECLONIA_ONLY_CONNECTS) and not mask & rules.DUST_BITS[side]
               for side, n in beside.items()):
            affected.append((x, y, sz - 1 - z))
    if affected:
        where = ", ".join(str(p) for p in sorted(affected)[:MAX_POSITIONS])
        report.warn(
            f"{len(affected)} redstone dust next to a lever or button also touch a lamp, dropper "
            "or dispenser they are not connected to. In Mineclonia they will connect to it once "
            f"the lever or button is used, and power it. Source positions: {where}"
            + (" ..." if len(affected) > MAX_POSITIONS else ""))


def map_grid(grid: VoxelGrid, *, allow_unmapped: bool = False, source: str = "") -> Conversion:
    mirrored = grid.mirror_z()
    sx, sy, sz = size = mirrored.size
    report = Report()
    names = ["air"]
    name_ids = {"air": 0}
    volume = sx * sy * sz
    node_ids = [0] * volume
    param2 = [0] * volume
    cache: dict[BlockState, tuple] = {}
    known_differences = load_table().get("warnings", {})
    substituted: dict[str, int] = {}

    legacy_dust = (mirrored.data_version is not None
                   and mirrored.data_version < CROSS_DUST_DATA_VERSION)
    dust_cells = []
    for (x, y, z), state in mirrored.cells():
        if state.name == _DUST:
            if legacy_dust:
                state = _legacy_dust(state)
            dust_cells.append(((x, y, z), state))
        hit = cache.get(state)
        if hit is None:
            hit = cache[state] = map_state(state)
        node, reason = hit
        if node is None:
            # Report the state as it appears in the source file.
            key = str(mirror_state(state))
            entry = report.unmapped.setdefault(key, UnmappedEntry(reason=reason))
            entry.count += 1
            if len(entry.positions) < MAX_POSITIONS:
                entry.positions.append((x, y, sz - 1 - z))
            substituted[key] = substituted.get(key, 0) + 1
            node = rules.Node(PLACEHOLDER, 0)
        if node.name == "air":
            continue
        note = known_differences.get(state.name)
        if note:
            report.warn(note)
        idx = name_ids.get(node.name)
        if idx is None:
            idx = name_ids[node.name] = len(names)
            names.append(node.name)
        i = mts.index(size, x, y, z)
        node_ids[i] = idx
        param2[i] = node.param2 & 0xFF
        report.counts[node.name] = report.counts.get(node.name, 0) + 1

    # Comparators keep their output strength in the block entity; Mineclonia
    # keeps it in the upper bits of param2.
    for (x, y, z), entity in mirrored.block_entities.items():
        i = mts.index(size, x, y, z)
        if names[node_ids[i]].startswith("mcl_comparators:comparator_"):
            try:
                signal = max(0, min(15, int(entity.get("OutputSignal", 0))))
            except (TypeError, ValueError):
                signal = 0
            param2[i] = signal * 4 + param2[i] % 4

    _warn_about_unstable_dust(dust_cells, size, names, node_ids, report)

    for entry in report.unmapped.values():
        entry.positions.sort()
    if report.unmapped and not allow_unmapped:
        report.counts.pop(PLACEHOLDER, None)
        raise UnmappedBlocksError(report)

    manifest = {
        "format": MANIFEST_FORMAT,
        "source": source,
        "converter": __version__,
        "size": [sx, sy, sz],
        "complete": not substituted,
        "substituted": dict(sorted(substituted.items())),
        "containers": containers.extract(
            mirrored, lambda pos: names[node_ids[mts.index(size, *pos)]], report),
        "meta": containers.lectern_meta(mirrored),
    }
    return Conversion(size, names, node_ids, param2, manifest, report)
