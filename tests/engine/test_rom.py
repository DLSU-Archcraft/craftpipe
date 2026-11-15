"""Containers used as comparator ROM give the same signal after conversion."""

import json
import math

import pytest

from craftpipe import nbt
from circuits import Circuit, bench


def stacks(item, total, size=64, first_slot=0):
    out, slot = [], first_slot
    while total > 0:
        n = min(size, total)
        out.append({"Slot": nbt.Byte(slot), "id": item, "count": nbt.Int(n)})
        total -= n
        slot += 1
    return out


def reader(block_state, ident, items=None, extra=None):
    """container -> comparator -> dust; the comparator faces away from it."""
    c = Circuit((3, 2, 1))
    c.block(0, 1, 0, block_state)
    c.grid.block_entities[(0, 1, 0)] = {"id": ident, **({"Items": items} if items is not None else {}),
                                        **(extra or {})}
    c.block(1, 1, 0, "minecraft:comparator[facing=west,mode=compare,powered=false]")
    c.probe("cmp", (1, 1, 0)).dust((2, 1, 0)).probe("out", (2, 1, 0))
    return c


def chest_with_signal(n):
    """Fewest redstone items that make a 27-slot chest read n."""
    total = 1 if n == 1 else math.ceil((n - 1) * 27 * 64 / 14)
    return reader("minecraft:chest[facing=north,type=single,waterlogged=false]", "minecraft:chest",
                  stacks("minecraft:redstone", total))


def double_chest():
    c = Circuit((4, 2, 3))
    # North-facing pair: the LEFT half's partner is to its east.
    c.block(1, 1, 1, "minecraft:chest[facing=north,type=left,waterlogged=false]")
    c.block(2, 1, 1, "minecraft:chest[facing=north,type=right,waterlogged=false]")
    c.grid.block_entities[(1, 1, 1)] = {"id": "minecraft:chest",
                                        "Items": stacks("minecraft:redstone", 27 * 64)}
    c.grid.block_entities[(2, 1, 1)] = {"id": "minecraft:chest", "Items": []}
    # one comparator behind each half, reading south
    for name, x in (("full", 1), ("empty", 2)):
        c.block(x, 1, 2, "minecraft:comparator[facing=north,mode=compare,powered=false]")
        c.probe(name, (x, 1, 2))
    return c


TILES = {f"chest{n}": (chest_with_signal(n), n) for n in range(1, 16)}
TILES.update({
    "empty": (reader("minecraft:chest[facing=north,type=single]", "minecraft:chest", []), 0),
    "barrel": (reader("minecraft:barrel[facing=up,open=false]", "minecraft:barrel",
                      stacks("minecraft:redstone", 13 * 64 + 32)), 8),
    "furnace": (reader("minecraft:furnace[facing=north,lit=false]", "minecraft:furnace",
                       stacks("minecraft:redstone", 64)), 5),
    "hopper": (reader("minecraft:hopper[enabled=true,facing=down]", "minecraft:hopper",
                      stacks("minecraft:redstone", 128)), 6),
    "dropper": (reader("minecraft:dropper[facing=up,triggered=false]", "minecraft:dropper",
                       stacks("minecraft:redstone", 3 * 64)), 5),
    "dispenser": (reader("minecraft:dispenser[facing=east,triggered=false]", "minecraft:dispenser",
                         stacks("minecraft:redstone", 9 * 64)), 15),
    "pearls": (reader("minecraft:chest[facing=north,type=single]", "minecraft:chest",
                      stacks("minecraft:ender_pearl", 80, size=16)), 3),
    "unknown_item": (reader("minecraft:chest[facing=north,type=single]", "minecraft:chest",
                            stacks("minecraft:nautilus_shell", 640)), 6),
    "swords": (reader("minecraft:chest[facing=north,type=single]", "minecraft:chest",
                      stacks("minecraft:diamond_sword", 4, size=1)), 3),
    "lectern": (reader("minecraft:lectern[facing=north,has_book=true,powered=false]",
                       "minecraft:lectern", extra={"Page": nbt.Int(2), "Book": {
                           "id": "minecraft:written_book", "count": nbt.Int(1),
                           "components": {"minecraft:written_book_content": {
                               "pages": [{"raw": "x"}] * 5}}}}), 8),
})


@pytest.fixture(scope="module")
def run(module_engine):
    tiles = {k: v[0] for k, v in TILES.items()}
    tiles["double"] = double_chest()
    circuit = bench(tiles)
    world, conv = module_engine.prepare(circuit)
    probes = list(circuit.outputs)
    result = module_engine.run_raw(world, "circuit", conv.size, [
        {"wait": 10, "read": [list(conv.to_luanti(circuit.outputs[p])) for p in probes]}])
    assert result["place_ok"], result["place_message"]
    manifest = json.loads((world / "schems/circuit.craftpipe.json").read_text())
    return dict(zip(probes, result["steps"][0])), manifest, conv, circuit, result


@pytest.mark.parametrize("tile", sorted(TILES))
def test_container_signal_strength(run, tile):
    reads, *_ = run
    want = TILES[tile][1]
    assert reads[f"{tile}.cmp"]["param2"] >> 2 == want
    assert reads[f"{tile}.out"]["param2"] & 15 == want


def test_double_chest_reads_across_both_halves(run):
    reads, *_ = run
    assert reads["double.full"]["param2"] >> 2 == 8
    assert reads["double.empty"]["param2"] >> 2 == 8


def test_manifest_signal_matches_engine(run):
    reads, manifest, conv, circuit, _ = run
    by_pos = {tuple(e["pos"]): e["signal"] for e in manifest["containers"] + manifest["meta"]}
    checked = 0
    for tile, (sub, want) in TILES.items():
        cmp_pos = circuit.outputs[f"{tile}.cmp"]
        container = conv.to_luanti((cmp_pos[0] - 1, cmp_pos[1], cmp_pos[2]))
        assert by_pos[container] == want == reads[f"{tile}.cmp"]["param2"] >> 2, tile
        checked += 1
    assert checked == len(TILES)


def test_loader_reports_containers(run):
    *_, result = run
    assert result["place_stats"]["containers"] == len(TILES) - 1 + 2   # lectern is meta; double has 2
    assert result["place_stats"]["skipped_stacks"] == 0
