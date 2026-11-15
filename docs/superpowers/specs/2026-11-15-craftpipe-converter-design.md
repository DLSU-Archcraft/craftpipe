# craftpipe: Minecraft redstone schematic to Mineclonia converter

Date: 2026-11-15. Status: awaiting approval.

## Intent

ArchCraft II teaches computer architecture with redstone builds (ALUs, CPUs,
RAM, ROM) running in Luanti/Mineclonia instead of Minecraft. Existing builds
and student work made in Minecraft need to be brought across so they can be
run and graded without Minecraft licences or a JVM.

craftpipe converts a Minecraft schematic (`.litematic` or `.schem`) into a
Mineclonia schematic (`.mts`) plus a manifest, and ships a small Luanti mod
that loads the result into a world so the circuit actually works.

## Goals

1. `craftpipe convert build.litematic` produces `build.mts` and
   `build.craftpipe.json`.
2. Loading the result in Mineclonia gives a circuit that behaves like the
   original: every directional component faces the right way, dust is
   connected, containers used as ROM give the same comparator signal strength.
3. A conversion never silently drops a block. Anything unmapped is reported
   by name, count and position, and fails the conversion by default.
4. Correctness is proven in the real engine by automated tests, not by
   inspection.

## Non-goals (this round)

- Converting a full real CPU and comparing against a Minecraft baseline
  (handoff Phase 4). The real builds are being requested from colleagues;
  that is a follow-up project once they arrive.
- Pistons, observers, slime/honey contraptions, quasi-connectivity, 0-tick
  tricks. They are reported as unmapped, not approximated.
- Entities (minecarts, item frames, armour stands).
- Whole-world conversion (`.mca`), Bedrock formats, or converting back to
  Minecraft.
- Cosmetic fidelity for decorative blocks beyond a reasonable palette.

## Anti-goals

- A conversion that "succeeds" but yields a circuit that computes something
  different. A loud failure is always better than a subtly wrong CPU,
  because the output is used for grading.
- Running code from a converted file on the grader's machine.

## Constraints and facts found on the target machine

Target: Mineclonia release 35899 on Luanti (min version 5.10), with WorldEdit
installed. The handoff's node names (`mesecons_*`) are out of date. Actual:

| Component | Mineclonia nodes | param2 |
|---|---|---|
| Dust | `mcl_redstone:redstone` (dot), `mcl_redstone:wire_<flags>` (connected) | low 4 bits = power; node name encodes connection shape |
| Repeater | `mcl_repeaters:repeater_{off,on}_{1..4}`, `repeater_{off,on}_locked` | `4dir` |
| Comparator | `mcl_comparators:comparator_{off,on}_{comp,sub}` | `4dir` |
| Torch | `mcl_redstone_torch:redstone_torch_{on,off}` and `..._wall` | `wallmounted` |
| Lever | `mcl_lever:lever_{off,on}` | `facedir` |
| Button | `mcl_buttons:button_<material>_{off,on}` | `wallmounted` |
| Lamp | `mcl_redstone_lamp:lamp_{off,on}` | none |
| Redstone block | `mcl_redstone_torch:redstoneblock` | none |

Other facts that drive the design:

- **Schematic placement skips node setup.** `core.place_schematic` (and so
  WorldEdit `//mtschemplace`) does not call `on_construct`. Dust chooses its
  connected shape only in `on_construct`, so a pasted `.mts` has unconnected
  dust unless something fixes it afterwards.
- Mineclonia re-initialises redstone nodes through two load-time LBMs
  (`mcl_redstone:update`, `mcl_redstone:update_neighbours`), so powered state
  self-corrects once dust shapes are right.
- Redstone runs on Mineclonia's own event queue, tick length
  `mcl_redstone_update_tick` (default 0.1 s), not on node timers.
- Comparators read chests, barrels, furnaces, dispensers/droppers, hoppers
  and lecterns from node inventory/metadata. `.mts` cannot carry either.
- Coordinates: Minecraft +Z is south, Luanti +Z is north. The converter
  mirrors Z (`z' = max_z - z`) and swaps north/south in every facing; east
  and west are unchanged.
- No sample schematics exist yet; test inputs are generated.

## Approaches

