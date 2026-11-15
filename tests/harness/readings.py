"""Backend-neutral readings, so Minecraft and Mineclonia results compare."""

from __future__ import annotations

from typing import NamedTuple, Optional


class Reading(NamedTuple):
    on: bool                    # lamp lit / component powered / dust carrying power / hopper locked
    power: Optional[int]        # 0-15 for dust and comparators, otherwise None


def luanti_reading(raw: dict) -> Reading:
    """Translate what the Luanti test driver reports for one node."""
    name, param2 = raw["name"], raw["param2"]
    if name == "mcl_redstone:redstone" or name.startswith("mcl_redstone:wire_"):
        power = param2 & 15
        return Reading(power > 0, power)
    if name.startswith("mcl_comparators:comparator_"):
        return Reading("_on_" in name, param2 >> 2)
    if name.startswith("mcl_hoppers:"):
        return Reading(name.endswith("_disabled"), None)      # "on" = locked by redstone
    return Reading(bool(raw["on"]), None)
