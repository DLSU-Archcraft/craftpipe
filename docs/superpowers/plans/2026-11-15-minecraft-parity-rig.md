# Minecraft Parity Rig Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the same generated circuits in a real headless Minecraft 1.21.1 server and in Mineclonia, compare them output by output and tick by tick, and keep every difference in one enforced data file.

**Architecture:** A second test backend (`MinecraftServer`) with the same `run(circuit, steps)` call as the existing Luanti `Engine`. Circuits and their step scripts move into shared "suites" so engine tests and parity tests use the same definitions. Parity tests compare neutral readings from both backends and consult `tests/parity/known_differences.json`.

**Tech Stack:** Python 3.10+ standard library, pytest, Java 21, the official Minecraft 1.21.1 server jar (downloaded, never committed), RCON, existing Luanti/Mineclonia harness.

**Spec:** `docs/superpowers/specs/2026-11-15-minecraft-parity-rig-design.md`

## Global Constraints

- Unmodified Mojang server only. No mods, no client, no account.
- The jar lives at `~/.cache/craftpipe/minecraft/1.21.1/server.jar` (override with env `CRAFTPIPE_MINECRAFT_DIR`), SHA-1 checked against Mojang's version metadata. Nothing from Mojang is committed.
- `eula=true` is written only when the marker `eula-accepted` exists beside the jar; the marker is created only by `tools/fetch_minecraft_server.py --accept-eula`. On this machine the user has accepted; run the tool with the flag.
- Missing jar, marker or Java 21 → skip with a message naming the missing piece and the fix command. Never fail for that.
- Server: temp directory, 127.0.0.1, free ports, offline mode, void flat world, `/tick freeze`.
- Public interface is in redstone ticks; Minecraft steps 2 game ticks per redstone tick.
- Comparison is engine against engine. No expectation shared by both sides stands in for a comparison.
- Only game differences go in `known_differences.json`. A difference caused by craftpipe's converter or loader is fixed with a failing test first; if too large, it is reported to the user as a craftpipe bug.
- Never edit a circuit to make the engines agree. A new circuit may be added to isolate a difference.
- Work on branch `feat/minecraft-rig`; commit at the end of every task.

## Review Focus

1. **Harness artefacts recorded as game differences.** Each recorded difference needs a reason that holds for a player, not only for commands (the lever mounting-block notification is the known trap).
2. **Server left running** after a failed test or Ctrl-C: the process must be killed and the ports freed. Test in Task 2.
3. **Jar present but corrupt or wrong version:** the SHA-1 check must catch it and the message must say to re-run the fetch tool. Test in Task 1.
4. **A recorded difference that stops occurring** (e.g. after a Mineclonia update) must fail, not silently pass. Test in Task 3.
5. **Someone without the EULA marker** must get a skip that tells them the exact command, and the harness must not write `eula=true`. Test in Task 1 and Task 2.
6. **Structure placement leaving redstone uninitialised** (torches lit beside unpowered dust): the settle period must be long enough that the first read is stable. Test in Task 2.

## File Structure

```
tools/fetch_minecraft_server.py     download + verify + EULA marker
tools/render_differences.py         known_differences.json -> README section
tests/conftest.py                   fixtures for both backends (session/module scoped)
tests/harness/__init__.py
tests/harness/luanti.py             Engine (moved from tests/engine/conftest.py)
tests/harness/minecraft.py          Rcon, MinecraftServer, structure writer
tests/harness/readings.py           Reading, luanti_reading()
tests/suites.py                     Suite definitions shared by engine and parity tests
tests/parity/known_differences.json
tests/parity/differences.py         load + match recorded differences
tests/parity/test_minecraft_rig.py  the rig itself
tests/parity/test_parity.py         existing suites on both backends
tests/parity/test_timing.py         traces and difference-hunting circuits
tests/test_fetch_tool.py, tests/test_differences_file.py
```

---

### Task 1: Fetch tool and harness move

**Files:** Create `tools/fetch_minecraft_server.py`, `tests/test_fetch_tool.py`, `tests/harness/__init__.py`, `tests/harness/luanti.py`, `tests/harness/readings.py`, `tests/conftest.py`, `tests/test_readings.py`. Modify `tests/engine/conftest.py` (reduced to nothing or removed), `tests/engine/craftpipe_test/init.lua` (no change yet).

