"""Named rules for blocks whose Mineclonia node depends on block state.

A rule receives the block state *after* the Z mirror, plus any extra keys
from its row in blocks.json, and returns a Node, or None when the state has
no equivalent.

Direction names in a mirrored state keep Minecraft's axis convention but
apply to Luanti coordinates: north = -Z, south = +Z, east = +X, west = -X.
(The mirror already swapped north and south, which is what makes this
hold.) FACEDIR and WALLMOUNTED below translate those names into Luanti's
param2 encodings.
"""

from __future__ import annotations

from typing import Callable, NamedTuple, Optional

from .grid import BlockState


class Node(NamedTuple):
    name: str
    param2: int = 0


Rule = Callable[..., Optional[Node]]
RULES: dict[str, Rule] = {}
# rule name -> the block-state properties it reads, with every value each can take.
DOMAINS: dict[str, dict[str, tuple[str, ...]]] = {}

_H4 = ("north", "south", "east", "west")
_TF = ("true", "false")
_FACE = ("floor", "wall", "ceiling")


def rule(name: str, **domain: tuple[str, ...]):
    """Register a rule. ``domain`` lists the properties the rule reads, so
    that every node name it can produce can be enumerated (see
    ``possible_nodes``); the loader only accepts schematics made of those."""
    def register(fn: Rule) -> Rule:
        RULES[name] = fn
        DOMAINS[name] = domain
        return fn
    return register


def possible_nodes(name: str, **extra) -> set[str]:
    """Every node name rule ``name`` can return."""
    import itertools
    domain = DOMAINS[name]
    keys = list(domain)
    out = set()
    for values in itertools.product(*(domain[k] for k in keys)):
        node = RULES[name](BlockState("minecraft:x", tuple(zip(keys, values))), **extra)
        if node is not None:
            out.add(node.name)
    return out


@rule("slab", type=("bottom", "top", "double"))
def slab(state: BlockState, base: str) -> Node:
    suffix = {"top": "_top", "double": "_double"}.get(state.get("type", "bottom"), "")
    return Node(base + suffix)


# Luanti facedir (and 4dir) value whose direction is the named one.
FACEDIR = {"south": 0, "east": 1, "north": 2, "west": 3}
# Luanti wallmounted value for a node attached to the block in that direction.
WALLMOUNTED = {"up": 0, "down": 1, "east": 2, "west": 3, "south": 4, "north": 5}
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east",
            "up": "down", "down": "up"}


def _on(state: BlockState, key: str = "powered") -> bool:
    return state.get(key, "false") == "true"


# Mineclonia names each dust shape mcl_redstone:wire_XY. The low hex digit
# has one bit per horizontal connection; the high digit marks connections
# that climb onto the neighbouring block.
DUST_BITS = {"north": 0x1, "west": 0x2, "south": 0x4, "east": 0x8}
_DUST_SIDE = ("none", "side", "up")


def dust_mask(state: BlockState) -> int:
    """Horizontal connections of a (mirrored) redstone_wire state."""
    mask = 0
    for side, bit in DUST_BITS.items():
        if state.get(side, "none") != "none":
            mask |= bit
    # A single connection is drawn, and behaves, as a straight line.
    return {0x1: 0x5, 0x4: 0x5, 0x2: 0xA, 0x8: 0xA}.get(mask, mask)


def dust_name(mask: int) -> str:
    return "mcl_redstone:redstone" if mask == 0 else f"mcl_redstone:wire_{mask:02x}"


@rule("dust", north=_DUST_SIDE, east=_DUST_SIDE, south=_DUST_SIDE, west=_DUST_SIDE)
def dust(state: BlockState) -> Node:
    # Mineclonia decides dust connections by its own rules, which differ
    # from Java's (it connects dust to lamps and droppers, and makes an
    # unconnected dust a dot). The shape saved by Minecraft is what the
    # circuit was built around, so it is written out as is; the loader
    # only lets Mineclonia add the climbing bits. Power goes in both
    # nibbles of param2.
    try:
        power = max(0, min(15, int(state.get("power", "0"))))
    except ValueError:
        power = 0
    return Node(dust_name(dust_mask(state)), power * 17)


@rule("lamp", lit=_TF)
def lamp(state: BlockState) -> Node:
    return Node("mcl_redstone_lamp:lamp_on" if _on(state, "lit") else "mcl_redstone_lamp:lamp_off")


@rule("lever", face=_FACE, facing=_H4, powered=_TF)
def lever(state: BlockState) -> Optional[Node]:
    # Mineclonia levers use facedir; facedir_to_dir(param2) points at the
    # block the lever is attached to (values from mcl_lever's on_place).
    name = "mcl_lever:lever_on" if _on(state) else "mcl_lever:lever_off"
    face, facing = state.get("face", "wall"), state.get("facing", "north")
    if facing not in FACEDIR:
        return None
    along_x = facing in ("east", "west")
    if face == "floor":
        return Node(name, 13 if along_x else 10)
    if face == "ceiling":
        return Node(name, 15 if along_x else 8)
    return Node(name, FACEDIR[OPPOSITE[facing]])


