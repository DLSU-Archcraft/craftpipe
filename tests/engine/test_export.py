"""/craftpipe_export: saving a region of a Mineclonia world for conversion
back to Minecraft."""

import hashlib
import json

import suites


def export(engine, steps, circuit=None):
    world, conv = engine.prepare(circuit or suites.rom().circuit)
    result = engine.run_raw(world, "circuit", conv.size, steps)
    assert result["place_ok"], result["place_message"]
    return world, conv, result


def test_export_writes_schematic_and_manifest(engine):
    world, conv, result = export(engine, [{"export": {"name": "out"}}])
    (entry,) = result["exports"]
    assert entry["ok"], entry["message"]
    assert "exported out" in entry["message"]
    mts_file, manifest_file = world / "schems/out.mts", world / "schems/out.craftpipe.json"
    manifest = json.loads(manifest_file.read_text())
    assert manifest["format"] == 1 and manifest["size"] == list(conv.size)
    assert manifest["mts_sha1"] == hashlib.sha1(mts_file.read_bytes()).hexdigest()
    forward = json.loads((world / "schems/circuit.craftpipe.json").read_text())
    assert len(manifest["containers"]) == len(forward["containers"]) == entry["containers"]

    def stacks(m):
        return {tuple(c["pos"]): {name: [(s["slot"], s["name"], s["count"]) for s in lst]
                                  for name, lst in (c["lists"] or {}).items() if lst}
                for c in m["containers"]}
    assert stacks(manifest) == stacks(forward)
    first = next(s for c in manifest["containers"] for lst in (c["lists"] or {}).values() for s in lst)
    assert first["max"] in (1, 16, 64)
    (meta,) = manifest["meta"]
    assert meta["fields"] == {"pages": "5", "page": "3"}


def test_export_refuses_bad_names_and_huge_regions(engine):
    _, _, result = export(engine, [
        {"export": {"name": "../evil"}},
        {"export": {"name": "big", "region": [[0, 0, 0], [999, 99, 999]]}},
    ])
    bad_name, too_big = result["exports"]
    assert bad_name["ok"] is False and "invalid schematic name" in bad_name["message"]
    assert too_big["ok"] is False and "too large" in too_big["message"]


def test_an_export_can_be_placed_again(engine):
    """The exported pair is a valid input for /craftpipe_place."""
    world, conv, result = export(engine, [{"export": {"name": "copy"}}])
    assert result["exports"][0]["ok"]
    again = engine.run_raw(world, "copy", conv.size, [])
    assert again["place_ok"], again["place_message"]
