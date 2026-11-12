#!/usr/bin/env python3
"""Alt+Enter in herdr: a shell in a new tab of the current workspace, listed in the agents panel.

herdr lists only panes that report as agents there, so the new pane reports
itself as the `terminal` agent. Bound by tasks/agent_sessions.yml.
start-app (ALT+D) opens its apps through this too, with --cwd, --name and --run;
--name adds -1, -2... while another tab holds that name.
A line highlighted in the source pane (herdr copies a mouse selection to the
clipboard) is typed at the new prompt, not run; see highlighted_line().
"""

import argparse
import itertools
import json
import os
import subprocess
from pathlib import Path

# The agents panel shows a shell by its pane name alone; a blank braille cell and
# a space line it up with the names after the agents' state dots. herdr trims
# plain spaces.
INDENT = "\u2800 "


def herdr(*args: str) -> dict:
    out = subprocess.run(["herdr", *args], capture_output=True, text=True, check=True).stdout
    if not out.strip():
        return {}
    reply = json.loads(out)
    if "result" not in reply:
        raise SystemExit(f"herdr {' '.join(args)}: {reply.get('error', reply)}")
    return reply["result"]


def source_pane() -> dict | None:
    """The pane the key was pressed in: the focused one, else HERDR_PANE_ID if herdr passes it."""
    panes = herdr("pane", "list").get("panes", [])
    wanted = os.environ.get("HERDR_PANE_ID")
    return next((p for p in panes if p.get("focused")), None) or next(
        (p for p in panes if p["pane_id"] == wanted), None
    )


def highlighted_line(pane: dict) -> str | None:
    """The clipboard, if it is one line on the pane's screen: what was just highlighted there.

    Anything else on the clipboard (an old copy, a copy from another app) is left out, and so
    is a multi-line selection, whose line breaks would run its lines one by one. The read asks
    for no more rows than the screen holds: for more, herdr scrolls a Claude Code pane up
    through its history and back, which shows as a jump before the new tab opens.
    """
    rows = str((pane.get("scroll") or {}).get("viewport_rows") or 24)
    try:
        clip = subprocess.run(
            ["wl-paste", "--no-newline", "--type", "text"],
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        if not clip or "\n" in clip or "\r" in clip:
            return None
        shown = subprocess.run(
            [
                "herdr",
                "pane",
                "read",
                pane["pane_id"],
                "--source",
                "recent-unwrapped",
                "--lines",
                rows,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    wanted = " ".join(clip.split())
    if not any(wanted in " ".join(row.split()) for row in shown.splitlines()):
        return None
    # Claude shows commands as `$ command`.
    return clip.removeprefix("$ ").strip()


def free_name(name: str) -> str:
    """The name, or the first of name-1, name-2... no tab holds, in any workspace."""
    taken = {tab.get("label") for tab in herdr("tab", "list").get("tabs", [])}
    if name not in taken:
        return name
    return next(f"{name}-{n}" for n in itertools.count(1) if f"{name}-{n}" not in taken)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", help="the tab's folder, instead of the source pane's")
    parser.add_argument("--name", help="the tab and pane name, instead of terminal")
    parser.add_argument("--run", help="a command to type at the tab's prompt")
    options = parser.parse_args()

    pane = source_pane()
    typed = None
    if pane:
        typed = None if options.run else highlighted_line(pane)
        workspace, cwd = pane["workspace_id"], pane["cwd"]
    else:
        workspaces = herdr("workspace", "list").get("workspaces", [])
        workspace = next((w["workspace_id"] for w in workspaces if w.get("focused")), None)
        if workspace is None:
            raise SystemExit("herdr-new-terminal: no focused herdr workspace")
        cwd = str(Path.home())
    name = free_name(options.name) if options.name else "terminal"
    tab = herdr(
        "tab",
        "create",
        "--workspace",
        workspace,
        "--cwd",
        options.cwd or cwd,
        "--label",
        name,
        "--focus",
    )
    pane_id = tab["root_pane"]["pane_id"]
    herdr("pane", "rename", pane_id, INDENT + name)
    herdr(
        "pane",
        "report-agent",
        pane_id,
        "--source",
        "workstation:terminal",
        "--agent",
        "terminal",
        "--state",
        "idle",
    )
    if options.run:
        herdr("pane", "run", pane_id, options.run)
    elif typed:
        herdr("pane", "send-text", pane_id, typed)


if __name__ == "__main__":
    main()
