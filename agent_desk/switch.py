"""`cs --switch <session> --as <account>`: reopen one Claude conversation on another account.

The session is named by its id (or the first 8+ characters of it), by its name (/rename,
Claude's title), or as `here` for the agent's own session (CLAUDE_CODE_SESSION_ID), whether a herdr pane runs it now or it was closed. An open one is closed
first, then resumed with `claude --resume` in a new tab of its repo's workspace, on the
account asked for. The work runs in a process of its own, so an agent may switch the very
session it runs in: its pane closes, and the conversation comes back on the other account.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from agent_desk import accounts
from agent_desk.closed import CACHE, ago, closed_sessions, place, read_transcript

PROJECTS = Path("~/.claude/projects")


@dataclass(frozen=True)
class Session:
    session_id: str
    cwd: Path
    name: str
    pane_id: str | None  # the herdr pane running it, None when closed


class NotFound(RuntimeError):
    pass


def open_agents(herdr) -> list[dict]:
    return [a for a in herdr("agent", "list").get("agents", [])
            if a.get("agent_session", {}).get("value")]


def transcript(session_id: str, projects: Path) -> Path | None:
    return next(iter(sorted(projects.expanduser().glob(f"*/{session_id}.jsonl"))), None)


def all_sessions(herdr, projects: Path = PROJECTS, limit: int = 200) -> list[Session]:
    """Open sessions first (in herdr's order), then closed ones, newest first."""
    projects = projects.expanduser()
    found: list[Session] = []
    agents = open_agents(herdr)
    for a in agents:
        sid = a["agent_session"]["value"]
        path = transcript(sid, projects)
        cwd, name = read_transcript(path) if path else (None, None)
        found.append(Session(sid, cwd or Path(a.get("cwd", ".")),
                             a.get("terminal_title_stripped") or name or sid, a["pane_id"]))
    open_ids = {s.session_id for s in found}
    for c in closed_sessions(projects, open_ids, limit=limit, cache_file=CACHE):
        found.append(Session(c.session_id, c.cwd, c.name, None))
    return found


def find(query: str, sessions: list[Session]) -> Session:
    """By id, then an id prefix of 8+ characters, then the exact name, then a unique part of a name."""
    tests = [lambda s: s.session_id == query,
             lambda s: len(query) >= 8 and s.session_id.startswith(query),
             lambda s: s.name == query,
             lambda s: query.lower() in s.name.lower()]
    for test in tests:
        hits = [s for s in sessions if test(s)]
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            listed = "\n".join(f"  {s.session_id}  {s.name}" for s in hits[:10])
            raise NotFound(f"{len(hits)} sessions match {query!r}; name one by its id:\n{listed}")
    raise NotFound(f"no session matches {query!r}; `cs --sessions` lists them")


def listing(sessions: list[Session], repos: dict[str, Path]) -> str:
    lines = []
    for s in sessions:
        state = "open  " if s.pane_id else "closed"
        lines.append(f"{s.session_id}  {state}  {place(s.cwd, repos):<24}  {s.name}")
    return "\n".join(lines)


def wait_closed(herdr, session_id: str, seconds: float = 10) -> None:
    for _ in range(int(seconds * 10)):
        if session_id not in {a["agent_session"]["value"] for a in open_agents(herdr)}:
            return
        time.sleep(0.1)
    raise RuntimeError(f"session {session_id} still runs {seconds:.0f}s after its pane was closed")


def run(session: Session, label: str, account: str, token_file: Path | None, herdr, open_session) -> None:
    """Close the session's pane if it has one, then resume it on the account."""
    command = accounts.command(account, token_file, f"claude --resume {session.session_id}")
    if session.pane_id:
        herdr("pane", "close", session.pane_id)
        wait_closed(herdr, session.session_id)
    open_session(label, session.cwd, command)


def detach(argv: list[str]) -> None:
    """Run `cs <argv>` in its own session, so closing the caller's pane doesn't kill it."""
    log = Path("~/.cache/agent-desk/switch.log").expanduser()
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as out:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve().parents[1] / "bin" / "cs"), *argv],
                         stdin=subprocess.DEVNULL, stdout=out, stderr=out, start_new_session=True)
