# craftpipe Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Minecraft `.litematic`/`.schem` redstone schematics into Mineclonia `.mts` plus a JSON manifest, with a Luanti loader mod that makes the placed circuit work, proven by tests in a headless Luanti server.

**Architecture:** Readers produce one `VoxelGrid`; the mapper mirrors Z and applies a data-driven block table plus named rules to get node names and param2; the writer emits `.mts` v4 and a manifest. The `craftpipe_loader` mod places the schematic, then reuses Mineclonia's own hooks to connect dust, initialise redstone and fill inventories.

**Tech Stack:** Python 3.10+ (standard library only at runtime), pytest, Lua (Luanti mod API), Mineclonia release 35899, Luanti ≥ 5.10.

**Spec:** `docs/superpowers/specs/2026-11-15-craftpipe-converter-design.md`

## Global Constraints

- Python 3.10+; no runtime dependencies outside the standard library. pytest is the only dev dependency.
- Data files are JSON (not TOML: `tomllib` needs 3.11).
- Target node names come from the installed game at `~/.minetest/games/mineclonia` (release 35899). Never use `mesecons_*` names. When a param2 value or node name is in doubt, read the Mineclonia source, then let the engine test decide.
- Mapping table is written against Java Edition 1.21 block-state names; generated inputs use DataVersion 3953.
- Z mirror: `z' = max_z - z`; north↔south swapped, east/west unchanged.
- Never silently drop a block. Unmapped → fail (exit 1) unless `--allow-unmapped`.
- The manifest is JSON and is only ever parsed, never executed.
- Engine tests skip with a clear message when `luanti` or Mineclonia is missing; they never fail for that reason.
- A circuit that is valid in Minecraft but behaves differently in Mineclonia is recorded as a finding (README "Known differences"); do not bend a test to hide it.
- Work on branch `feat/converter`; commit at the end of every task.

## Review Focus

1. **Mirroring flips handedness, not just facing.** Double chests (`type=left/right`) must swap sides or the two halves pair wrongly and ROM signal changes. Test in Task 2 and Task 9.
2. **Litematic regions with negative sizes or several regions.** Litematica writes negative `Size` when the selection was dragged backwards. Test in Task 4.
3. **Unreadable input** (truncated gzip, not NBT, legacy `.schematic`, numeric IDs): one-line error and exit 2, no traceback. Test in Task 4 and Task 6.
4. **Block states with extra properties the table does not mention** (`waterlogged=false`, `powered`, `lit`) must still match their row. Test in Task 6.
5. **Loader given a hostile or missing name** (`../../x`, no manifest, manifest larger than the schematic): refuse with a chat message, place nothing. Test in Task 7.
6. **Dimension limits.** `.mts` sizes are u16 and palettes above 255 entries need multi-byte varints in `.schem`. Test in Task 3 and Task 5.

## File Structure

```
pyproject.toml
src/craftpipe/
  __init__.py        version, public re-exports
  errors.py          CraftpipeError, UnsupportedFormatError, UnmappedBlocksError
  nbt.py             NBT read/write
  grid.py            BlockState, VoxelGrid, mirror_z
  schem.py           Sponge .schem v2/v3 read + v3 write
  litematic.py       .litematic read + write
  reader.py          read_schematic() dispatch and legacy detection
  mts.py             .mts v4 write/read
  mapper.py          table loading, map_grid, Report, Conversion
  rules.py           named rules for stateful components
  signal.py          comparator signal arithmetic
  containers.py      block entities -> manifest entries
  cli.py             convert / inspect
  data/blocks.json   one-to-one rows and rule bindings
  data/items.json    item name map and stack sizes
mod/craftpipe_loader/{mod.conf,init.lua}
tests/
  test_*.py          unit tests, one file per module
  circuits.py        Circuit builder used by engine tests
  engine/conftest.py headless server harness
  engine/craftpipe_test/{mod.conf,init.lua}   test-only mod
  engine/test_*.py   engine tests
README.md
```

---

### Task 1: Project scaffold and NBT

**Files:** Create `pyproject.toml`, `src/craftpipe/__init__.py`, `src/craftpipe/errors.py`, `src/craftpipe/nbt.py`, `tests/test_nbt.py`, `.gitignore`

