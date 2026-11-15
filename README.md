# craftpipe

Converts redstone builds between Minecraft Java and Mineclonia (Luanti),
in both directions, so that computer-architecture builds (adders, ALUs,
ROM, CPUs) made in one can be run and graded in the other. It also
measures where the two games' redstone differs, and ships a mod that
makes Mineclonia follow Java where it does.

Minecraft schematics (`.litematic`, Sponge `.schem`) become Mineclonia
schematics (`.mts`), and exported Mineclonia regions become Minecraft
schematics.

A conversion produces two files:

- `build.mts`: the blocks.
- `build.craftpipe.json`: a manifest with what `.mts` cannot hold
  (container contents for comparator ROM, lectern pages). It records a
  hash of the `.mts`, so the two files must come from the same conversion.

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
   (the same folder WorldEdit uses). The base name may contain only
   letters, digits, `_` and `-`; the converter warns if it does not.
3. In the game, with the `server` privilege, stand where the build's
   lowest corner should go and run:

   ```
   /craftpipe_place build
   ```

From Lua: `craftpipe.place(pos, "build")` (area must already be generated)
or `craftpipe.place_async(pos, "build", callback)`.

### Why not WorldEdit's `//mtschemplace`?

It will place the blocks, but pasting a schematic skips each node's setup
step: containers have no inventory, ROM is empty, and dust that climbs
onto a block is not connected. `craftpipe_loader` runs that setup, lets
Mineclonia initialise the redstone, restores the dust shapes Minecraft
saved, and fills the containers from the manifest.

### Loading files from students

The loader treats both files as untrusted:

- The manifest is parsed as JSON and never executed.
- A schematic is refused if it contains any node the converter cannot
  produce (the list is `mod/craftpipe_loader/allowed_nodes.lua`), so a
  hand-made `.mts` cannot bring in a command block or similar.
- The manifest can only fill the inventories of container nodes and set
  the page of a lectern. It cannot write any other metadata.
- A manifest that does not match the `.mts` (by hash) is refused.

Re-converting a build and placing it again works without restarting the
server; the loader does not use Luanti's by-name schematic cache.

## Convert a Mineclonia build to Minecraft

Builds made (or changed) in a Mineclonia world can go back to Minecraft
Java 1.21.1.

1. In the game, with the `server` privilege, mark the region and export:

   ```
   /craftpipe_pos1          (standing at one corner)
   /craftpipe_pos2          (standing at the opposite corner)
   /craftpipe_export build
   ```

   If you use WorldEdit, its selection is used when no corners were set.
   This writes `build.mts` and `build.craftpipe.json` into
   `<world>/schems/`. The second file carries what `.mts` cannot:
   container contents and lectern pages. An existing name is not
   replaced unless you add the word `overwrite`, and a region that has
   not been fully generated is refused.

2. On the command line:

   ```
   $ craftpipe to-minecraft build.mts
   build.litematic: 3301 blocks, Minecraft Java 1.21.1
   ```

   Use `-o build.schem` for a WorldEdit schematic. As a library:
   `craftpipe.to_minecraft("build.mts")`.

What carries over: the same blocks the forward direction supports, with
their orientation; lever positions, torches, repeater delay and lock,
comparator mode and output; every dust with its exact connections, power
and deliberate dots; container contents. An item with no Minecraft
equivalent becomes a filler of the same stack size (cobblestone, snowball
or wooden shovel), with a warning, so comparator signals are kept.

A node with no Minecraft 1.21.1 equivalent stops the conversion and is
listed with its count and positions, as in the other direction. That
includes blocks Mineclonia has but Minecraft 1.21.1 does not yet (pale
oak), and components turned to an orientation the converter does not
recognise. `--allow-unmapped` puts bedrock there instead.

Things to know:

- **Use the Java-rules mod in the world.** Without it, Mineclonia shapes
  dust by its own rules (towards lamps and hoppers, dots for unconnected
  dust), and the export faithfully carries those shapes to Minecraft,
  where the circuit may then behave differently.
