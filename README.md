# craftpipe

Converts Minecraft redstone schematics (`.litematic`, Sponge `.schem`) into
Mineclonia schematics (`.mts`) for Luanti, so that computer-architecture
builds (adders, ALUs, ROM, CPUs) made in Minecraft can be run and graded
without Minecraft.

A conversion produces two files:

- `build.mts`: the blocks.
- `build.craftpipe.json`: a manifest with what `.mts` cannot hold
  (container contents for comparator ROM, lectern pages).

The bundled Luanti mod `craftpipe_loader` places both and makes the circuit
work.

Tested against Mineclonia release 35899 on Luanti 5.17.

## Install

```
python -m venv .venv
.venv/bin/pip install -e .          # add [dev] for the tests
```

Python 3.10 or later. No other dependencies.

## Convert

```
$ craftpipe convert adder.litematic
adder.mts: 152 x 5 x 15, 3301 nodes, 0 container(s)
adder.craftpipe.json: manifest
```

Options: `-o OUT.mts` to choose the output path, `--report FILE.json` to
save the report, `--allow-unmapped` (see below).

`craftpipe inspect FILE` prints the size, the block counts and anything
that would not convert, without writing files.

Exit codes: `0` converted, `1` some blocks have no mapping, `2` the input
could not be read.

As a library:

```python
import craftpipe
conv = craftpipe.convert("adder.litematic")     # writes both files
conv.report.unmapped, conv.report.warnings, conv.manifest
```

### Blocks that do not convert

craftpipe never drops a block silently. If anything has no Mineclonia
equivalent, the conversion stops and lists it:

```
$ craftpipe convert adder4.litematic
1 block(s) in 1 state(s) have no Mineclonia mapping:
       1 x minecraft:sticky_piston[extended=false,facing=up]  [pistons are not supported]
           at (0,1,14)
Nothing was written. ...
```

Positions are in the source schematic's coordinates.

`--allow-unmapped` converts anyway and puts bedrock where the unmapped
blocks were. **That output is for looking at, not for grading.** A
placeholder cannot know whether the original block was solid, and that
changes how redstone behaves around it. The manifest is marked
`"complete": false` and the loader prints `WARNING: not gradeable` when it
is placed. To make a build gradeable, add the missing blocks to the
mapping table.

## Load into Mineclonia

1. Copy `mod/craftpipe_loader` into the world's `worldmods/` folder (or
   into your Luanti `mods/` folder and enable it for the world).
2. Copy `build.mts` and `build.craftpipe.json` into `<world>/schems/`
   (the same folder WorldEdit uses).
3. In the game, with the `server` privilege, stand where the build's
   lowest corner should go and run:

   ```
   /craftpipe_place build
   ```

From Lua: `craftpipe.place(pos, "build")` (area must already be generated)
or `craftpipe.place_async(pos, "build", callback)`.

### Why not WorldEdit's `//mtschemplace`?

It will place the blocks, but pasting a schematic skips each node's setup
step. Redstone dust stays as unconnected dots, containers have no
inventory, and ROM is empty. `craftpipe_loader` runs that setup, lets
Mineclonia initialise the redstone, and fills the containers from the
manifest. The manifest is read as JSON and is never executed, so a file
from a student cannot run code on the grader's machine.

## What is supported

Input: Java Edition schematics using namespaced block names (1.13 and
later). The mapping table is written for 1.21 names. `.litematic` files
with several regions are merged. MCEdit `.schematic` files and other
numeric-ID formats are rejected with a message.

| Kind | Blocks |
|---|---|
| Redstone | dust, repeater (delay, locked), comparator (compare, subtract), redstone torch (floor, wall), lever, buttons (stone, polished blackstone, all woods), redstone lamp, redstone block, target |
| Containers | chest and trapped chest (single, double), barrel, furnace, blast furnace, smoker, hopper, dropper, dispenser, lectern |
| Structure | stone family, deepslate family, bricks, sandstone, planks, 16 colours of wool, concrete, terracotta and stained glass, glass, mineral blocks, glowstone, sea lantern, and the matching slabs |