**Interfaces — Produces:**
- `errors.CraftpipeError(Exception)`; `UnsupportedFormatError(CraftpipeError)`; `UnmappedBlocksError(CraftpipeError)`
- Tag types in `nbt`: `Byte, Short, Int, Long` (subclass `int`), `Float, Double` (subclass `float`), `ByteArray, IntArray, LongArray` (subclass `list`), `str` for strings, `dict` for compounds, `list` for lists. Reading returns these types so read→write round-trips.
- `nbt.loads(data: bytes) -> tuple[str, dict]` (root name, root compound; accepts gzip or raw)
- `nbt.load(path) -> tuple[str, dict]`
- `nbt.dumps(root: dict, name: str = "", gzipped: bool = True) -> bytes`
- Malformed or truncated data raises `UnsupportedFormatError`.

- [ ] **Step 1:** `git switch -c feat/converter`. Write `pyproject.toml` (setuptools, src layout, `requires-python = ">=3.10"`, script `craftpipe = "craftpipe.cli:main"`, package-data `data/*.json`, optional dep group `dev = ["pytest"]`). Create a venv in `.venv` and `pip install -e .[dev]`.
- [ ] **Step 2: Failing tests** in `tests/test_nbt.py`:
  - `test_roundtrip_all_tags`: a compound holding one of each tag type, a nested compound, a list of compounds and an empty list survives `loads(dumps(x))` with equal values and equal Python types.
  - `test_negative_long_array`: `LongArray([-1, 2**63 - 1])` round-trips.
  - `test_reads_uncompressed`: `loads(dumps(x, gzipped=False))` works.
  - `test_truncated_raises`: `loads(dumps(x)[:20])` and `loads(b"not nbt")` raise `UnsupportedFormatError`.
- [ ] **Step 3:** Run `pytest tests/test_nbt.py -v`; expect import failure.
- [ ] **Step 4:** Implement `errors.py` and `nbt.py` (big-endian, modified-UTF-8 strings treated as UTF-8, empty lists written with element tag End).
- [ ] **Step 5:** Run tests; expect PASS. Commit `feat: project scaffold and NBT codec`.

### Task 2: Grid, block states, Z mirror

**Files:** Create `src/craftpipe/grid.py`, `tests/test_grid.py`

**Interfaces — Produces:**
- `BlockState(name: str, props: tuple[tuple[str, str], ...] = ())`, frozen and hashable, props sorted by key. `BlockState.parse("minecraft:repeater[facing=north,delay=2]")`; `str(state)` gives the same form; `state.get(key, default=None) -> str | None`; `state.with_props(**kv) -> BlockState`. A name without a namespace gets `minecraft:`.
- `AIR = BlockState("minecraft:air")`
- `VoxelGrid(size: tuple[int, int, int])` with `size` as (x, y, z); `get(x, y, z) -> BlockState`; `set(x, y, z, state)`; `block_entities: dict[tuple[int,int,int], dict]`; `counts() -> dict[BlockState, int]`; `positions(state) -> Iterator[tuple[int,int,int]]`; `mirror_z() -> VoxelGrid`. Internally a palette plus a flat index array; out-of-range access raises `IndexError`.

`mirror_z()` moves every cell and block entity to `z' = size_z - 1 - z` and rewrites each state:
- value swap north↔south on the property `facing` (the 16-way `rotation` property is left unchanged; blocks using it are outside the mapping table)
- key swap between properties named `north` and `south` (dust, fences, panes)
- value swap `left`↔`right` on `type` (chests) and `hinge` (doors), and `inner_left`↔`inner_right`, `outer_left`↔`outer_right` on `shape` (stairs)
- `axis` unchanged

- [ ] **Step 1: Failing tests**:
  - `test_parse_roundtrip`: `str(BlockState.parse(s)) == s` for `"minecraft:repeater[delay=2,facing=north]"`; props given unsorted compare equal.
  - `test_default_is_air`, `test_set_get`, `test_out_of_range_raises`.
  - `test_mirror_moves_cells`: grid (2,1,3) with stone at (0,0,0) → after mirror at (0,0,2).
  - `test_mirror_facing`: `repeater[facing=north]` → `facing=south`; `facing=east` unchanged; `facing=up` unchanged.
  - `test_mirror_dust_sides`: `redstone_wire[north=side,south=none,east=up,west=none]` → `north=none,south=side,east=up,west=none`.
  - `test_mirror_chest_handedness`: `chest[facing=east,type=left]` → `chest[facing=east,type=right]`; `type=single` unchanged.
  - `test_mirror_twice_is_identity` on a grid mixing all of the above plus a block entity.
