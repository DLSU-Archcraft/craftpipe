"""Comparator signal strength of a container (same formula in Minecraft
and Mineclonia)."""

from __future__ import annotations

from fractions import Fraction
from typing import Iterable


def container_signal(slots: int, stacks: Iterable[tuple[int, int]]) -> int:
    """``stacks`` holds (count, max_stack_size) for each occupied slot."""
    fullness = Fraction(0)
    any_item = False
    for count, max_stack in stacks:
        if count <= 0:
            continue
        any_item = True
        fullness += Fraction(min(count, max_stack), max_stack)
    if not any_item or slots <= 0:
        return 0
    return min(15, int(1 + 14 * fullness / slots))


def lectern_signal(page: int, pages: int) -> int:
    """``page`` is 1-based."""
    if pages <= 1:
        return 15
    return int(14 * (page - 1) / (pages - 1) + 1)
