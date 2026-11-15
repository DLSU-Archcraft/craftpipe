"""The recorded differences between Minecraft and Mineclonia.

known_differences.json is the single list of ways the two games are known
to behave differently for the circuits under test. The parity tests call
``check`` for every observation: anything not recorded must be identical
in both games, and anything recorded must still occur exactly as recorded
(so an entry cannot outlive the difference it describes).
"""

from __future__ import annotations

import fnmatch
import json
import pathlib
from dataclasses import dataclass

PATH = pathlib.Path(__file__).with_name("known_differences.json")


@dataclass(frozen=True)
class Difference:
    id: str
    suite: str
    output: str            # fnmatch pattern over "<tile>.<output>"
    step: object           # step index, "trace", or "*" for any
    minecraft: dict        # the observation keys this entry pins, e.g. {"on": False}
    mineclonia: dict
    established: str       # "measured" or "documented" (Minecraft side taken from documentation)
    title: str
    explanation: str

    def applies(self, suite: str, output: str, step) -> bool:
        return (self.suite == suite and fnmatch.fnmatchcase(output, self.output)
                and (self.step == "*" or self.step == step))


def load(path: pathlib.Path = PATH) -> list[Difference]:
    return [Difference(**raw) for raw in json.loads(path.read_text())]


def _observation(value) -> dict:
    if hasattr(value, "_asdict"):
        return dict(value._asdict())
    return dict(value)


def check(suite: str, output: str, step, minecraft, mineclonia, entries=None) -> None:
    """Assert that the two observations agree, or differ exactly as recorded."""
    entries = load() if entries is None else entries
    mc, mcl = _observation(minecraft), _observation(mineclonia)
    where = f"{suite} / {output} / step {step}"
    matching = [e for e in entries if e.applies(suite, output, step)]
    if not matching:
        assert mc == mcl, f"{where}: Minecraft gave {mc}, Mineclonia gave {mcl}"
        return
    (entry,) = matching
    assert mc != mcl, (f"{where}: recorded difference '{entry.id}' no longer occurs "
                       f"(both games gave {mc}); remove or update the entry")
    for label, got, want in (("Minecraft", mc, entry.minecraft), ("Mineclonia", mcl, entry.mineclonia)):
        mismatch = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
        assert not mismatch, (f"{where}: recorded difference '{entry.id}' changed; {label} gave "
                              f"{got}, entry expects {want}")
    other = {k for k in mc if k not in entry.minecraft and mc[k] != mcl.get(k)}
    assert not other, f"{where}: the games also differ in {sorted(other)}, which '{entry.id}' does not record"