- [ ] **Step 2:** Run; expect FAIL. **Step 3:** Implement. **Step 4:** Run; expect PASS.
- [ ] **Step 5:** Commit `feat: voxel grid and Z mirror`.

### Task 3: Sponge `.schem` read and write

**Files:** Create `src/craftpipe/schem.py`, `tests/test_schem.py`

**Interfaces — Consumes:** `nbt`, `VoxelGrid`, `BlockState`. **Produces:**
- `schem.read_schem(root_name: str, root: dict) -> VoxelGrid`
- `schem.write_schem(grid: VoxelGrid, path, version: int = 3, data_version: int = 3953) -> None` (versions 2 and 3)

Format facts: v2 has root name `Schematic` with `Version, DataVersion, Width (x), Height (y), Length (z)` as shorts, `Palette` (state string → Int), `BlockData` (ByteArray of varints), `BlockEntities` (list of compounds with `Pos` IntArray and `Id`, data inline). v3 has root name `""` containing `Schematic` → `Version=3`, sizes, and `Blocks` → `Palette`, `Data`, `BlockEntities` (each `Pos`, `Id`, nested `Data`). Cell index = `(y * Length + z) * Width + x`. Block entities are normalised to `{"id": ..., **data}` keyed by position.

- [ ] **Step 1: Failing tests**:
  - `test_roundtrip_v2` and `test_roundtrip_v3`: a (3,2,4) grid with five distinct states and one chest block entity carrying `Items` reads back equal (cells, size, block entity).
  - `test_large_palette_varints`: a (300,1,1) grid with 300 distinct states (`minecraft:stone[n=<i>]`) round-trips.
  - `test_unknown_version_raises`: `Version=1` raises `UnsupportedFormatError` naming the version.
- [ ] **Step 2–4:** Run FAIL, implement, run PASS.
- [ ] **Step 5:** Commit `feat: Sponge schematic reader and writer`.

### Task 4: `.litematic` read/write and reader dispatch

**Files:** Create `src/craftpipe/litematic.py`, `src/craftpipe/reader.py`, `tests/test_litematic.py`, `tests/test_reader.py`

**Interfaces — Produces:**
- `litematic.read_litematic(root: dict) -> VoxelGrid`
- `litematic.write_litematic(grid_or_regions, path, data_version: int = 3953) -> None` where the argument is a `VoxelGrid` or `list[tuple[tuple[int,int,int], VoxelGrid]]` (position, region grid); test helper keyword `negative_size: bool = False` writes regions with negative `Size` and adjusted `Position`.
- `reader.read_schematic(path) -> VoxelGrid`

Format facts: root has `Version`, `MinecraftDataVersion`, `Metadata`, `Regions` → name → `Position{x,y,z}`, `Size{x,y,z}` (components may be negative), `BlockStatePalette` (list of `{Name, Properties}`), `BlockStates` (LongArray), `TileEntities` (list with `x,y,z` relative to the region). Bits per entry = `max(2, ceil(log2(len(palette))))`. Entries are packed tightly and may straddle two longs. Index = `(y * |sz| + z) * |sx| + x`. For a negative size component the region's minimum corner on that axis is `position + size + 1`. Regions are merged into one grid spanning the union of their boxes, origin at the overall minimum; later regions overwrite only where they are non-air.

`read_schematic` dispatch: parse NBT, then choose by content, not extension: `Regions` → litematic; `Schematic` key or root name `Schematic` with `Palette` → Sponge. Root containing `Blocks` and `Data` byte arrays with `Materials` (MCEdit `.schematic`) → `UnsupportedFormatError("MCEdit .schematic (numeric block IDs, pre-1.13) is not supported")`. Anything else → `UnsupportedFormatError` naming the root keys found.

