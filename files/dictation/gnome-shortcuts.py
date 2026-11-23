#!/usr/bin/env python3
"""Add or update GNOME custom shortcuts, keeping the ones already there.

Usage: gnome-shortcuts.py '<json list of {"id", "name", "command", "binding"}>'
Each shortcut lives at .../custom-keybindings/<id>/, so a re-run updates it in place.
Prints "changed" when it wrote anything, "ok" otherwise. Installed by tasks/dictation.yml.
"""

import ast
import json
import subprocess
import sys

SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"


def gsettings(*args: str) -> str:
    return subprocess.run(
        ["gsettings", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def parse(value: str):
    """A GVariant as gsettings prints it: '@as []', "['/a/']", "'text'"."""
    if value.startswith("@"):
        value = value.split(" ", 1)[1]
    return ast.literal_eval(value)


def main() -> int:
    wanted = json.loads(sys.argv[1])
    changed = False
    paths = parse(gsettings("get", SCHEMA, "custom-keybindings"))
    for shortcut in wanted:
        path = f"{BASE}{shortcut['id']}/"
        schema = f"{SCHEMA}.custom-keybinding:{path}"
        for key in ("name", "command", "binding"):
            if parse(gsettings("get", schema, key)) != shortcut[key]:
                gsettings("set", schema, key, json.dumps(shortcut[key]))
                changed = True
        if path not in paths:
            paths.append(path)
            gsettings("set", SCHEMA, "custom-keybindings", json.dumps(paths))
            changed = True
    print("changed" if changed else "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