**Interfaces — Produces:**
- `tools/fetch_minecraft_server.py`: importable functions `cache_dir() -> Path` (env `CRAFTPIPE_MINECRAFT_DIR` or `~/.cache/craftpipe/minecraft/1.21.1`), `expected_sha1(fetch=urllib) -> str`, `verify(jar: Path, sha1: str) -> bool`, `status() -> tuple[bool, str]` (ready?, message naming what is missing and the command to run), `main(argv)`. CLI: no flag downloads and verifies; `--accept-eula` also writes the marker `eula-accepted` containing the date and the EULA URL `https://aka.ms/MinecraftEULA`. The version's server SHA-1 is stored next to the jar as `server.jar.sha1` at download time so later checks work offline.
- `VERSION = "1.21.1"`, manifest URL `https://piston-meta.mojang.com/mc/game/version_manifest_v2.json`.
- `tests/harness/luanti.py`: `Engine` exactly as today (methods `prepare`, `run_raw`, `run`), plus `require_luanti()` raising `pytest.skip`.
- `tests/harness/readings.py`: `Reading = NamedTuple(on: bool, power: int | None)`; `luanti_reading(raw: dict) -> Reading` where dust (`mcl_redstone:redstone`, `mcl_redstone:wire_*`) gives `power = param2 & 15`, `on = power > 0`; comparators give `power = param2 >> 2`, `on = name contains "_on_"`; everything else `power = None`, `on = raw["on"]`.
- `tests/conftest.py`: fixtures `engine` (function), `module_engine` (module), unchanged behaviour.

- [ ] **Step 1: Failing tests** `tests/test_fetch_tool.py` (no network: pass a fake fetch):
  - `test_status_reports_missing_jar`: empty dir via env → `(False, msg)` and msg contains `tools/fetch_minecraft_server.py`.
  - `test_status_reports_missing_eula`: jar + sha1 present, no marker → `(False, msg)` with `--accept-eula` in msg.
  - `test_corrupt_jar_is_rejected`: jar bytes not matching `server.jar.sha1` → `(False, msg)` mentioning re-running the tool.
  - `test_ready_when_all_present` → `(True, ...)`.
  - `test_accept_eula_writes_marker_only_with_flag`: `main([])` with fake fetch writes jar but no marker; `main(["--accept-eula"])` writes it.
- [ ] **Step 2:** `tests/test_readings.py`: dust param2 `0x77` → `Reading(True, 7)`; `mcl_redstone:redstone` param2 0 → `(False, 0)`; `comparator_on_comp` param2 `9*4+2` → `(True, 9)`; `lamp_on` → `(True, None)`; `lever_off` → `(False, None)`.
- [ ] **Step 3:** Run; FAIL. Implement. Move `Engine` into `tests/harness/luanti.py` and fixtures into `tests/conftest.py`.
- [ ] **Step 4:** `pytest -q` (whole suite, about 6 minutes): everything that passed before passes.
- [ ] **Step 5:** Run `python tools/fetch_minecraft_server.py --accept-eula` on this machine; expect the jar verified and the marker written.
- [ ] **Step 6:** Commit `test: fetch tool for the Minecraft server and shared harness package`.

### Task 2: Minecraft backend

**Files:** Create `tests/harness/minecraft.py`, `tests/parity/test_minecraft_rig.py`. Modify `tests/conftest.py`.

**Interfaces — Produces:**
- `minecraft.structure_nbt(grid: VoxelGrid) -> bytes`: structure template (`DataVersion` 3955, `size`, `palette`, `blocks` with `pos`, `state` and, for block entities, `nbt` including `id`), gzip NBT.
- `minecraft.Rcon(port, password)` with `cmd(text) -> str`, `close()`.
- `minecraft.MinecraftServer(tmp_path)` context manager: `start()`, `stop()` (sends `stop`, waits, kills on timeout; also registered with `atexit`), and
  `run(circuit, steps, settle: int = 20) -> list[dict]`. Each step: `{"set": {input: bool}, "wait": rt, "read": [names], "trace": n}`. Result per step: `{name: Reading}`; when `trace` is given, also `"trace": [{name: Reading}, ...]` with one entry per redstone tick after the `set`, taken before `wait` is applied.
  One server can run several circuits: each `run` places its circuit at a fresh X offset (previous extent + 16) at y = 100.
