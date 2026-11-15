import pytest

import suites
from harness.readings import Reading
from parity import differences
from parity.differences import Difference, check


def entry(**kw):
    base = dict(id="x", suite="logic", output="tile.lamp", step=1,
                minecraft={"on": False}, mineclonia={"on": True}, established="measured",
                title="t", explanation="e", with_java_rules="remains")
    base.update(kw)
    return Difference(**base)


def test_file_entries_are_well_formed():
    entries = differences.load()
    assert len({e.id for e in entries}) == len(entries)
    for e in entries:
        assert e.established in ("measured", "documented"), e.id
        assert e.suite in suites.ALL or e.suite == "timing", e.id
        assert e.title.strip() and e.explanation.strip(), e.id
        assert e.minecraft != e.mineclonia, e.id
        assert isinstance(e.step, (int, str)), e.id


def test_equal_readings_pass_without_an_entry():
    check("logic", "a.lamp", 1, Reading(True, None), Reading(True, None), entries=[])


def test_unequal_readings_fail_without_an_entry():
    with pytest.raises(AssertionError, match="a.lamp"):
        check("logic", "a.lamp", 1, Reading(True, None), Reading(False, None), entries=[])


def test_recorded_difference_passes_when_it_occurs():
    check("logic", "tile.lamp", 1, Reading(False, None), Reading(True, None), entries=[entry()])


def test_recorded_difference_fails_when_it_stops_occurring():
    with pytest.raises(AssertionError, match="no longer"):
        check("logic", "tile.lamp", 1, Reading(True, None), Reading(True, None), entries=[entry()])


def test_recorded_difference_fails_when_it_changes():
    with pytest.raises(AssertionError):
        check("logic", "tile.lamp", 1, Reading(False, None), Reading(False, None), entries=[entry()])


def test_entry_only_applies_to_its_suite_output_and_step():
    e = entry()
    for suite, output, step in [("rom", "tile.lamp", 1), ("logic", "other.lamp", 1), ("logic", "tile.lamp", 2)]:
        with pytest.raises(AssertionError):
            check(suite, output, step, Reading(False, None), Reading(True, None), entries=[e])


def test_output_patterns_and_any_step():
    e = entry(output="button_*.lamp", step="*", minecraft={"power": 3}, mineclonia={"power": 5})
    check("logic", "button_oak.lamp", 7, Reading(True, 3), Reading(True, 5), entries=[e])


def test_plain_values_can_be_compared_too():
    check("timing", "rep.out", "trace", {"delay_ticks": 2}, {"delay_ticks": 2}, entries=[])
    e = entry(suite="timing", output="rep.out", step="trace",
              minecraft={"delay_ticks": 15}, mineclonia={"delay_ticks": 10})
    check("timing", "rep.out", "trace", {"delay_ticks": 15}, {"delay_ticks": 10}, entries=[e])


# ---- trace summaries -------------------------------------------------------

from parity.differences import changes, summarise   # noqa: E402

R = Reading


def trace_of(*values):
    return [{"x": v} for v in values]


def test_changes_lists_tick_and_new_value():
    t = trace_of(R(False, None), R(True, None), R(True, None), R(False, None))
    assert changes(t, "x", before=R(False, None)) == [(1, R(True, None)), (3, R(False, None))]
    assert changes(t, "x", before=R(True, None)) == [(0, R(False, None)), (1, R(True, None)), (3, R(False, None))]
    assert changes(trace_of(R(False, 0), R(False, 0)), "x", before=R(False, 0)) == []


def test_wave_summary_is_relative_to_the_reference():
    out = [(4, R(True, None)), (14, R(False, None))]
    assert summarise("wave", out, ref_first=2) == {
        "changes_at": [2, 12], "values": [[True, None], [False, None]]}
    assert summarise("wave", [], ref_first=2) == {"changes_at": [], "values": []}
    assert summarise("wave", out, ref_first=None) == {
        "changes_at": [4, 14], "values": [[True, None], [False, None]]}


def test_period_summary_ignores_phase():
    a = [(3, R(True, 15)), (8, R(False, 0)), (13, R(True, 15)), (18, R(False, 0))]
    b = [(1, R(False, 0)), (6, R(True, 15)), (11, R(False, 0))]
    assert summarise("period", a, None) == summarise("period", b, None) == {"half_periods": [5]}
    assert summarise("period", [], None) == {"half_periods": []}


def test_count_summary():
    a = [(1, R(False, None)), (2, R(True, None)), (3, R(False, None))]
    assert summarise("count", a, None) == {"changes": 3, "final_on": False}


# ---- README section ----------------------------------------------------------

import importlib.util   # noqa: E402
import pathlib          # noqa: E402

REPO = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("render_differences", REPO / "tools/render_differences.py")
render_differences = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(render_differences)


def test_render_marks_documented_entries():
    text = render_differences.render([
        entry(id="a", title="First", explanation="Why one."),
        entry(id="b", title="Second", explanation="Why two.", established="documented"),
    ])
    assert "- **First.** Why one." in text
    assert "- **Second.** Why two. *(Minecraft's side is taken from documentation, not measured.)*" in text


def test_readme_differences_section_is_in_sync():
    readme = (REPO / "README.md").read_text()
    start, end = render_differences.START, render_differences.END
    assert start in readme and end in readme
    section = readme.split(start, 1)[1].split(end, 1)[0].strip()
    assert section == render_differences.render(differences.load()).strip(), \
        "run `python tools/render_differences.py`"


def test_every_recorded_difference_is_exercised_by_a_parity_test():
    """An entry that matches no test case could outlive its difference
    unnoticed (a renamed tile, a mistyped step)."""
    from parity import test_parity, test_timing
    cases = [(name, output, step) for name in test_parity.FAST
             for step, output in test_parity._cases(name)]
    for tile, out, mode in test_timing.OUTPUTS:
        name = f"{tile}.{out}"
        cases += [("timing", name, s) for s in (0, 1, 2) if tile not in test_timing.FREE_RUNNING]
        if mode:
            cases += [("timing", name, f"trace{s}") for s in (1, 2)]
    cases += [("timing", f"{tile}.ref", f"input{s}") for tile, s in test_timing.LATENCY_CASES]
    unused = [e.id for e in differences.load() if not any(e.applies(*c) for c in cases)]
    assert not unused
    orphan = entry(id="orphan", suite="timing", output="no_such_tile.out")
    assert not any(orphan.applies(*c) for c in cases)


# ---- with the Java-rules mod -------------------------------------------------

def test_entries_say_what_the_mod_does_to_them():
    for e in differences.load():
        assert e.with_java_rules in ("fixed", "remains"), e.id


def test_fixed_entry_must_be_gone_in_java_mode():
    e = entry(with_java_rules="fixed")
    check("logic", "tile.lamp", 1, Reading(True, None), Reading(True, None), entries=[e], mode="java")
    with pytest.raises(AssertionError):
        check("logic", "tile.lamp", 1, Reading(False, None), Reading(True, None), entries=[e], mode="java")


def test_remaining_entry_must_still_occur_in_java_mode():
    e = entry(with_java_rules="remains")
    check("logic", "tile.lamp", 1, Reading(False, None), Reading(True, None), entries=[e], mode="java")
    with pytest.raises(AssertionError, match="no longer"):
        check("logic", "tile.lamp", 1, Reading(True, None), Reading(True, None), entries=[e], mode="java")