- [ ] **Step 1: Failing tests**:
  - `test_roundtrip_single_region`: (5,3,4) grid with 3, 5 and 17 palette sizes (three cases, to cross bit-width boundaries and force straddling).
  - `test_negative_size_region`: same grid written with `negative_size=True` reads back identical.
  - `test_two_regions_merged`: region A (2,1,2) at (0,0,0) and region B (2,1,2) at (3,0,1) → grid size (5,1,3) with each block at its absolute offset; block entity in B lands at its merged position.
  - `test_dispatch_by_content`: a `.schem` file renamed `.litematic` still reads.
  - `test_legacy_mcedit_rejected`: hand-built NBT with `Materials="Alpha"`, `Blocks`, `Data` raises `UnsupportedFormatError` mentioning `MCEdit`.
  - `test_garbage_rejected`: a file of random bytes raises `UnsupportedFormatError`.
- [ ] **Step 2–4:** Run FAIL, implement, run PASS.
- [ ] **Step 5:** Commit `feat: litematic reader and format dispatch`.

### Task 5: `.mts` writer

**Files:** Create `src/craftpipe/mts.py`, `tests/test_mts.py`

**Interfaces — Produces:**
- `mts.write_mts(path, size: tuple[int,int,int], names: list[str], node_ids: Sequence[int], param2: Sequence[int]) -> None`
- `mts.read_mts(path) -> tuple[size, names, node_ids, param2]`
- `mts.index(size, x, y, z) -> int` = `(z * size_y + y) * size_x + x`

Format (all big-endian): `b"MTSM"`, u16 version `4`, u16 size x, y, z, then `size_y` bytes of slice probability `127`, u16 name count, each name as u16 length + bytes, then one zlib stream of: node ids (u16 each), param1 (u8 each, `127`), param2 (u8 each). Any size component over 65535 or under 1 raises `CraftpipeError`.

- [ ] **Step 1: Failing tests**: `test_header_bytes` (first 12 bytes for size (2,3,4) equal `b"MTSM\x00\x04\x00\x02\x00\x03\x00\x04"`); `test_roundtrip`; `test_index_order` (`index((2,3,4),1,0,0)==1`, `index((2,3,4),0,1,0)==2`, `index((2,3,4),0,0,1)==6`); `test_oversize_raises`.
- [ ] **Step 2–4:** Run FAIL, implement, run PASS. **Step 5:** Commit `feat: MTS v4 writer`.

### Task 6: Mapper, structural blocks, report, CLI

**Files:** Create `src/craftpipe/mapper.py`, `src/craftpipe/rules.py` (registry only), `src/craftpipe/data/blocks.json`, `src/craftpipe/cli.py`, `tests/test_mapper.py`, `tests/test_cli.py`

**Interfaces — Produces:**
- `rules.Node = NamedTuple(name: str, param2: int)`; `rules.RULES: dict[str, Callable[[BlockState], Node | None]]`; decorator `@rules.rule("name")`.
- `mapper.Report` with `unmapped: dict[str, UnmappedEntry]` (`count: int`, `positions: list` of first 5 source positions, `reason: str | None`), `warnings: list[str]`, `counts: dict[str, int]` (output node name → count), `to_json() -> dict`.
- `mapper.Conversion` with `size`, `names`, `node_ids`, `param2`, `manifest: dict`, `report: Report`, and `to_luanti(pos) -> tuple[int,int,int]` mapping a source position to schematic-relative Luanti coordinates.
- `mapper.map_grid(grid: VoxelGrid, *, allow_unmapped: bool = False, source: str = "") -> Conversion`; raises `UnmappedBlocksError` (carrying the `Report`) when anything is unmapped and `allow_unmapped` is false.
- `mapper.PLACEHOLDER = "mcl_core:bedrock"` (verify the name exists in the installed game; if not, pick another unmistakable solid node and update this line).
- `convert(input_path, output_path=None, *, allow_unmapped=False) -> Conversion` in `craftpipe/__init__.py`, writing `<out>.mts` and `<out stem>.craftpipe.json`.
- CLI as in the spec. Exit codes: 0 ok, 1 unmapped blocks, 2 unreadable input or other `CraftpipeError`.

`blocks.json` shape:

```json
{
  "blocks": {
    "minecraft:stone": "mcl_core:stone",
    "minecraft:white_wool": "mcl_wool:white",
    "minecraft:smooth_stone_slab": {"rule": "slab", "base": "mcl_stairs:slab_stone"}
  },
  "unsupported": {
    "minecraft:piston": "pistons are not supported",
    "minecraft:observer": "observers are not supported"
  }
}
```

A string row matches the block name regardless of properties and gives param2 0. An object row calls the named rule, passing extra keys as keyword arguments. `unsupported` rows always count as unmapped, with the reason. `minecraft:air`, `cave_air`, `void_air` → `air`.