- Reading a probe uses the block the circuit has at that position: lamp → `lit`; dust → `power` (0 to 15) with `on = power > 0`; comparator → `on` from `powered`, `power` from block entity `OutputSignal`; repeater → `powered`; torches → `lit`; lever/button → `powered`.
- Input driving, as the spec's "Driving inputs" section: lever = `setblock` with `powered` flipped, then swap the mounting block to another solid block and back (stone ↔ cobblestone) before stepping; mounting position from `face`/`facing`. Button = same with `powered=true`, and the rig sets it back to `false` (with the same swap) after 10 redstone ticks for stone and polished blackstone, 15 for wooden, splitting `wait`/`trace` stepping at that moment. A `set` to `False` on a button is ignored.
- Stepping: `tick step <2*rt>` and wait until `time query gametime` has advanced that far; `tick rate 10000` is set once.
- `tests/conftest.py`: fixtures `minecraft` (function scope) and `module_minecraft` (module scope) that skip using `fetch_minecraft_server.status()` and when `java -version` is not 21 or later.

- [ ] **Step 1: Failing tests** `tests/parity/test_minecraft_rig.py`:
  - `test_lever_dust_lamp`: as the Luanti smoke test; lamp off, on, off; middle dust power 14 then 0.
  - `test_lamp_on_mounting_block_follows_lever`: stone at centre, wall lever on its east face, lamp on its west face; lamp on after set True, off after set False. (Pins the mounting-block swap.)
  - `test_button_pulse_is_released_by_the_rig`: stone button on a block, lamp on the far side; trace 14 ticks after press: lamp lit for ticks covering the pulse and dark by the end; same with an oak button and 20 ticks.
  - `test_first_read_is_settled`: NOT gate (torch on a block, lamp beside the torch, lever on the block): first read with no `set` shows the lamp on; a second read after waiting 20 more ticks is identical.
  - `test_container_items_survive_structure_placement`: chest with 27 × 64 redstone, comparator, dust; comparator power 15.
  - `test_two_circuits_in_one_server_do_not_interact`: run the lever/lamp circuit twice in one server with different inputs; results independent.
  - `test_server_is_stopped_on_error`: raise inside the `with` block; afterwards the process has exited and the RCON port refuses connections.
  - `test_no_eula_marker_means_skip_and_no_eula_file`: with `CRAFTPIPE_MINECRAFT_DIR` pointing at a dir holding the jar but no marker, constructing the fixture skips, and no `eula.txt` was written anywhere under `tmp_path`.
- [ ] **Step 2:** Run; FAIL. Implement. Iterate to PASS.
- [ ] **Step 3:** Commit `test: Minecraft server backend for running circuits`.

### Task 3: Shared suites, parity for existing circuits, recorded differences

**Files:** Create `tests/suites.py`, `tests/parity/differences.py`, `tests/parity/known_differences.json`, `tests/parity/test_parity.py`, `tests/test_differences_file.py`. Modify `tests/engine/test_orientation.py`, `test_logic.py`, `test_comparator.py`, `test_rom.py`, `test_adder.py` to take their circuits and steps from `tests/suites.py` (assertions unchanged).

**Interfaces — Produces:**
- `suites.Suite(name: str, circuit: Circuit, steps: list[dict])` and `suites.ALL: dict[str, Callable[[], Suite]]` with entries `orientation`, `logic`, `comparator`, `rom`, `adder_fast`, `adder_all` (slow).
- `differences.load() -> list[Difference]`; `Difference(id, suite, output, step, minecraft: dict, mineclonia: dict, established, title, explanation)`. `output` may be an `fnmatch` pattern. `minecraft`/`mineclonia` hold the expected `{"on": ..., "power": ...}` (only the keys that are asserted). `established` is `"measured"` or `"documented"`.
- `differences.check(suite, output, step, mc: Reading, mcl: Reading) -> None`: if a recorded difference matches (suite, output, step), assert both readings equal the recorded ones (so a difference that disappears fails); otherwise assert `mc == mcl`.
- JSON entry shape:
  ```json
  {"id": "wooden-button-pulse", "suite": "timing", "output": "button_oak.lamp", "step": "trace",
   "minecraft": {"pulse_ticks": 15}, "mineclonia": {"pulse_ticks": 10},
   "established": "documented", "title": "...", "explanation": "..."}
  ```
  For trace steps the compared quantity is named in the entry (`pulse_ticks`, `delay_ticks`, `period_ticks`); Task 4 defines how each is computed.

