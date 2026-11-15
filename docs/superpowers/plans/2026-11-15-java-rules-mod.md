# craftpipe_java_rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Luanti mod that makes Mineclonia's redstone follow Java in the four ways the spec lists, proven by the parity rig.

**Architecture:** `mod/craftpipe_java_rules/init.lua` overrides node definitions at load time. The Luanti test harness can load it; parity tests run in `stock` and `java` modes and in a `native` (game-shaped dust) variant.

**Tech Stack:** Lua (Luanti mod API, Mineclonia 35899), existing Python test harness and parity rig.

**Spec:** `docs/superpowers/specs/2026-11-15-java-rules-mod-design.md`

## Global Constraints

- The mod only overrides; it never edits Mineclonia's files.
- It fails at load with a clear error if a function it wraps is missing.
- Stock-mode tests and `known_differences.json` semantics stay as they are; each entry gains `"with_java_rules": "fixed" | "remains"`.
- A difference the mod is meant to fix must be absent in java mode (tests fail if it still occurs).
- Branch `feat/java-rules-mod`; commit per task.

## Review Focus

1. The cross default turning a player-made dot back into a cross (after a neighbour changes).
2. A converted build's explicit dots surviving load with the mod active.
3. Dust beside a repeater's side (Java: no connection) and an observer.
4. Comparator with a container directly behind it (no block between) while that container is itself powered: must still read the container.
5. The mod loaded in a world without `craftpipe_loader`, and the loader without the mod.

---

### Task 1: Harness modes

**Files:** Modify `tests/harness/luanti.py`, `tests/engine/craftpipe_test/init.lua`, `tests/conftest.py`, `tests/parity/differences.py`, `tests/parity/known_differences.json`, `tests/test_differences_file.py`.

**Interfaces — Produces:**
- `Engine(tmp_path, mods=())`: extra mod directory names under `mod/` copied into the world. Fixtures `module_engine_java` (module scope, `mods=("craftpipe_java_rules",)`).
- `Engine.run(..., native=False)`: with `native=True` the driver, after placing, calls `on_construct` on every dust node in the schematic area so the game shapes it.
- Reads gain `"wire_mask"` (low nibble of the dust shape, or None) in raw results.
- `differences.check(..., mode="stock")`: in `mode="java"`, entries with `with_java_rules == "fixed"` are ignored (so the readings must be equal).

- [ ] Failing unit tests: every entry has `with_java_rules` in the allowed set; `check(mode="java")` with a `fixed` entry raises when the difference still occurs and passes when readings are equal; a `remains` entry behaves as in stock.
- [ ] Implement; mark `input-latency` `remains`, the other three `fixed`.
- [ ] `pytest -q --ignore=tests/engine --ignore=tests/parity` green; commit.

### Task 2: The mod, test-first against the rig

**Files:** Create `mod/craftpipe_java_rules/mod.conf`, `init.lua`, `tests/parity/test_java_rules.py`. Modify `mod/craftpipe_loader/init.lua` (mark saved dots with metadata `java_dot = "1"`).

- [ ] **Failing tests** (`test_java_rules.py`, Mineclonia with the mod vs real Minecraft):
  - `test_timing_matches_minecraft`: timing suite, pinned; `differences.check(mode="java")` for finals, waveforms and latency.
  - `test_existing_suites_match_minecraft[pinned|native]`: orientation, logic, comparator, rom, adder_fast.
  - `test_timing_native_matches_minecraft`.
  - `test_native_dust_shapes_equal_minecraft`: for every dust in every suite, `wire_mask` after native shaping equals `rules.dust_mask` of the saved Minecraft state (mirrored).
  - `test_player_made_dot_stays_a_dot`: lone dot beside a lamp; after a neighbouring block is placed and removed (driver step `"poke": pos`), still a dot and the lamp stays dark.
  - `test_stock_mineclonia_still_differs_natively`: the same native shape test without the mod finds mismatches (guards against the test being vacuous).
- [ ] Implement the four changes; iterate to green. Any remaining mismatch is triaged as in the rig plan.
- [ ] Commit.

### Task 3: Docs

- [ ] README: a section on the mod (what it changes, install, that the study's Luanti worlds should load it), the differences list showing which entries the mod removes (renderer prints "Removed by `craftpipe_java_rules`."), converter warning text mentioning the mod.
- [ ] Full suite and slow suite green; commit.