- A `.mts` saved by other means (WorldEdit's `//mtschemcreate`) converts
  too, but has no manifest, so containers come out empty; the converter
  says so.
- Mineclonia does not keep a facing for levers and buttons on floors and
  ceilings, so those come back with a default one; upright barrels come
  back lying on their side. Neither affects behaviour.
- A button that was pressed at the moment of export is written released,
  with a warning: Minecraft cannot release a button loaded as pressed.
- Lit furnaces and open barrels come back unlit and closed.
- Lectern books come back with the right number of pages and the right
  page open, but blank.

This direction is tested in the real engines. Six sets of test circuits
are loaded into a Mineclonia world with the Java-rules mod, exported,
converted back and run in a real Minecraft server, where every output
must match the original circuit's (and, for the timing circuits, every
tick). A structure placed by hand in Mineclonia, never having been in
Minecraft, is also exported, converted and checked there.

What is not tested: the chat commands themselves (the tests call the
function behind them), and opening the files in Litematica or WorldEdit.
The files follow the published formats and the test server accepts their
contents, but neither tool has been tried.

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

### Redstone dust shapes

Minecraft saves which of its four sides each dust connects to, and a
circuit depends on that: a lone "cross" powers all four neighbours, a
"dot" none, a line only its two ends. Mineclonia works these out by its
own rules, which differ (it connects dust to lamps, droppers and
dispensers, and turns an unconnected dust into a dot). craftpipe therefore
writes each dust with the connections Minecraft saved, and the loader
keeps them that way. Files from before Java 1.16 store an unconnected dust
with no sides; those are treated as crosses, as they behaved then.

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
as a warning. Stack sizes come from a table in
`src/craftpipe/data/items.json` and from the item's own
`max_stack_size` component when it has one. An item the table does not
know is assumed to stack to 64, with a warning that says so: check those,
because a wrong stack size means a wrong signal. Each container's expected
signal is written to the manifest as `signal`.

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

Component delays were measured tick by tick in real Minecraft 1.21.1 and
in Mineclonia, and are the same in both:

| Component | Delay (redstone ticks) |
|---|---|
| Repeater, set to 1 / 2 / 3 / 4 | 1 / 2 / 3 / 4 |
| Four 4-tick repeaters in a row | 16 |
| Redstone torch | 1 |
| Comparator | 1 |
| Locked repeater, after the lock is released | same in both |
| Stone button pulse / wooden button pulse | 10 / 15 |
| Torch-and-repeater clock (4-tick repeater) | switches every 5 |
| Redstone lamp turning off | 2 |

So a clock that is safe in Minecraft needs no extra padding in Mineclonia
because of component timing. For reference, a 4-bit ripple-carry adder
built from 36 torch NAND stages gives the same sums in both games for all
512 input combinations. In Mineclonia it settles within 48 redstone ticks
(the settle time was not measured separately in Minecraft).

Two things can still make a converted CPU slower in real time:

- Mineclonia limits the redstone work done per server step
  (`mcl_redstone_time_budget`, default 20% of a tick). A large circuit
  with a lot switching at once falls behind real time. Tick order is kept,
  so the circuit still computes the same thing, only later.
- Designs that depend on zero-tick pulses or on Java's update order inside
  a tick are not covered by these tests. Give them more margin or redesign.

As an operator you can run `/tick freeze`, then `/tick step N`, to advance
the circuit a known number of ticks. That is how the tests here drive it.

## Making Mineclonia follow Java: `craftpipe_java_rules`

Stock Mineclonia differs from Minecraft Java in a few redstone rules (the
list is in the next section). The mod in `mod/craftpipe_java_rules`
removes the ones that can be removed:

1. Dust connects only to what Java connects it to: other dust and signal
   sources (levers, buttons, torches whether lit or not, redstone blocks,
   pressure plates, comparators, repeater fronts and backs, an observer's
   output, targets, trapped chests, lecterns, daylight detectors). Lamps,
   hoppers, droppers, dispensers, note blocks, doors, gates, TNT and
   pistons no longer pull dust towards them.
2. An unconnected dust is a cross, as in Java. Right-click it to make it
   a dot; it stays a dot until something connects to it. Changing between
   the two updates what the dust powers straight away.
3. A comparator reading a container through a solid block outputs 15 when
   that block is powered at 15.
4. A lamp lights in the tick it is powered.

Install it like the loader: copy `mod/craftpipe_java_rules` into the
world's `worldmods/` folder (or your Luanti `mods/` folder, enabled for
the world). It does not need the loader, and the loader does not need it.
For a study where builds must behave the same in both games, load it in
every Luanti world participants build in.

With the mod, dust laid by hand in Mineclonia connects the way real
Minecraft connects it, for the blocks this converter supports. That is
tested: every dust in every test circuit is shaped by Mineclonia itself
and compared with what a real Minecraft server decided for the same
circuit, including dust beside 18 kinds of block and beside unlit torches.

Not covered by the mod:

- Java connects dust to detector rails, jukeboxes and lightning rods;
  Mineclonia does not, with or without the mod.
- A lever or button still takes effect at Mineclonia's next 0.1 s
  redstone tick.
- Dust already in a world keeps its shape until something next to it
  changes. Add the mod before participants start building, not partway
  through.

The mod overrides Mineclonia's node definitions and wraps three of its
internal functions when the game loads; it changes no Mineclonia files and
refuses to load, with a message, on a Mineclonia version that lacks what
it needs. It was written against release 35899. After a Mineclonia update,
run the parity tests before relying on it.

## Differences between Minecraft and Mineclonia

The same generated circuits are run in a real Minecraft 1.21.1 server and
in Mineclonia (stock, and again with `craftpipe_java_rules`), and compared
output by output and tick by tick. Each item says whether the mod removes
it. This list
is generated from `tests/parity/known_differences.json`. For the circuits
tested, the tests fail if the games differ in any way not listed here, and
also if a listed difference stops occurring. A behaviour no test circuit
exercises can still differ.

<!-- differences:start (generated by tools/render_differences.py) -->
- **A lever or button takes effect at the next 0.1 s redstone tick (Minecraft: the next 0.05 s game tick).** In Minecraft a lever or button acts within one game tick (0.05 s) of being used. In Mineclonia it acts at the next redstone tick (0.1 s), so a person's input can land up to 0.1 s later. The tests see this as 0 versus 1 tick because they step a frozen world; in live play the gap is a small fraction of a second and varies. Everything downstream then runs with the same delays in both games, so this shifts when a circuit starts reacting to a person, not what it computes. *Still present with `craftpipe_java_rules`.*
- **Redstone lamps light one tick later.** A lamp lights in the same tick it is powered in Minecraft, and one redstone tick later in Mineclonia. Both games turn a lamp off two ticks after it loses power. Lamps are outputs only, so this affects what a display looks like for a tenth of a second, not any signal. *Removed by `craftpipe_java_rules`.*
- **Comparator reading a container through a solid block that is powered at full strength.** A comparator can read a container through one solid block. If that block is itself powered at full strength (15), whether by a lever on it, a repeater, or dust carrying 15 that points into it, Minecraft Java outputs 15 and ignores the container; Mineclonia keeps outputting the container's level. With the block unpowered, or powered by dust carrying 14 or less, both games output the container's level. Avoid powering the block between a container and its comparator. *Removed by `craftpipe_java_rules`.*
- **Dust next to a lever or button can start powering a lamp or hopper beside it.** Mineclonia connects redstone dust to lamps and hoppers (and, from its source, to droppers, dispensers and note blocks); Minecraft Java does not. craftpipe places dust with the connections Minecraft saved, so a wire running past a lamp or hopper leaves it alone. But using a lever or button makes Mineclonia re-shape the dust directly beside that lever or button by its own rules: if that dust also touches such a block it was not pointing at, it connects to it and powers it. A lamp lights; a hopper locks and stops moving items, which changes what an item-based circuit does. The same re-shaping happens if someone edits the build in Mineclonia by placing or removing dust, a redstone component or a solid block next to dust. The converter warns, with positions, when a build contains the lever or button arrangement. Keep one block of dust between a lever or button and anything the wire should pass without powering. *Removed by `craftpipe_java_rules`.*
<!-- differences:end -->