- [ ] **Step 1:** Move circuit and step construction from the five engine test modules into `tests/suites.py`; run `pytest tests/engine -q`; same passes as before. Commit `refactor: share test circuits between engine and parity tests`.
- [ ] **Step 2: Failing tests** `tests/test_differences_file.py`: every entry has all fields, a unique `id`, `established` in the allowed set, `suite` in `suites.ALL` or `"timing"`, non-empty `title` and `explanation`; `check` passes for equal readings with no entry, raises for unequal readings with no entry, passes when readings equal a matching entry, raises when a matching entry's difference does not occur (both sides equal).
- [ ] **Step 3: Parity tests** `tests/parity/test_parity.py`: for each non-slow suite, a module-scoped fixture runs it once on each backend; one parametrised test per (output, step) calls `differences.check`. `adder_all` is marked slow.
- [ ] **Step 4:** Run. For every failure decide, by reading both games' behaviour: (a) rig artefact → fix the rig, with a test in `test_minecraft_rig.py`; (b) craftpipe bug → failing test, fix; (c) game difference → add an entry whose explanation says why it holds for a player. Iterate until the parity run is green. Record each decision in the ledger.
- [ ] **Step 5:** Commit `test: parity of existing circuits between Minecraft and Mineclonia`.

### Task 4: Timing traces and difference-hunting circuits

**Files:** Modify `tests/engine/craftpipe_test/init.lua` and `tests/harness/luanti.py` (trace support), `tests/suites.py`. Create `tests/parity/test_timing.py`.

**Interfaces — Produces:**
- Luanti `Engine.run` accepts `"trace": n` with the same result shape as the Minecraft backend (readings through `luanti_reading`).
- `suites.timing() -> Suite`: tiles, each with a reference probe `ref` (dust directly beside the input lever) and outputs:
  `repeater_d1..d4`, `torch`, `comparator`, `lamp` (on and off delay), `repeater_chain` (four 4-tick repeaters), `locked_repeater`, `repeater_into_side`, `button_stone`, `button_oak`, `clock` (5-torch ring, period), `burnout` (1-torch loop), `through_block_container` and `through_block_container_powered15`, `dust_beside_lamp` / `dust_beside_dropper` / `dust_beside_dispenser` (read before and after an adjacent lever is used), `dust_on_glass`, `dust_on_glowstone`, `strong_vs_weak` (dust, repeater and torch each powering a block with dust and a lamp beside it).
- Trace metrics (pure functions in `tests/parity/differences.py`, unit-tested): `delay_ticks(trace, ref, out)` = first tick `out` changes minus first tick `ref` changes; `pulse_ticks(trace, out)` = number of consecutive ticks `out` is on; `period_ticks(trace, out)` = ticks between successive rising edges (None if it never repeats).
- The offset between engines in how soon `ref` itself reacts is asserted once, as its own recorded entry if non-zero.

- [ ] **Step 1: Failing unit tests** for the three metric functions on hand-written traces (including "never changes" → None).
- [ ] **Step 2:** Add trace support to the Luanti driver; test in `tests/engine/test_smoke.py` that a 6-tick trace of the lever/lamp circuit has 6 entries and the lamp turns on within it.
- [ ] **Step 3:** Build the timing suite; `test_timing.py` runs it on both backends and, per tile, compares the tile's metric through `differences.check` (step `"trace"`). Each tile's layout must be valid by Java's rules; check each tile works in Minecraft before looking at Mineclonia.
- [ ] **Step 4:** Triage failures as in Task 3 Step 4. The wooden-button entry is `"documented"` for the Minecraft side.
- [ ] **Step 5:** Commit `test: tick-by-tick timing parity and difference-hunting circuits`.

### Task 5: README from the differences file, and findings

**Files:** Create `tools/render_differences.py`. Modify `README.md`, `tests/test_differences_file.py`.

- [ ] **Step 1: Failing test** `test_readme_differences_section_is_in_sync`: the text between `<!-- differences:start -->` and `<!-- differences:end -->` in `README.md` equals `render_differences.render(differences.load())`.
- [ ] **Step 2:** Implement `render(entries) -> str` (one bullet per entry: bold title, explanation, and "(taken from documentation, not measured)" where applicable) and a CLI that rewrites the README section. Split the README's current list: game differences come from the file; converter limitations (lectern text, unlit furnaces, unsupported blocks, dust beside a lever) stay hand-written under their own heading unless Task 4 measured them as game differences.
- [ ] **Step 3:** Update the README test section (fetch tool, EULA flag, how to run parity tests) and the "Clock speed" section with measured per-component delays from both games.
- [ ] **Step 4:** Run `pytest -q` and `pytest -q -m slow`; all green.
- [ ] **Step 5:** Commit `docs: known differences generated from the parity tests`. The final message to the user lists every recorded difference in plain words and says what it implies for the Java-rules mod decision.
