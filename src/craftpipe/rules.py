"""Named rules for blocks whose Mineclonia node depends on block state.

A rule receives the block state *after* the Z mirror (so ``facing`` is
already in Luanti's orientation) plus any extra keys from its row in
blocks.json, and returns a Node, or None when the state has no equivalent.
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
