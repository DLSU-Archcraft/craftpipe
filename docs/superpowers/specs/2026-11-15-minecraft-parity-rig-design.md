# Minecraft parity rig

Date: 2026-11-15. Status: approved by the user.

## Intent

Study participants build redstone computers, and builds move between
Minecraft and Mineclonia. What matters most is that redstone behaves the
same in both. So far "the same" has only been checked against truth tables
and my reading of Java's rules. This project runs the same circuits in a
real Minecraft server and in Mineclonia and compares the results, so that
every difference is measured, named and kept under test.

It is the first of three pieces agreed in conversation:

1. **This document:** the Minecraft test rig and the difference list.
2. Mineclonia to Minecraft converter with an export command (next).
3. A mod that makes Mineclonia follow Java's redstone rules. Whether to
   build it is the user's decision (it changes what the Luanti arm of the
   study runs) and is deferred until this rig shows how large the gap is.

## What the spike showed

A throwaway spike (not kept) proved the approach on this machine:

- The official Minecraft 1.21.1 server runs headless on Java 21 and is
  ready in about 7 seconds. No game client or account is involved.
- A generated circuit is loaded as a structure template with
  `/place template`. The 152 x 5 x 15 adder loads in one piece.
- `/tick freeze` and `/tick step N` advance the game deterministically;
  `time query gametime` tells when the steps have finished.
- Levers are set with `/setblock`; lamps and dust are read with
  `/execute if block`; all of it over the server's remote console (RCON).
- Lever, dust and lamp gave the same readings as Mineclonia (dust strength
  14 at the second dust). The 4-bit ripple adder gave correct sums for the
  7 cases tried, in 0.3 s.

A second spike, prompted by the design review, found two ways a command
differs from a player's hand:

- **Levers and buttons set by `/setblock` do not notify the block they are
  mounted on.** A lamp touching only that block stayed dark. A player's
  use notifies it. Swapping the mounting block for another solid block
  (stone to cobblestone) produced the missing notification and the lamp
  lit; swapping back after switching off cleared it.
- **A button set to pressed by command never releases.** The release is
  scheduled by the press itself, which a command does not perform.

## Goals

1. Any test circuit can be run in real Minecraft with the same call used
   for Mineclonia, and return results in the same shape.
2. Every existing engine test circuit (orientation, dust, towers, gates,
   comparator grid, adder, latches, ROM containers) is also run in
   Minecraft and compared with the Mineclonia result, output by output.
3. Timing is compared, not only final states: for timing-sensitive
   components the outputs are sampled every redstone tick and the two
   traces compared.
4. Each difference found is recorded in one data file with a plain
   explanation. The tests fail on any difference that is not recorded,
   and fail if a recorded difference stops occurring.
5. The README's "Known differences" section is produced from that file,
   so the list users read is the list the tests enforce.

## Non-goals

- The reverse converter and the export command (piece 2).
- Changing Mineclonia's behaviour (piece 3).
- Driving the Minecraft client, or anything needing the user's account.
- Minecraft versions other than 1.21.1.
- Pistons, observers, slime and honey: still unsupported by the converter,
  so not compared.

## Anti-goals

- A parity test that passes because both sides are compared with the same
  hand-written expectation. The comparison is engine against engine.
- Shipping or committing Mojang's server file.
- A difference being "fixed" by editing the test circuit until it agrees.

## Constraints

- **Licence.** The server jar may not be redistributed. A fetch tool
  downloads it from Mojang into a per-user cache
  (`~/.cache/craftpipe/minecraft/1.21.1/server.jar`) and checks its SHA-1
  against Mojang's published value. Nothing from Mojang goes in the repo.
- **EULA.** Running the server needs `eula=true`. The user has accepted it
  for this machine, so the builder may run the fetch tool with
  `--accept-eula` here. The tool records the acceptance in a marker file
  beside the jar; the harness writes
  `eula=true` only when that marker exists. Anyone else running the tests
  must pass the flag themselves.
- **Skips.** Without the jar, the marker or Java 21, the Minecraft tests
  skip with a message naming the missing piece and the command to fix it.
  They never fail for that reason.
- **Isolation.** The server runs in a temporary directory, bound to
  127.0.0.1 on free ports, offline mode, void world. It does not touch
  Prism Launcher's files.
- Minecraft counts game ticks; one redstone tick is two game ticks. The
  rig's public interface is in redstone ticks, like the Mineclonia one.

