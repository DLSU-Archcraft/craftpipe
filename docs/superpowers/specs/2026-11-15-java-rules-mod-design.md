# craftpipe_java_rules: Mineclonia redstone that follows Java

Date: 2026-11-15. Status: approved by the user.

## Intent

Study participants build redstone computers, some directly in Mineclonia.
The parity rig showed Mineclonia and Minecraft Java 1.21.1 agree on
everything tested except four things, two of which change what a circuit
computes. This mod removes the differences that can be removed, so that a
participant building in Mineclonia is building under Java's rules.

## What it changes

1. **Dust connects only to what Java connects it to**: other dust and
   signal sources (levers, buttons, torches, redstone blocks, pressure
   plates, comparators, repeater fronts and backs, observers, targets,
   trapped chests, lecterns, daylight detectors, detector rails).
   Everything else (lamps, hoppers, droppers, dispensers, note blocks,
   doors, gates, TNT, pistons ...) loses its dust connection.
2. **An unconnected dust is a cross**, unless a player right-clicked it
   into a dot (remembered in the node's metadata). Needed because of 1:
   stock Mineclonia would make a lone dust beside a lamp a dot.
3. **A comparator reading through a solid block powered at 15 outputs 15.**
4. **Lamps light in the tick they are powered.**

Not changed: player input landing on the next 0.1 s redstone tick.

## Approaches

- **A separate mod (chosen).** Overrides node definitions and wraps three
  internal Mineclonia functions at load time. Can be added to or removed
  from any world; needs re-checking on each Mineclonia release, which the
  parity rig does.
- **Patching Mineclonia.** Simpler code, but a fork to maintain. Rejected.
- **Design rules only, no mod.** Workable (two rules), but relies on every
  participant following them. The user chose the mod.

## Verification

The parity rig gains a second Mineclonia mode with the mod loaded.

- Recorded differences are marked with what the mod does to them. With
  the mod, the comparator, dust-beside-lamp/hopper and lamp-delay entries
  must not occur; input latency must still occur.
- "Built natively": after loading, every dust is re-shaped by the game's
  own rules (no pinning by the loader), as when a participant builds in
  Mineclonia. With the mod, every dust in every suite must end up with
  the same horizontal connections Minecraft saved, and all suites must
  behave as in real Minecraft.
- Stock Mineclonia stays under test unchanged.

## Risks

Change 2 wraps `mcl_redstone._connect_with_wires`,
`mcl_redstone._update_opaque_connections` and the dust nodes'
`on_construct`/`after_destruct`/`on_rightclick`. A Mineclonia update that
renames these breaks it; the mod checks they exist at load and refuses to
start with a clear message if not.

## Left to the builder

Exact node-name allow-list (from the installed game), how the comparator
override recognises "a container is directly behind" versus "a plain solid
block", metadata key name, README wording.
