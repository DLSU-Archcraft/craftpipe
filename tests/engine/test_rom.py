"""Containers used as comparator ROM give the same signal after conversion
(circuits in suites.py)."""

import json

import pytest

import suites
from suites import ROM_TILES as TILES


@pytest.fixture(scope="module")
def run(module_engine):
    circuit = suites.rom().circuit
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