Not supported, and reported as such: pistons, sticky pistons, observers,
slime and honey blocks. Entities (minecarts, item frames) are ignored.
Anything else that is missing is reported as unmapped.

Stored state is carried over: lever positions, lit torches, repeater delay
and lock, comparator mode and output, dust power. A latch saved while
holding a bit still holds it after loading.

### Coordinates

Minecraft's +Z points south and Luanti's +Z points north, so the build is
mirrored along Z and every facing is adjusted to match. Left and right
swap as a consequence (it matters for double chests). The result looks and
works like the original; a block at Minecraft `(x, y, z)` ends up at
`(x, y, size_z - 1 - z)` inside the schematic.

### ROM

Comparator output depends only on how full each slot is, so craftpipe
preserves the signal strength, not necessarily the items. Common items are
mapped; anything else becomes a filler with the same stack size
(cobblestone for 64, snowball for 16, wooden shovel for 1) and is listed
as a warning. Each container's expected signal is written to the manifest
as `signal`.

## Adding a block

Simple blocks are rows in `src/craftpipe/data/blocks.json`:

```json
"minecraft:calcite": "mcl_amethyst:calcite"
```

Families (colours, woods, slabs) are generated: edit `tools/gen_blocks.py`
and run `python tools/gen_blocks.py`. A block whose node depends on its
state needs a rule in `src/craftpipe/rules.py`. The test
`test_every_plain_target_exists_in_mineclonia` checks each target against
a list of node names dumped from the real game
(`tests/data/mineclonia_registry.json`).

## Clock speed

Mineclonia's redstone runs in ticks of 0.1 s by default (setting
`mcl_redstone_update_tick`), the same length as a Minecraft redstone tick.
Torches and 1-tick repeaters each take one tick, as in Minecraft.

Measured here: a 4-bit ripple-carry adder built from 36 torch NAND stages
gives correct sums for all 512 input combinations and settles within
**48 redstone ticks** (4.8 s) of an input change in the worst case tested.
Size your clock from your own longest path the same way: one tick per
torch or repeater on it, plus margin.

Two things can make a converted CPU slower in real time than in Minecraft:

- Mineclonia limits the redstone work done per server step
  (`mcl_redstone_time_budget`, default 20% of a tick). A large circuit
  with a lot switching at once falls behind real time. Tick order is kept,
  so the circuit still computes the same thing, only later.
- Designs that depend on zero-tick pulses or on Java's update order inside
  a tick are not guaranteed to work. Give them more margin or redesign.

As an operator you can run `/tick freeze`, then `/tick step N`, to advance
the circuit a known number of ticks. That is how the tests here drive it.

## Known differences from Minecraft Java

- **Wooden buttons** stay pressed for 10 redstone ticks (15 in Minecraft).
  Stone buttons are 10 in both. The converter warns when it sees one.
- **Comparator reading a container through a solid block**: Mineclonia
  follows Bedrock Edition here. Java's special case when that block is
  powered at strength 15 is not implemented.
- **Lecterns** keep their page signal; the book's text is not carried over.
- **Furnaces** are placed unlit. One that holds both fuel and something to
  smelt will start smelting and its signal will change, as in Minecraft.
- **Pistons, observers, slime, honey**: not converted (see above).

Checked and found the same as Java: dust connection shapes and the
15-block range, signal going up a tower of top slabs but not down, torch
towers, comparator compare and subtract arithmetic over mixed strengths,
repeater locking, container signal strengths 0 to 15.

Not checked yet: a full CPU against a Minecraft run of the same program.
That needs real builds and a Minecraft baseline.

## Tests

```
.venv/bin/pytest              # unit tests + engine tests (about 5 minutes)
.venv/bin/pytest -m slow      # all 512 adder cases and the settle-time measurement
```

The engine tests start a headless Luanti server with Mineclonia, place
generated circuits through `craftpipe_loader`, flip levers, step redstone
ticks and read lamps and comparators. They are skipped with a message if
`luanti` or Mineclonia is not installed. Test circuits are generated by
`tests/circuits.py` and written as real `.schem` and `.litematic` files.