**A. `.mts` plus a loader mod (chosen).** The converter writes `.mts` and a
manifest. A mod places the schematic and then lets Mineclonia finish the job:
connect dust, initialise redstone, fill inventories. Reuses the game's own
logic, so it tracks Mineclonia changes. Cost: the mod is required.

**B. Fully resolved `.mts`, no mod.** The converter computes dust shapes and
power states itself. Works with plain WorldEdit, but duplicates Mineclonia's
redstone rules in Python (brittle across releases) and still cannot fill ROM
containers.

**C. No `.mts`; the mod places a node list one by one.** Setup hooks fire
naturally, but it is slow for CPU-sized builds and gives up WorldEdit
compatibility and the handoff's output format.

The user left the how to the implementer; A was chosen for the reasons above.
This and every decision marked *(my call)* below was made by the implementer,
not agreed line by line.

## Design

### Pieces

```
build.litematic ─┐
build.schem ─────┴─> reader ─> VoxelGrid ─> mapper ─> .mts writer ─> build.mts
                                              │
                                              └─> manifest ─> build.craftpipe.json
                                              └─> report (stdout / --report json)

Luanti: craftpipe_loader mod  reads both files, places, fixes up
```

1. **Readers** (`.litematic`, `.schem`). Each returns the same in-memory
   grid: dimensions, a block-state per cell (name plus properties), and block
   entities by position. Litematic files with several regions are merged into
   one grid by their region offsets. Sponge schematic versions 2 and 3 are
   supported. NBT is parsed by a small in-repo reader *(my call: no runtime
   dependencies; the format is small and this avoids version drift in
   third-party libraries on Python 3.14)*.
2. **Mapper.** Applies the Z mirror, then turns each Minecraft block state
   into a Mineclonia node name and param2 using a data-driven table kept in
   the repo as a data file, not code, so colleagues can extend it. Simple
   one-to-one blocks are table rows; components whose node name depends on
   state (repeater delay, comparator mode, wall vs floor torch, lever face)
   use small named rules. Air stays air.
3. **Writer.** `.mts` version 4, written directly.
4. **Manifest** (`<name>.craftpipe.json`). Lists, by position relative to the
   schematic origin: container contents, and any per-node metadata the loader
   must set. Also records source file, converter version, dimensions and the
   expected comparator signal strength of each container (for checking).
   *(My call: JSON, not the `.lua` manifest the handoff suggested. A Lua
   manifest would be executed by the loader, and these files can come from
   students.)*
5. **Loader mod** (`craftpipe_loader`, shipped in this repo under `mod/`).
   Chat command `/craftpipe_place <name>` (needs the `server` privilege)
   places `<world>/schems/<name>.mts` at the player's position, and a Lua
   function `craftpipe.place(pos, name)` does the same for scripts. After
   placing it: fixes dust connections, triggers redstone initialisation for
   the region, applies the manifest. It reports how many nodes and containers
   it handled. Files are read from the same `schems/` folder WorldEdit uses.

Plain `//mtschemplace` still loads the `.mts`, but dust will not be connected
and containers will be empty; the README says to use the loader.

### State carried over

*(My call.)* Stored state is preserved where Mineclonia has a matching node:
lever on/off, torch lit/unlit, repeater delay, powered and locked, comparator
mode and powered, lamp lit, dust power level. Mineclonia's initialisation
then reconciles anything inconsistent. Whether a latch's stored bit survives
that reconciliation is to be established by the D flip-flop test; if it does
not, the README documents that memory contents are reset on load.

### Unmapped blocks

Default: conversion fails and prints each unmapped block state with count and
first few positions. `--allow-unmapped` converts anyway, substituting a
conspicuous placeholder node, and still prints the report. Blocks in the
explicit non-goals list are reported with the reason ("pistons are not
supported").

`--allow-unmapped` output is for looking at, not grading *(my call)*. A
placeholder cannot know whether the original block was solid, and solidity
changes how dust and power behave. So the manifest records
`"complete": false` with the list of substituted blocks, and the loader
prints a prominent warning when placing such a build. The way to make a
build gradeable is to add the missing rows to the mapping table.

### Known behaviour differences

*(My call.)* When the engine tests show that a construct maps cleanly but
behaves differently in Mineclonia (for example a latch losing its bit on
load), it is documented in the README, and if it can be recognised from a
single block state the mapper emits a named warning in the report. Warnings
do not change the exit code. General circuit pattern detection is out of
scope; the warning list starts empty and grows only from test findings.

### Input versions

The user's steer: Mineclonia tracks a recent Java Edition release (they
recalled 1.21), and builds are expected from around that version. So the
mapping table is written against Java Edition 1.21 block-state names, and
generated test inputs use 1.21 names and data versions. Anything from 1.13
onwards uses the same namespaced scheme and is accepted; a block whose name
changed between versions simply shows up as unmapped until a row is added. Legacy inputs (numeric block IDs,
MCEdit `.schematic`, pre-1.13 Litematica) are detected and rejected with a
message naming the format; a translation layer for them would be a separate
piece of work.