## Design

### One interface, two backends

Today `engine.run(circuit, steps)` returns raw Mineclonia node names and
param2 values. Both backends will return a neutral reading per output:

```
{"on": bool,          # lamp lit / component powered
 "power": int | None, # 0-15 for dust and comparators, else None
 "raw": {...}}        # backend-specific detail, for failure messages
```

A step is `{"set": {input: bool}, "wait": redstone_ticks, "read": [names]}`,
plus `"trace": n` to read the outputs after each of the next n redstone
ticks.

- **Mineclonia backend:** the existing harness, with the conversion and
  loader in the path (so parity covers the converter too), and readings
  translated to the neutral shape.
- **Minecraft backend:** writes the circuit as a structure template
  (including block entities, so containers carry their items), starts the
  server, places it, and drives it as the spike did.

### Driving inputs in Minecraft

Decided by the user (2026-11-15): the rig stays on the unmodified Mojang
server.

- **Levers:** set the state by command, then swap the mounting block to
  another solid block and straight back within the same tick. That gives
  the same two notifications a player's pull gives, and leaves the world
  identical. One test pins this: a lamp touching only the mounting block
  must follow the lever.
- **Buttons:** a press is the powered state plus the mounting-block
  notification, and the rig releases it itself after the documented pulse
  length (stone 10, wood 15 redstone ticks). So button *orientation* and
  what a pulse does are compared, but Minecraft's pulse length is taken
  from documentation, not measured. The differences file marks that entry
  as "documented, not measured".

The alternative considered and not chosen was a modded test server
(Fabric with the Carpet mod), whose scripted player performs real presses.

Existing Mineclonia-only tests keep working; they move to the neutral
readings where that is a mechanical change.

### Parity tests

For each existing set of tiles, one Minecraft run and one Mineclonia run
with identical steps; then one test per output asserting the readings
match. New circuits added specifically to look for differences:

- repeater delays 1 to 4, torch, comparator and lamp on/off delay, as
  tick-by-tick traces after a lever flip
- stone and wooden button pulse length
- a clock (torch loop) period, and torch burn-out
- comparator reading a container through a solid block, with and without
  the block powered at 15
- dust beside a lamp, dropper and dispenser, before and after a lever next
  to it is used
- dust on glass, glowstone and slabs; power through a solid block from
  dust, repeater and torch (strong versus weak)
- a locked repeater's timing; a repeater feeding a repeater's side

### Recorded differences

`tests/parity/known_differences.json`: a list of entries, each naming the
circuit and output it applies to, what Minecraft does, what Mineclonia
does, how it was established (measured, or documented), and a
one-paragraph explanation for users.

Only differences between the two games go in this file. A difference that
turns out to be a bug in craftpipe's converter or loader is fixed, with a
test *(my call)*. If such a fix is too large for this project it is
reported to the user as a craftpipe bug, not listed as a game difference.

### Comparing traces

*(My call.)* A lever set by command acts at once in Minecraft, while
Mineclonia handles it in its next redstone tick. Traces are therefore
aligned on a reference probe placed directly beside the input, and what is
compared is each output's delay after that reference. If the two games
differ in how soon the reference itself reacts, that is recorded once as
its own entry, not repeated for every circuit. The parity tests consult
it: a recorded difference must occur exactly as recorded; anything else
must match. A small tool renders the entries into the README section.

### Tooling

`python tools/fetch_minecraft_server.py [--accept-eula]` downloads and
verifies the jar. The README's test section explains it.

## Left to the builder

- RCON client details, port selection, server.properties contents.
- How many circuits share one server run (start-up is about 7 s).
- How to read dust power efficiently (16 `execute if block` probes worked
  in the spike; a cheaper way is welcome).
- Whether structure placement leaves any component uninitialised, and the
  settle time to allow after placing. The spike used 20 redstone ticks.
- Exact layouts of the new difference-hunting circuits, valid by Java's
  rules.
- File layout under `tests/`.

## Order of work

1. Fetch tool, Minecraft backend, neutral readings; lever, dust and lamp
   passing on both backends.
2. Existing tile sets compared on both backends; record what differs.
3. Trace support and the new difference-hunting circuits; record what
   differs.
4. Differences file enforced by the tests; README section generated from
   it; a short summary of findings for the user, since it feeds the
   decision on piece 3.
