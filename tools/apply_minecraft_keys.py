#!/usr/bin/env python3
"""Give a Luanti installation Minecraft-style controls.

    python tools/apply_minecraft_keys.py [path/to/minetest.conf]

Merges config/minecraft-keys.conf into the player's Luanti settings file:
the listed settings are replaced, everything else is left as it was, and
the original is kept beside it as minetest.conf.before-minecraft-keys.
Close Luanti first; it rewrites its settings file when it exits.

Without a path, ~/.minetest/minetest.conf is used if it exists.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import sys

PRESET = pathlib.Path(__file__).resolve().parents[1] / "config/minecraft-keys.conf"
DEFAULT_TARGET = pathlib.Path.home() / ".minetest/minetest.conf"
_LINE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*=\s*(.*?)\s*$")


def parse(text: str) -> dict[str, str]:
    """name -> value for every `name = value` line; comments are ignored."""
    out = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = _LINE.match(line)
        if match:
            out[match.group(1)] = match.group(2)
    return out


def apply(preset: pathlib.Path, target: pathlib.Path) -> int:
    """Merge the preset into the settings file. Returns how many settings
    were added or changed (0 means it was already applied)."""
    wanted = parse(preset.read_text())
    original = target.read_text() if target.exists() else ""
    current = parse(original)
    changed = [name for name, value in wanted.items() if current.get(name) != value]
    if not changed:
        return 0
    kept = []
    for line in original.splitlines():
        match = _LINE.match(line) if not line.lstrip().startswith("#") else None
        if not (match and match.group(1) in wanted):
            kept.append(line)
    kept += [f"{name} = {value}".rstrip() if value else f"{name} =" for name, value in wanted.items()]
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_name(target.name + ".before-minecraft-keys")
        if not backup.exists():
            shutil.copy2(target, backup)
    target.write_text("\n".join(kept) + "\n")
    return len(changed)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(args) > 1:
        print("usage: apply_minecraft_keys.py [path/to/minetest.conf]", file=sys.stderr)
        return 2
    if args:
        target = pathlib.Path(args[0]).expanduser()
    elif DEFAULT_TARGET.exists():
        target = DEFAULT_TARGET
    else:
        print(f"{DEFAULT_TARGET} does not exist; pass the path to this computer's minetest.conf",
              file=sys.stderr)
        return 2
    count = apply(PRESET, target)
    if count:
        print(f"{target}: {count} setting(s) updated for Minecraft-style controls")
    else:
        print(f"{target}: already has the Minecraft-style controls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
