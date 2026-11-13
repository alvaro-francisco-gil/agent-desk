"""`cs`: pick one of this machine's repos and start Claude in it, as a herdr workspace named after the repo."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from agent_desk import repos
from agent_desk.closed import CACHE, ago, closed_sessions, place

HERDR_APP_ID = "org.omarchy.herdr"


def match(labels: list[str], query: str) -> str | None:
    """The label equal to the query, else the only one ending in /query or containing it."""
    if query in labels:
        return query
    for test in (lambda l: l.endswith("/" + query), lambda l: query in l):
        hits = [l for l in labels if test(l)]
        if len(hits) == 1:
            return hits[0]
    return None


def herdr(*args: str) -> dict:
    out = subprocess.run(["herdr", *args], capture_output=True, text=True).stdout
    reply = json.loads(out) if out.strip() else {}
    if "error" in reply:
        raise RuntimeError(f"herdr {' '.join(args)}: {reply['error'].get('message', reply['error'])}")
    return reply.get("result", {})


def server_running() -> bool:
    out = subprocess.run(["herdr", "status", "server"], capture_output=True, text=True).stdout
    return "status: running" in out


def ensure_server() -> None:
    if server_running():
        return
    subprocess.Popen(["herdr", "server"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(50):
        if server_running():
            return
        time.sleep(0.1)
    raise RuntimeError("herdr server did not start; see ~/.config/herdr/herdr-server.log")


def open_session(label: str, path: Path, command: str = "claude") -> str:
    """Run `command` (Claude) in a new tab of the repo's workspace (created if missing); returns the workspace id."""
    existing = [w for w in herdr("workspace", "list").get("workspaces", []) if w.get("label") == label]
    if existing:
        workspace = existing[0]["workspace_id"]
        pane = herdr("tab", "create", "--workspace", workspace, "--cwd", str(path), "--no-focus")["root_pane"]
    else:
        pane = herdr("workspace", "create", "--cwd", str(path), "--label", label, "--no-focus")["root_pane"]
        workspace = pane["workspace_id"]
    herdr("pane", "run", pane["pane_id"], command)
    herdr("tab", "focus", pane["tab_id"])
    return workspace


def detached(argv: list[str]) -> None:
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def show_herdr_window() -> None:
    """Bring herdr up: on Hyprland focus its window or open one; elsewhere open a terminal running it."""
    if shutil.which("hyprctl"):
        show_hyprland_herdr_window()
    elif shutil.which("ghostty"):
        detached(["ghostty", "-e", "herdr"])
    elif shutil.which("x-terminal-emulator"):
        detached(["x-terminal-emulator", "-e", "herdr"])
    else:
        raise RuntimeError("no terminal to show herdr in (looked for ghostty and x-terminal-emulator)")


def show_hyprland_herdr_window() -> None:
    """Focus the herdr window, or open one detached from this terminal.

    Matches the window class only: omarchy-launch-or-focus also matches titles,
    and the picker's own terminal title names org.omarchy.herdr, so it focused
    the picker and the herdr window never opened.
    """
    clients = json.loads(subprocess.run(["hyprctl", "clients", "-j"], capture_output=True,
                                        text=True, check=True).stdout)
    window = next((c["address"] for c in clients if c.get("class") == HERDR_APP_ID), None)
    if window:
        subprocess.run(["hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{window}" }})'],
                       capture_output=True, check=False)
        return
    detached(["omarchy-launch-tui", f"--app-id={HERDR_APP_ID}", "herdr"])


def pick(labels: list[str]) -> str | None:
    if not shutil.which("fzf"):
        raise RuntimeError("fzf is missing; pass the repo name instead: cs <repo>")
    done = subprocess.run(["fzf", "--prompt", "claude in ▸ ", "--height", "~100%", "--reverse"],
                          input="\n".join(labels), capture_output=False, stdout=subprocess.PIPE, text=True)
    return done.stdout.strip() or None


def open_ids() -> set[str]:
    """The Claude sessions some herdr pane runs right now."""
    agents = herdr("agent", "list").get("agents", [])
    return {a["agent_session"]["value"] for a in agents if a.get("agent_session", {}).get("value")}


def pick_closed(found: dict[str, Path]) -> tuple[str, Path, str] | None:
    """List the closed sessions; returns the picked one's workspace label, folder and session id."""
    sessions = closed_sessions(Path("~/.claude/projects").expanduser(), open_ids(), cache_file=CACHE)
    if not sessions:
        print("cs: no closed sessions to reopen", file=sys.stderr)
        return None
    if not shutil.which("fzf"):
        raise RuntimeError("fzf is missing")
    rows = [(s, place(s.cwd, found)) for s in sessions]
    width = max(len(label) for _, label in rows)
    lines = [f"{i}\t{ago(s.closed_at):>8}  {label:<{width}}  {s.name}" for i, (s, label) in enumerate(rows)]
    done = subprocess.run(["fzf", "--prompt", "reopen ▸ ", "--height", "~100%", "--reverse",
                           "--delimiter", "\t", "--with-nth", "2..", "--no-sort"],
                          input="\n".join(lines), stdout=subprocess.PIPE, text=True)
    chosen = done.stdout.strip()
    if not chosen:
        return None
    session, label = rows[int(chosen.split("\t", 1)[0])]
    return label, session.cwd, session.session_id


def reopen(found: dict[str, Path]) -> int:
    try:
        ensure_server()
        picked = pick_closed(found)
        if picked is None:
            return 1
        label, cwd, session_id = picked
        open_session(label, cwd, f"claude --resume {session_id}")
    except RuntimeError as e:
        print(f"cs: {e}", file=sys.stderr)
        return 1
    if os.environ.get("HERDR_ENV") != "1":
        show_herdr_window()
    return 0


def main(argv: list[str], config: Path = repos.CONFIG) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print("usage: cs [repo]    start Claude in a repo, as a herdr workspace named after it\n"
              "       cs <repo> --run <line>  type <line> at the new tab's prompt instead of claude\n"
              "       cs --closed  reopen one of the Claude sessions closed most recently")
        return 0
    try:
        found = repos.load(config)
    except repos.ConfigError as e:
        print(f"cs: {e}", file=sys.stderr)
        return 1
    if argv and argv[0] == "--closed":
        return reopen(found)
    # --run lets a desktop action (the Omarchy crash toast) start its own command
    # in a repo's herdr workspace instead of a loose terminal window.
    command = "claude"
    if len(argv) == 3 and argv[1] == "--run":
        command = argv[2]
        argv = argv[:1]
    elif "--run" in argv:
        print("cs: --run needs a repo before it and one line after it", file=sys.stderr)
        return 1
    labels = list(found)
    label = match(labels, argv[0]) if argv else pick(labels)
    if label is None:
        if argv:
            print(f"cs: no single repo matches {argv[0]!r}", file=sys.stderr)
        return 1
    try:
        ensure_server()
        open_session(label, found[label], command)
    except RuntimeError as e:
        print(f"cs: {e}", file=sys.stderr)
        return 1
    if os.environ.get("HERDR_ENV") != "1":
        show_herdr_window()
    return 0
