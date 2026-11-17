"""config/minecraft-keys.conf and the tool that merges it into a
player's Luanti settings."""

import importlib.util
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
CONF = REPO / "config/minecraft-keys.conf"
SETTINGTYPES = pathlib.Path("/usr/share/luanti/builtin/settingtypes.txt")
spec = importlib.util.spec_from_file_location("apply_keys", REPO / "tools/apply_minecraft_keys.py")
apply_keys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply_keys)


def settings():
    return apply_keys.parse(CONF.read_text())


def test_preset_remaps_the_keys_that_differ_from_minecraft():
    s = settings()
    assert s["keymap_inventory"].startswith("SYSTEM_SCANCODE_8")      # E
    assert s["keymap_aux1"].startswith("SYSTEM_SCANCODE_224")         # Left Ctrl (sprint)
    assert s["keymap_camera_mode"] == "SYSTEM_SCANCODE_62"            # F5
    assert s["keymap_toggle_debug"] == "SYSTEM_SCANCODE_60"           # F3
    assert s["keymap_screenshot"].startswith("SYSTEM_SCANCODE_59")    # F2
    assert s["doubletap_jump"] == "true"


def test_values_are_well_formed():
    for name, value in settings().items():
        if name.startswith("keymap_"):
            assert re.fullmatch(r"((SYSTEM_SCANCODE_\d+|GAMEPAD_\w+)(\||$))*", value), (name, value)


def test_setting_names_exist_in_this_luanti():
    if not SETTINGTYPES.exists():
        pytest.skip("Luanti's settingtypes.txt is not installed here")
    known = set(re.findall(r"^(\w+) \(", SETTINGTYPES.read_text(), flags=re.M))
    assert not [name for name in settings() if name not in known]


def test_no_keyboard_key_is_bound_twice_after_applying_to_the_defaults():
    """Applied on top of Luanti's own defaults, no two actions may end up
    on the same keyboard key."""
    if not SETTINGTYPES.exists():
        pytest.skip("Luanti's settingtypes.txt is not installed here")
    defaults = dict(re.findall(r"^(keymap_\w+) \([^)]*\) key ?(\S*)$", SETTINGTYPES.read_text(), flags=re.M))
    merged = {**defaults, **{k: v for k, v in settings().items() if k.startswith("keymap_")}}
    seen = {}
    for name, value in merged.items():
        for key in value.split("|"):
            if key.startswith("SYSTEM_SCANCODE_"):
                assert key not in seen, f"{key} is bound to both {seen[key]} and {name}"
                seen[key] = name


def test_apply_merges_without_losing_other_settings(tmp_path):
    target = tmp_path / "minetest.conf"
    target.write_text("mainmenu_last_selected_world = 3\nkeymap_inventory = SYSTEM_SCANCODE_12\n"
                      "name = student\n")
    changed = apply_keys.apply(CONF, target)
    text = target.read_text()
    assert "mainmenu_last_selected_world = 3" in text and "name = student" in text
    assert text.count("keymap_inventory") == 1
    assert apply_keys.parse(text)["keymap_inventory"] == settings()["keymap_inventory"]
    assert changed == len(settings())
    assert (tmp_path / "minetest.conf.before-minecraft-keys").read_text().startswith("mainmenu_last")


def test_apply_is_idempotent_and_creates_a_missing_file(tmp_path):
    target = tmp_path / "sub" / "minetest.conf"
    assert apply_keys.apply(CONF, target) == len(settings())
    first = target.read_text()
    assert apply_keys.apply(CONF, target) == 0
    assert target.read_text() == first
    assert apply_keys.parse(first) == settings()


def test_cli_reports_what_it_did(tmp_path, capsys):
    target = tmp_path / "minetest.conf"
    assert apply_keys.main([str(target)]) == 0
    assert str(target) in capsys.readouterr().out
