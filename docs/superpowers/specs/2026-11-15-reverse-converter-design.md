# Mineclonia to Minecraft converter

Date: 2026-11-15. Status: approved by the user.

## Intent

Study participants build redstone computers in Mineclonia worlds (running
`craftpipe_java_rules`). Those builds must be openable in Minecraft Java
1.21.1 and behave the same there.

## Design

- **Export.** `craftpipe_loader` gains `/craftpipe_pos1`, `/craftpipe_pos2`
  and `/craftpipe_export <name>` (privilege `server`; staff export
  participants' builds, as the user confirmed). A WorldEdit selection is
  used when no positions were set. It writes `<world>/schems/<name>.mts`
  and `<name>.craftpipe.json` (container contents with each stack's
  maximum size, lectern pages, a hash of the `.mts`). Lua:
  `craftpipe.export(pos1, pos2, name)`.
- **Convert.** `craftpipe to-minecraft build.mts [-o out.litematic|.schem]`
  and `craftpipe.to_minecraft(...)`. Output is for Java 1.21.1.
- **Mapping.** The reverse of the forward table. For blocks whose node
  depends on state, the reverse is derived by enumerating the forward
  rules, so the two directions cannot drift apart. Dust is translated
  directly (connections, climbing sides, power, dots). Comparator output
  goes back into the block entity. A few nodes that only exist at run
  time (lit furnace, open barrel, triggered trapped chest) map to their
  resting block.
- **Items.** Reverse of the item table; an item with no Minecraft
  equivalent becomes a filler of the same stack size, with a warning.
- **Unmapped nodes** stop the conversion and are listed with count and
  positions; `--allow-unmapped` substitutes bedrock and warns.
- A `.mts` without a manifest (for example saved by WorldEdit) converts
  with a warning that containers will be empty.

## Approaches

- **Derive the reverse from the forward rules (chosen)**: one source of
  truth; anything the forward direction cannot produce is reported.
- Hand-written reverse rules: more control, but two tables to keep in
  step. Rejected.
- Export straight to a Minecraft file from Lua: no NBT or compression
  tooling there, and it would duplicate the mapping. Rejected.

## Verification

- Every test circuit converted to Mineclonia and back gives a build whose
  forward conversion is identical to the first one (blocks, orientation,
  containers).
- In the engines: each suite is loaded into Mineclonia with the Java-rules
  mod, exported with the new command, converted back, and run in the real
  Minecraft server. Results must equal the original circuit's Minecraft
  run, finals and tick-by-tick waveforms.

## Non-goals

Participants exporting their own builds; entities; blocks the forward
converter does not support; Minecraft versions other than 1.21.1.
