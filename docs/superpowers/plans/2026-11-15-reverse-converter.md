# Reverse Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert a Mineclonia region (exported as `.mts` + manifest) into a Minecraft 1.21.1 schematic that behaves the same.

**Architecture:** `src/craftpipe/reverse.py` builds a reverse lookup by enumerating the forward rules, reads `.mts` + manifest into a `VoxelGrid`, and writes it with the existing `.schem`/`.litematic` writers. `craftpipe_loader` gains an export command. The parity rig checks round trips in both real engines.

**Tech Stack:** as the rest of the repository.

**Spec:** `docs/superpowers/specs/2026-11-15-reverse-converter-design.md`

## Global Constraints

- Never drop a node silently; unmapped nodes fail the conversion unless `--allow-unmapped`.
- The reverse mapping is derived from `blocks.json` and `rules.py`; no second hand-written table of block names. Explicit exceptions (canonical choices, run-time-only nodes) live in one small, commented place.
- Export is privilege `server`, names match `^[%w_%-]+$`, files go to `<world>/schems/`.
- Output data version 3955. Branch `feat/reverse-converter`; commit per task.

## Review Focus

1. Two Minecraft states mapping to one Mineclonia node: the reverse must pick the same one every time, and a sensible one.
2. Nodes Mineclonia creates at run time that the forward converter never emits (wire shapes with climbing bits, lit furnace, open barrel, powered trapped chest, dispenser "triggered" param2 bit).
3. Dust "up" connections and dots surviving the trip.
4. Double chests after the Z mirror, in the reverse direction.
5. Export of a large or unloaded region; a hostile name.
6. Items with no Minecraft equivalent, and item counts above the stack size.

---

### Task 1: Reverse mapping and `to_minecraft`

**Files:** Create `src/craftpipe/reverse.py`, `tests/test_reverse.py`. Modify `src/craftpipe/__init__.py`, `src/craftpipe/cli.py`, `tests/test_cli.py`.

**Interfaces — Produces:**
- `reverse.node_to_state(name: str, param2: int) -> BlockState | None` (state in mirrored space, as the forward rules receive it).
- `reverse.to_grid(size, names, node_ids, param2, manifest: dict | None, *, allow_unmapped=False) -> tuple[VoxelGrid, Report]` raising `UnmappedBlocksError`.
- `craftpipe.to_minecraft(mts_path, output_path=None, *, allow_unmapped=False) -> Report`; output defaults to the `.mts` path with `.litematic`.
- CLI `craftpipe to-minecraft INPUT.mts [-o OUT] [--allow-unmapped] [--report FILE]`, same exit codes as `convert`.

- [ ] Failing tests: forward→reverse→forward identity for every suite circuit and for every block in `blocks.json` over its rule domain; dust sides, power and dots; climbing bits become `up`; comparator `OutputSignal`; double chest halves; container items and furnace slots; lectern pages; unknown node fails with name/count/position; unknown item becomes a same-stack-size filler with a warning; run-time-only nodes; missing manifest warns; CLI exit codes and output formats.
- [ ] Implement; `pytest -q --ignore=tests/engine --ignore=tests/parity` green; commit.

### Task 2: Export command and engine round trip

**Files:** Modify `mod/craftpipe_loader/init.lua`, `tests/engine/craftpipe_test/init.lua`, `tests/harness/luanti.py`, `tests/circuits.py`. Create `tests/engine/test_export.py`, `tests/parity/test_round_trip.py`.

- [ ] Failing tests: export writes both files and the manifest hash matches; containers and lectern pages are in the manifest; hostile name and oversized region refused; exported then re-converted suites (Mineclonia with the Java-rules mod) run in real Minecraft exactly like the originals (finals for all suites; waveforms for timing).
- [ ] Implement; iterate to green; commit.

### Task 3: Docs

- [ ] README: exporting, converting back, what carries over, limits. Full suite green; commit.
