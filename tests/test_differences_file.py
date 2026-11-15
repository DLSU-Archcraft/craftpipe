import pytest

import suites
from harness.readings import Reading
from parity import differences
from parity.differences import Difference, check


def entry(**kw):
    base = dict(id="x", suite="logic", output="tile.lamp", step=1,
                minecraft={"on": False}, mineclonia={"on": True}, established="measured",
                title="t", explanation="e")
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
