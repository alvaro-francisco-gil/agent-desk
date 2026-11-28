"""`cs`: pick one of this machine's repos and start Claude in it, as a herdr workspace named after the repo."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from agent_desk import accounts, repos, switch
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


def pick(labels: list[str], names: list[str]) -> tuple[str, str] | None:
    """The repo picked and the account to start it on: Enter is the first account, Alt+2… the next ones."""
    if not shutil.which("fzf"):
        raise RuntimeError("fzf is missing; pass the repo name instead: cs <repo>")
    done = subprocess.run(["fzf", "--prompt", "claude in ▸ ", "--height", "~100%", "--reverse", *account_flags(names)],
                          input="\n".join(labels), stdout=subprocess.PIPE, text=True)
    label, account = chosen(done.stdout, names)
    return (label.strip(), account) if label.strip() else None


def open_ids() -> set[str]:
    """The Claude sessions some herdr pane runs right now."""
    agents = herdr("agent", "list").get("agents", [])
    return {a["agent_session"]["value"] for a in agents if a.get("agent_session", {}).get("value")}


def account_keys(names: list[str]) -> dict[str, str]:
    """fzf key → account: Enter is the first account, Alt+2… the next ones."""
    return {f"alt-{i}": name for i, name in enumerate(names[1:], start=2)}


def account_flags(names: list[str]) -> list[str]:
    keys = account_keys(names)
    if not keys:
        return []
    hint = "  ".join([f"enter: {names[0]}"] + [f"{k.replace('alt-', 'alt+')}: {n}" for k, n in keys.items()])
    return ["--expect", ",".join(keys), "--header", hint]


def chosen(stdout: str, names: list[str]) -> tuple[str, str]:
    """fzf's output with account_flags: (picked line, account)."""
    keys = account_keys(names)
    lines = stdout.splitlines()
    if not keys:
        return (lines[0] if lines else ""), names[0]
    key, line = (lines + ["", ""])[:2]
    return line, keys.get(key, names[0])


SHOW_HELPERS = "helpers"


def pick_closed(found: dict[str, Path], names: list[str]) -> tuple[str, Path, str, str] | None:
    """List the closed sessions; returns the picked one's workspace label, folder, session id and account.

    Helper sessions (another Claude session started them) stay hidden behind a last row
    that lists everything again with them in.
    """
    sessions = closed_sessions(Path("~/.claude/projects").expanduser(), open_ids(), cache_file=CACHE)
    if not sessions:
        print("cs: no closed sessions to reopen", file=sys.stderr)
        return None
    if not shutil.which("fzf"):
        raise RuntimeError("fzf is missing")
    hidden = sum(s.helper for s in sessions)
    show_helpers = hidden == len(sessions)
    while True:
        shown = sessions if show_helpers else [s for s in sessions if not s.helper]
        rows = [(s, place(s.cwd, found)) for s in shown]
        width = max(len(label) for _, label in rows)
        lines = [f"{i}\t{ago(s.closed_at):>8}  {label:<{width}}  {s.name}" for i, (s, label) in enumerate(rows)]
        if hidden and not show_helpers:
            lines.append(f"{SHOW_HELPERS}\t  ▸ show hidden helper sessions ({hidden})")
        done = subprocess.run(["fzf", "--prompt", "reopen ▸ ", "--height", "~100%", "--reverse",
                               "--delimiter", "\t", "--with-nth", "2..", "--no-sort", *account_flags(names)],
                              input="\n".join(lines), stdout=subprocess.PIPE, text=True)
        line, account = chosen(done.stdout, names)
        if not line.strip():
            return None
        key = line.split("\t", 1)[0]
        if key == SHOW_HELPERS:
            show_helpers = True
            continue
        session, label = rows[int(key)]
        return label, session.cwd, session.session_id, account


def reopen(found: dict[str, Path], known: dict[str, Path | None]) -> int:
    try:
        ensure_server()
        picked = pick_closed(found, list(known))
        if picked is None:
            return 1
        label, cwd, session_id, account = picked
        open_session(label, cwd, accounts.command(account, known[account], f"claude --resume {session_id}"))
    except (RuntimeError, repos.ConfigError) as e:
        print(f"cs: {e}", file=sys.stderr)
        return 1
    if os.environ.get("HERDR_ENV") != "1":
        show_herdr_window()
    return 0


