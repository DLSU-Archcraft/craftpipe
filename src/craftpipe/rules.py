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


def rule(name: str):
    def register(fn: Rule) -> Rule:
        RULES[name] = fn
        return fn
    return register


@rule("slab")
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


@rule("dust")
def dust(state: BlockState) -> Node:
    # The loader's on_construct pass picks the connected shape; Mineclonia
    # keeps the power level in both nibbles of param2.
    try:
        power = max(0, min(15, int(state.get("power", "0"))))
    except ValueError:
        power = 0
    return Node("mcl_redstone:redstone", power * 17)


@rule("lamp")
def lamp(state: BlockState) -> Node:
    return Node("mcl_redstone_lamp:lamp_on" if _on(state, "lit") else "mcl_redstone_lamp:lamp_off")


@rule("lever")
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