Compared and found identical in both games: every directional component
in every orientation; dust shapes, the 15-block range, a lone cross
powering its neighbours and a lone dot not; a wire passing a lamp without
lighting it; signal going up a tower of top slabs but not down; torch
towers; dust carried over glass and glowstone; weak versus strong power
through a block; NAND, AND, OR and XOR torch gates; comparator compare and
subtract arithmetic over mixed strengths; an RS torch latch and a
locked-repeater latch, including a stored bit surviving a load; the 4-bit
adder; container signal strengths 0 to 15 for chests, double chests,
barrels, furnaces, hoppers, droppers, dispensers and lecterns; and the
timings in the table above.

How the Minecraft side is driven matters for reading these results. The
test server is unmodified and has no player, so levers are set by command
(with the extra block update a player's hand causes), and buttons are
released by the test rig after Minecraft's documented pulse length. The
button pulse lengths in the table are therefore measured in Mineclonia and
taken from documentation for Minecraft.

### Converter limitations

These come from the converter, not from the games:

- **Lecterns** keep their page signal; the book's text is not carried over.
- **Furnaces** are placed unlit. One that holds both fuel and something to
  smelt will start smelting and its signal will change, as in Minecraft.
- **Pistons, observers, slime, honey**: not converted (see above).

### Not checked yet

- A full CPU against a Minecraft run of the same program. That needs real
  builds.
- Files saved by Litematica or WorldEdit themselves. Every test input is
  generated by this repository's own writers, following the published
  formats and Java's dust-connection rules.
- Edge-triggered flip-flops. The memory cells tested are level-sensitive.
- How quickly a torch burns out. Both games end with the torch burnt out
  and it stays out (tested); the number of flickers before that is not
  under test.
- Droppers, dispensers and note blocks beside dust. Mineclonia's source
  connects dust to them as it does to lamps and hoppers; only the lamp
  and hopper cases are measured.
- Minecraft versions other than 1.21.1.

## Tests

```
.venv/bin/pytest              # everything that can run here (about 10 minutes)
.venv/bin/pytest -m slow      # all 512 adder cases in both games, settle-time measurement
```

There are three layers, each skipped with a message when its engine is
missing:

- **Unit tests** need nothing but Python.
- **Engine tests** (`tests/engine`) start a headless Luanti server with
  Mineclonia, place generated circuits through `craftpipe_loader`, flip
  levers, step redstone ticks and read lamps and comparators. They need
  `luanti` and the Mineclonia game.
- **Parity tests** (`tests/parity`) run the same circuits in a real
  Minecraft server as well and compare the two. They need Java 21 and the
  official server file:

  ```
  python tools/fetch_minecraft_server.py --accept-eula
  ```

  This downloads the Minecraft 1.21.1 server from Mojang into
  `~/.cache/craftpipe/`, checks it against Mojang's checksum, and records
  that you accept the [Minecraft EULA](https://aka.ms/MinecraftEULA),
  which running the server requires. The file is never added to this
  repository. No Minecraft account or game client is involved.

Test circuits are generated by `tests/circuits.py` and `tests/suites.py`.
When the games disagree on something new, the parity tests fail and name
the circuit; record it in `tests/parity/known_differences.json` only if it
is a real difference between the games, then run
`python tools/render_differences.py` to update this README.