def switch_session(argv: list[str], account: str | None, found: dict[str, Path],
                   known: dict[str, Path | None]) -> int:
    """--switch checks the session and account, then hands the work to a detached --switch-now."""
    if len(argv) != 2 or account is None:
        print("cs: usage: cs --switch <session id or name> --as <account>", file=sys.stderr)
        return 1
    try:
        ensure_server()
        query = argv[1]
        if query == "here":  # the session of the agent running this, from Claude Code's own env
            query = os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
            if not query:
                raise RuntimeError("`here` only works from inside a Claude Code session")
        session = switch.find(query, switch.all_sessions(herdr))
        if argv[0] == "--switch":
            accounts.command(account, known[account])  # a missing token fails here, before any pane closes
            switch.detach(["--switch-now", session.session_id, "--as", account])
            what = "closing it and reopening" if session.pane_id else "reopening"
            print(f"cs: {session.name} ({session.session_id}): {what} it on {account}")
            return 0
        switch.run(session, place(session.cwd, found), account, known[account], herdr, open_session)
    except (RuntimeError, repos.ConfigError) as e:
        print(f"cs: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str], config: Path = repos.CONFIG) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print("usage: cs [repo] [--as account]  start Claude in a repo, as a herdr workspace named after it\n"
              "                                 (in the picker, Alt+2… start it on the next accounts)\n"
              "       cs <repo> --run <line>  type <line> at the new tab's prompt instead of claude\n"
              "       cs --closed  reopen a closed Claude session, newest first, helpers hidden (Alt+2… on another account)\n"
              "       cs --switch <session> --as <account>  reopen a conversation, open or closed, on that account\n"
              "                     (<session>: an id, a name, or `here` for the agent's own session)\n"
              "       cs --sessions  list the sessions --switch knows: id, open or closed, repo, name\n"
              "       cs --accounts  list the accounts in this machine's config")
        return 0
    try:
        found = repos.load(config)
        known = accounts.load(config)
    except repos.ConfigError as e:
        print(f"cs: {e}", file=sys.stderr)
        return 1
    if argv and argv[0] == "--accounts":
        print("\n".join(known))
        return 0
    if argv and argv[0] == "--closed":
        return reopen(found, known)
    if argv and argv[0] == "--sessions":
        try:
            print(switch.listing(switch.all_sessions(herdr), found))
        except RuntimeError as e:
            print(f"cs: {e}", file=sys.stderr)
            return 1
        return 0
    account = None
    if "--as" in argv:
        i = argv.index("--as")
        if i + 1 >= len(argv) or argv[i + 1] not in known:
            print(f"cs: --as needs one of: {', '.join(known)}", file=sys.stderr)
            return 1
        account = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if argv and argv[0] in ("--switch", "--switch-now"):
        return switch_session(argv, account, found, known)
    # --run lets a desktop action (the Omarchy crash toast) start its own command
    # in a repo's herdr workspace instead of a loose terminal window.
    command = None
    if len(argv) == 3 and argv[1] == "--run":
        command = argv[2]
        argv = argv[:1]
    elif "--run" in argv:
        print("cs: --run needs a repo before it and one line after it", file=sys.stderr)
        return 1
    labels = list(found)
    if argv:
        label = match(labels, argv[0])
        if label is None:
            print(f"cs: no single repo matches {argv[0]!r}", file=sys.stderr)
            return 1
    else:
        picked = pick(labels, list(known))
        if picked is None:
            return 1
        label, chosen = picked
        account = account or chosen
    account = account or accounts.LOGIN
    try:
        if command is None:
            command = accounts.command(account, known[account])
        ensure_server()
        open_session(label, found[label], command)
    except (RuntimeError, repos.ConfigError) as e:
        print(f"cs: {e}", file=sys.stderr)
        return 1
    if os.environ.get("HERDR_ENV") != "1":
        show_herdr_window()
    return 0