Rows for this task (find each Mineclonia name with grep in the installed game; a row whose target name is not registered there is a bug): all 16 colours of wool, concrete, terracotta, stained glass; glass; stone, cobblestone, smooth stone, stone bricks, the three polished stones; all overworld planks; iron/gold/diamond blocks; glowstone; sea lantern; and `slab` rule for the matching slabs (`type=bottom|top|double`). `unsupported`: piston, sticky_piston, piston_head, moving_piston, observer, slime_block, honey_block.

Manifest (written by `convert`): `{"format": 1, "source": <file name>, "converter": <version>, "size": [x,y,z], "complete": bool, "substituted": {state: count}, "containers": [], "meta": []}`.

- [ ] **Step 1: Failing tests** in `tests/test_mapper.py`:
  - `test_every_target_exists_in_mineclonia`: every node name reachable from `blocks.json` string rows appears in a `register_node`-derived name set or grep of the installed game; skip if the game is absent.
  - `test_maps_and_mirrors`: grid (1,1,2) with stone at z=0, white wool at z=1 → node at `index(size,0,0,1)` is `mcl_core:stone`.
  - `test_extra_properties_ignored`: `minecraft:stone[waterlogged=false]` maps like `minecraft:stone`.
  - `test_unmapped_raises_with_report`: a grid with 7 × `minecraft:dragon_egg` raises `UnmappedBlocksError`; report entry count 7, 5 positions.
  - `test_unsupported_reason`: `minecraft:piston[facing=up]` reports reason `"pistons are not supported"`.
  - `test_allow_unmapped_marks_incomplete`: with the flag, output contains `PLACEHOLDER`, `manifest["complete"] is False`, `manifest["substituted"]` lists the state.
  - `test_slab_rule`: bottom, top and double variants map to three distinct, registered results.
  - `test_to_luanti`: on size (3,2,4), `to_luanti((1,0,0)) == (1,0,3)`.
- [ ] **Step 2:** Tests in `tests/test_cli.py` (run via `subprocess` on `python -m craftpipe`): `convert` on a generated `.schem` writes both files and exits 0; on a grid with an unmapped block exits 1 and prints the block name; on a garbage file exits 2 with a one-line message and no `Traceback` in stderr; `inspect` prints dimensions and block counts and exits 1 when something would be unmapped; `convert --report r.json` writes `Report.to_json()` to that file in both the success and the unmapped case.
- [ ] **Step 3–5:** Run FAIL, implement (add `src/craftpipe/__main__.py`), run PASS.
- [ ] **Step 6:** Commit `feat: mapper, structural block table and CLI`.

### Task 7: Loader mod and engine harness

This task proves the riskiest assumption (a headless Mineclonia server can place and run a converted circuit) on the smallest circuit: lever → dust → lamp.

**Files:** Create `mod/craftpipe_loader/mod.conf`, `mod/craftpipe_loader/init.lua`, `tests/circuits.py`, `tests/engine/conftest.py`, `tests/engine/craftpipe_test/mod.conf`, `tests/engine/craftpipe_test/init.lua`, `tests/engine/test_smoke.py`. Modify `src/craftpipe/data/blocks.json`, `src/craftpipe/rules.py`, `tests/test_mapper.py`.

