from harness.readings import Reading, luanti_reading


def raw(name, param2=0):
    return {"name": name, "param2": param2, "on": name.endswith("_on") or "_on_" in name}


def test_dust():
    assert luanti_reading(raw("mcl_redstone:wire_05", 0x77)) == Reading(True, 7)
    assert luanti_reading(raw("mcl_redstone:redstone", 0)) == Reading(False, 0)


def test_comparator():
    assert luanti_reading(raw("mcl_comparators:comparator_on_comp", 9 * 4 + 2)) == Reading(True, 9)
    assert luanti_reading(raw("mcl_comparators:comparator_off_sub", 3)) == Reading(False, 0)


def test_plain_components():
    assert luanti_reading(raw("mcl_redstone_lamp:lamp_on")) == Reading(True, None)
    assert luanti_reading(raw("mcl_lever:lever_off", 10)) == Reading(False, None)
    assert luanti_reading(raw("mcl_repeaters:repeater_on_locked", 6)) == Reading(True, None)
    assert luanti_reading(raw("mcl_redstone_torch:redstone_torch_off_wall", 3)) == Reading(False, None)
