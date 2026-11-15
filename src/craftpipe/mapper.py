"""Turn a Minecraft VoxelGrid into Mineclonia node names and param2."""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass, field
from importlib import resources

from . import __version__, containers, mts, rules
from .errors import UnmappedBlocksError
from .grid import BlockState, Pos, VoxelGrid

PLACEHOLDER = "mcl_core:bedrock"
MAX_POSITIONS = 5
MANIFEST_FORMAT = 1


@functools.lru_cache(maxsize=None)
def load_table() -> dict:
    text = resources.files("craftpipe").joinpath("data/blocks.json").read_text(encoding="utf-8")
    return json.loads(text)


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

    for (x, y, z), state in mirrored.cells():
        hit = cache.get(state)
        if hit is None:
            hit = cache[state] = map_state(state)
        node, reason = hit
        if node is None:
            # Report the state as it appears in the source file.
            from .grid import mirror_state
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