@rule("repeater", facing=_H4, powered=_TF, locked=_TF, delay=("1", "2", "3", "4"))
def repeater(state: BlockState) -> Optional[Node]:
    # Minecraft's `facing` names the input side; Mineclonia's 4dir param2
    # is the output direction. Locked repeaters keep their delay in param2.
    facing = state.get("facing", "north")
    if facing not in FACEDIR:
        return None
    direction = FACEDIR[OPPOSITE[facing]]
    power = "on" if _on(state) else "off"
    try:
        delay = max(1, min(4, int(state.get("delay", "1"))))
    except ValueError:
        delay = 1
    if state.get("locked", "false") == "true":
        return Node(f"mcl_repeaters:repeater_{power}_locked", delay * 4 + direction)
    return Node(f"mcl_repeaters:repeater_{power}_{delay}", direction)


@rule("comparator", facing=_H4, powered=_TF, mode=("compare", "subtract"))
def comparator(state: BlockState) -> Optional[Node]:
    # param2 = 4 * output strength + output direction. The strength lives
    # in the block entity; the mapper adds it (see mapper.map_grid).
    facing = state.get("facing", "north")
    if facing not in FACEDIR:
        return None
    power = "on" if _on(state) else "off"
    mode = "sub" if state.get("mode", "compare") == "subtract" else "comp"
    return Node(f"mcl_comparators:comparator_{power}_{mode}", FACEDIR[OPPOSITE[facing]])


@rule("torch", lit=_TF)
def torch(state: BlockState) -> Node:
    lit = "on" if _on(state, "lit") else "off"
    return Node(f"mcl_redstone_torch:redstone_torch_{lit}", WALLMOUNTED["down"])


@rule("wall_torch", facing=_H4, lit=_TF)
def wall_torch(state: BlockState) -> Optional[Node]:
    # `facing` is the way the torch points; it hangs on the block behind it.
    facing = state.get("facing", "north")
    if facing not in FACEDIR:
        return None
    lit = "on" if _on(state, "lit") else "off"
    return Node(f"mcl_redstone_torch:redstone_torch_{lit}_wall", WALLMOUNTED[OPPOSITE[facing]])


@rule("button", face=_FACE, facing=_H4, powered=_TF)
def button(state: BlockState, material: str) -> Optional[Node]:
    name = f"mcl_buttons:button_{material}_{'on' if _on(state) else 'off'}"
    face, facing = state.get("face", "wall"), state.get("facing", "north")
    if face == "floor":
        return Node(name, WALLMOUNTED["down"])
    if face == "ceiling":
        return Node(name, WALLMOUNTED["up"])
    if facing not in FACEDIR:
        return None
    return Node(name, WALLMOUNTED[OPPOSITE[facing]])


def _front(state: BlockState) -> Optional[int]:
    """facedir for a node whose front faces the state's `facing`."""
    facing = state.get("facing", "north")
    return FACEDIR[OPPOSITE[facing]] if facing in FACEDIR else None


@rule("chest", facing=_H4, type=("single", "left", "right"))
def chest(state: BlockState, base: str) -> Optional[Node]:
    # `type` was already swapped by the Z mirror, so left/right line up
    # with Mineclonia's own left and right halves.
    param2 = _front(state)
    if param2 is None:
        return None
    suffix = {"left": "_left", "right": "_right"}.get(state.get("type", "single"), "_small")
    return Node(base + suffix, param2)


@rule("front_facing", facing=_H4 + ("up", "down"))
def front_facing(state: BlockState, node: str) -> Node:
    """Furnaces, barrels: horizontal facing only matters for looks."""
    param2 = _front(state)
    return Node(node, 0 if param2 is None else param2)


@rule("hopper", facing=_H4 + ("down",), enabled=_TF)
def hopper(state: BlockState) -> Optional[Node]:
    disabled = "_disabled" if state.get("enabled", "true") == "false" else ""
    facing = state.get("facing", "down")
    if facing == "down":
        return Node("mcl_hoppers:hopper" + disabled)
    if facing not in FACEDIR:
        return None
    # mcl_hoppers: output = fourdir_to_dir((param2 + 3) % 4)
    return Node("mcl_hoppers:hopper_side" + disabled, (FACEDIR[facing] + 1) % 4)


@rule("dropper", facing=_H4 + ("up", "down"))
def dropper(state: BlockState, base: str) -> Optional[Node]:
    facing = state.get("facing", "north")
    if facing in ("up", "down"):
        return Node(f"{base}_{facing}")
    if facing not in FACEDIR:
        return None
    return Node(base, FACEDIR[OPPOSITE[facing]])


@rule("lectern", facing=_H4, has_book=_TF)
def lectern(state: BlockState) -> Node:
    name = "mcl_lectern:lectern_with_book" if state.get("has_book") == "true" else "mcl_lectern:lectern"
    param2 = _front(state)
    return Node(name, 0 if param2 is None else param2)