### Containers and ROM

Comparator output depends only on how full a container is, so the goal is
identical signal strength, not identical items. Items with a known Mineclonia
equivalent are mapped; anything else is replaced by a filler item of the same
maximum stack size, which leaves the signal unchanged *(my call)*. The
converter computes the Minecraft signal strength from the source inventory
and writes it to the manifest; the loader test asserts the comparator reads
that value. Covered: chest (single and double), trapped chest, barrel,
furnace, hopper, dropper, dispenser. Lecterns: carried over if Mineclonia's
lectern page signal can be set from metadata; otherwise reported as
unsupported. The builder determines which.

### CLI

```
craftpipe convert INPUT [-o OUTPUT.mts] [--allow-unmapped] [--report FILE.json]
craftpipe inspect INPUT        # dimensions, block counts, what would be unmapped
```

Exit code is non-zero when anything is unmapped (without `--allow-unmapped`)
or the input cannot be read. Python 3.10+, installable package, importable
as a library with the same steps exposed as functions.

### Testing

Two layers.

- **Unit tests** (pytest): NBT and both readers against generated files,
  `.mts` writer round-trip, Z mirror and facing swap, every mapping rule,
  signal strength arithmetic, unmapped reporting.
- **Engine tests**: a harness starts a headless Luanti server on a throwaway
  flat Mineclonia world with the loader and a test-only mod. The test mod
  places a converted circuit, sets levers, waits a number of redstone ticks,
  reads lamp states and comparator power, writes results as JSON and shuts
  the server down. pytest compares against truth tables. These tests are
  skipped with a clear message when `luanti` or Mineclonia is not installed.

Test circuits are built by a Python circuit builder that writes `.schem` and
`.litematic` files in Minecraft coordinates, so the inputs exercise the real
readers:

- each directional component (repeater, comparator, torch, lever, button) in
  every orientation, checked by which lamp lights
- dust: straight, corners, T, cross, stepping up and down a block
- NOT, OR, AND, XOR from torches
- comparator compare and subtract modes across signal strengths 0 to 15
- 4-bit ripple-carry adder, all 256 input pairs with carry in
- D flip-flop
- container ROM: containers filled to give each signal strength 1 to 15

Expected results come from truth tables, since no Minecraft baseline is
available here. A circuit that is valid in Minecraft but behaves differently
in Mineclonia is a finding to document, not something to hide by adjusting
the test.

### Timing guidance

The README gets a short section for end users on clock speed, based on what
the engine tests measure (how many redstone ticks the adder needs to settle),
rather than the handoff's assumed 2x to 4x padding.

## Left to the builder

- Module layout, mapping file format (JSON or TOML), internal types.
- Exact palette of structural and decorative blocks in the first mapping
  table; at minimum wool, concrete, terracotta, glass and stained glass,
  stone variants, planks, slabs, and everything in the table above.
- How the loader fixes dust (calling the nodes' `on_construct`, or
  Mineclonia's wire-connect function) and triggers initialisation.
- param2 values per facing for each component, to be derived from the
  installed Mineclonia source and confirmed by the orientation tests.
- How slabs and other upside-down/top-half variants map.
- Headless server mechanics (config file, how the test mod signals
  completion, timeouts).
- Lectern support, as above.

## Order of work

1. Readers, grid, Z mirror, `.mts` writer, structural blocks, CLI skeleton.
2. Loader mod and engine test harness, proven on a lamp-and-lever circuit.
3. Redstone mapping rules with orientation tests, then gates, adder,
   flip-flop.
4. Containers, manifest, ROM tests.
5. README: usage, loader install, unsupported blocks, timing guidance.