**Interfaces — Produces:**
- Lua: `craftpipe.place(pos, name) -> ok, message_or_stats`; chat command `/craftpipe_place <name>` (privilege `server`). Reads `<worldpath>/schems/<name>.mts` and `<name>.craftpipe.json`. `name` must match `^[%w_%-]+$`, else refuse. Missing manifest → refuse. Manifest positions outside `size` → refuse. Manifest `complete == false` → place, and send a warning line beginning `WARNING: not gradeable`.
  After `core.place_schematic(pos, path, "0", nil, true)`: for every node in the region whose definition is in group `redstone_wire` or has `_mcl_redstone`, call its `on_construct(pos)` (this connects dust and queues Mineclonia's init); then apply manifest `containers` and `meta` (Task 9 fills these in; this task accepts empty lists).
- Rules added now: `lever`, `dust`, plus string row for `minecraft:redstone_lamp` handled by rule `lamp` (`lit=true` → `mcl_redstone_lamp:lamp_on`). `dust` → `mcl_redstone:redstone` with param2 = `power` (the loader's `on_construct` picks the shape). `lever`: derive facedir values for `face=floor|wall|ceiling` × `facing` from `mcl_lever/init.lua`.
- `tests/circuits.py`: `Circuit(size)` wrapping a `VoxelGrid` in Minecraft coordinates with `block(x,y,z,"state string")`, `fill(x0,y0,z0,x1,y1,z1,"state")`, `input(name, pos)` (places a floor lever on `pos`, records it), `output(name, pos)` (places a lamp, records it), `save(path)` writing `.schem` or `.litematic` by extension. Every circuit sits on a one-block floor of `minecraft:stone`.
- `tests/engine/conftest.py`: fixture `engine` with
  `engine.run(circuit: Circuit, steps: list[dict], fmt: str = "schem") -> list[dict]`. Each step is `{"set": {input_name: bool}, "wait": ticks, "read": [output_name, ...]}`; each result is `{output_name: {"name": node_name, "param2": int, "on": bool}}`. `on` is true when the node name ends in `_on`. Also `engine.run_raw(conversion_dir, name, job) -> dict` for tests that need raw positions.
  The fixture builds a throwaway world in `tmp_path` (`world.mt` with `gameid = mineclonia`, `backend = sqlite3`, `load_mod_craftpipe_loader = true`, `load_mod_craftpipe_test = true`; mods copied into `<world>/worldmods/`; `map_meta.txt`/config setting `mg_name = singlenode`), writes the converted files to `<world>/schems/`, writes `<world>/craftpipe_test/job.json`, starts `luanti --server --world <dir> --config <tmp conf> --quiet` on a free port, waits (timeout 120 s) for `<world>/craftpipe_test/result.json`, and kills the server if it outlives the timeout. Skips when `shutil.which("luanti")` is None or `~/.minetest/games/mineclonia` is absent.
- `craftpipe_test` mod: on first globalstep, forceload/emerge the target region at (0, 10, 0), call `craftpipe.place`, then run the job's steps: set levers through the node's `on_rightclick` when the wanted state differs, wait the given number of redstone ticks (`mcl_redstone.tick_speed` each), read nodes, write `result.json` (including `place_message` and any Lua error text), then `core.request_shutdown()`.

- [ ] **Step 1:** Unit tests for the `lever`, `dust`, `lamp` rules in `tests/test_mapper.py` (node names exist; lever on/off maps to `_on`/`_off`; dust `power=7` gives param2 7).
- [ ] **Step 2: Failing engine test** `tests/engine/test_smoke.py::test_lever_dust_lamp`: circuit of floor, lever at (0,1,0), dust at (1..3,1,0), lamp at (4,1,0). Steps: read (off) → set on, wait 10, read (on) → set off, wait 10, read (off). Run both `fmt="schem"` and `fmt="litematic"` (parametrised).
- [ ] **Step 3:** `test_dust_is_connected_after_place`: read the node at the middle dust position; its name starts with `mcl_redstone:wire_`.
- [ ] **Step 4:** Loader refusal tests via `run_raw`: name `../x` → result `place_ok == false`; manifest deleted → false; manifest with a container at `[99,0,0]` → false; manifest `complete=false` → true and message starts `WARNING: not gradeable`.
- [ ] **Step 5:** Run `pytest tests/engine -v`; expect FAIL. Implement mod, harness, rules. Iterate until PASS. If the headless server cannot run Mineclonia at all, stop and report: the design's testing approach depends on it.
- [ ] **Step 6:** Commit `feat: loader mod and headless engine test harness`.

### Task 8: Redstone components and logic circuits

**Files:** Modify `src/craftpipe/rules.py`, `src/craftpipe/data/blocks.json`, `tests/test_mapper.py`, `tests/circuits.py`. Create `tests/engine/test_orientation.py`, `tests/engine/test_logic.py`.

**Interfaces — Produces:** rules `repeater`, `comparator`, `torch`, `wall_torch`, `button`; string rows `minecraft:redstone_block` → `mcl_redstone_torch:redstoneblock`, `minecraft:target`. Circuit helpers in `tests/circuits.py`: `not_gate()`, `or_gate()`, `and_gate()`, `xor_gate()`, `full_adder()`, `ripple_adder(bits=4)`, `d_flip_flop()`, each returning a `Circuit` with named inputs/outputs (`a0..a3`, `b0..b3`, `cin`, `s0..s3`, `cout`; flip-flop `d`, `clk`, `q`).

Rule behaviour:
- `repeater`: `mcl_repeaters:repeater_{off|on}_{delay}`; `locked=true` → `repeater_{off|on}_locked`; param2 from `facing` (4dir). Note Minecraft's `facing` on repeaters and comparators names the side the *input* faces; derive the param2 table from `mcl_repeaters/init.lua` and let the orientation test confirm it.
- `comparator`: `mcl_comparators:comparator_{off|on}_{comp|sub}` from `powered`, `mode=compare|subtract`; param2 as repeater.
- `torch`: `minecraft:redstone_torch[lit]` → `mcl_redstone_torch:redstone_torch_{on|off}`, wallmounted param2 1 (floor). `wall_torch`: `..._wall` variants, param2 from `facing` (the torch points away from its support block).
- `button`: all Minecraft button materials with a Mineclonia `mcl_buttons:button_<material>_{off|on}`; `face` + `facing` → wallmounted.

- [ ] **Step 1:** Unit tests: each rule yields registered node names for every state combination; four facings give four distinct param2 values; north and south differ.
- [ ] **Step 2: Failing orientation tests** (`test_orientation.py`), parametrised over the four Minecraft facings, each built so that only the correct orientation lights the lamp and a wrong one leaves it dark:
  - repeater: lever → repeater → lamp in a line along the facing axis; also the reversed repeater must *not* light the lamp.
  - comparator: same layout.
  - wall torch on each side of a block: unpowered block → lamp beside the torch on; powering the block turns it off.
  - floor torch: lamp above is on; powering the support turns it off.
  - lever on each wall face and on floor and ceiling powers the block it is attached to.
  - button: lamp on after press, off again after 30 ticks.
- [ ] **Step 3: Failing dust tests**: corner, T, cross, a step up one block and a step down one block each carry a lever signal to a lamp; signal dies after 15 dust (lamp at distance 16 stays off; a repeater mid-way restores it).
- [ ] **Step 4: Failing logic tests** (`test_logic.py`): NOT, OR, AND, XOR over all input rows; comparator compare and subtract modes for rear/side strengths over {0, 1, 7, 8, 14, 15}², strengths produced by dust-length attenuation from a lever, output read as dust param2 & 15 next to the comparator; 4-bit ripple adder over all 512 combinations of a, b, cin (one server run, 512 steps; mark `@pytest.mark.slow`), plus a fast 16-case subset in the default run; D flip-flop: clock in 0 then 1, read q each time, then check q holds while d changes with clk low.
- [ ] **Step 5:** `test_stored_state_survives_load`: flip-flop schematic built with its latch already holding 1 (torch/dust states set accordingly); read q immediately after placing and settling. Record the outcome; if the bit is lost, mark the test `xfail(strict=True)` with reason text and add the finding to a `KNOWN_DIFFERENCES.md` scratch list for Task 10.
- [ ] **Step 6:** Measure settle time: the adder test records the smallest `wait` (in redstone ticks) at which all 16 fast cases pass, found by trying 2, 4, 8, 16, 32; write the number into `KNOWN_DIFFERENCES.md`.
- [ ] **Step 7:** Run FAIL, implement rules and circuits, iterate to PASS. Any circuit that is correct by Minecraft's rules but fails in the engine: confirm against Mineclonia source, then record as a finding instead of redesigning it to pass.
- [ ] **Step 8:** Commit `feat: redstone component rules with orientation and logic tests`.

### Task 9: Containers, manifest and ROM

**Files:** Create `src/craftpipe/signal.py`, `src/craftpipe/containers.py`, `src/craftpipe/data/items.json`, `tests/test_signal.py`, `tests/test_containers.py`, `tests/engine/test_rom.py`. Modify `mapper.py`, `rules.py`, `blocks.json`, `mod/craftpipe_loader/init.lua`.

**Interfaces — Produces:**
- `signal.container_signal(slots: int, stacks: Iterable[tuple[int, int]]) -> int` where each stack is (count, max_stack): `0` when no items, else `floor(1 + 14 * sum(count / max_stack) / slots)`.
- `containers.extract(grid: VoxelGrid) -> list[dict]` run on the already-mirrored grid; each entry `{"pos": [x,y,z], "node": name, "lists": {listname: [{"slot": int, "name": itemname, "count": int}]}, "signal": int}` with `pos` in Luanti schematic coordinates and slots 1-based.
- Rules `chest` (single and double, `type` already mirrored; trapped chests too), `barrel`, `furnace`, `hopper`, `dropper`, `dispenser`, `lectern`. Take node names, param2 conventions and inventory list names from the installed game (`mcl_chests`, `mcl_barrels`, `mcl_furnaces`, `mcl_hoppers`, `mcl_dispensers`, and the `mcl_comparators/init.lua` measure table).
- `items.json`: `{"items": {"minecraft:redstone": "mcl_redstone:redstone", ...}, "stack_size": {"minecraft:ender_pearl": 16, ...}, "filler": {"64": ..., "16": ..., "1": ...}}`. Unknown Minecraft items use the filler of the same stack size (default 64 unless listed in `stack_size`), and the report gets one warning per distinct substituted item. Fillers must be registered Mineclonia items with that stack size.
- Loader: for each manifest container, set each list's stacks on the node inventory, then call `mcl_redstone.update_comparators(pos)`.
- Lecterns: read `mcl_lectern/init.lua`. If its comparator output can be set from metadata, emit a manifest `meta` entry and test it; if not, move `minecraft:lectern` to `unsupported` with reason `"lectern page signal cannot be set"` and note it for the README.

Furnace slot mapping: Minecraft slots 0, 1, 2 → Mineclonia `src`, `fuel`, `dst`. Double chests: Minecraft stores 27 slots in each half; each half becomes its own manifest entry with its own inventory, and `signal` is computed across both halves (54 slots).

- [ ] **Step 1: Failing unit tests**: `container_signal(27, []) == 0`; `(27, [(1,64)]) == 1`; `(27, [(64,64)]*27) == 15`; `(27, [(64,64)]*13 + [(32,64)]) == 8`; `(5, [(16,16)]) == 3`; property check that signal is monotone in item count for 27 slots.
- [ ] **Step 2: Failing container tests**: a chest block entity with `Items` (`Slot` 0 and 26) yields slots 1 and 27; unknown item `minecraft:nautilus_shell` becomes the 64-filler and produces a warning; `minecraft:ender_pearl` ×16 keeps a 16-stack filler or mapped item so `signal` matches; mirrored double chest: left/right halves keep their own contents and both report the 54-slot signal; a block entity whose block is not a container is ignored.
- [ ] **Step 3: Failing engine test** `test_rom.py::test_chest_signal_strengths`: 15 chests, chest *n* filled with the minimum number of `minecraft:redstone` items that gives signal *n*, each with a comparator and dust behind it; after placing and settling, dust param2 & 15 equals *n* for all 15, and equals the manifest `signal`. Repeat one case each for barrel, furnace, hopper, dropper, and a double chest.
- [ ] **Step 4:** Run FAIL, implement, iterate to PASS.
- [ ] **Step 5:** Commit `feat: container contents, manifest and ROM signal tests`.

### Task 10: README and final check

**Files:** Create `README.md`. Delete `KNOWN_DIFFERENCES.md` after folding it in.

- [ ] **Step 1:** Write `README.md`: what it is; install; `convert` and `inspect` with a sample report; installing `mod/craftpipe_loader` (world `worldmods/` or `~/.minetest/mods`), copying files to `<world>/schems/`, `/craftpipe_place`; why plain `//mtschemplace` is not enough; supported blocks and the unsupported list with reasons; how to add a mapping row; `--allow-unmapped` and "not gradeable"; input versions (Java 1.13+, table written for 1.21; legacy formats rejected); **Clock speed** section stating the measured adder settle time in redstone ticks and seconds and the `mcl_redstone_update_tick` setting; **Known differences** from Tasks 8 and 9; running tests (`pytest`, `pytest -m slow`).
- [ ] **Step 2:** Add a mapper warning for each known difference recognisable from one block state (per the spec); unit-test each. Skip this step if there are none.
- [ ] **Step 3:** Run `pytest -v` and `pytest -m slow -v`; all pass or are documented `xfail`. Run `craftpipe convert` on the saved adder `.litematic` from a clean shell to confirm the installed entry point works.
- [ ] **Step 4:** Commit `docs: README with usage, clock guidance and known differences`.
