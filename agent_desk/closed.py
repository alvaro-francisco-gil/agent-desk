"""`cs --closed`: the Claude sessions closed most recently, across every repo, to reopen one.

A session is a transcript in ~/.claude/projects/<dir>/<session id>.jsonl. It counts as
closed when no herdr pane runs it. Sessions whose folder is gone (a deleted worktree)
can't be resumed and are left out, as are sessions with no prompt typed.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

LIMIT = 30


@dataclass(frozen=True)
class Closed:
    session_id: str
    cwd: Path
    name: str
    closed_at: float


def read_transcript(path: Path) -> tuple[Path | None, str | None]:
    """The session's folder and its name: the last /rename, else Claude's title, else the last prompt."""
    cwd = custom = ai = prompt = None
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if cwd is None and '"cwd":' in line:
                    cwd = json.loads(line).get("cwd")
                if '"type":"custom-title"' in line:
                    custom = json.loads(line).get("customTitle") or custom
                elif '"type":"ai-title"' in line:
                    ai = json.loads(line).get("aiTitle") or ai
                elif '"type":"last-prompt"' in line:
                    prompt = json.loads(line).get("lastPrompt") or prompt
    except (OSError, ValueError):
        return None, None
    name = custom or ai or prompt
    return (Path(cwd) if cwd else None), (" ".join(name.split()) if name else None)


def closed_sessions(projects: Path, open_ids: set[str], limit: int = LIMIT) -> list[Closed]:
    """Newest first: transcripts no herdr pane runs, with a prompt typed and a folder still on disk."""
    transcripts = sorted(projects.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    found: list[Closed] = []
    for path in transcripts:
        if path.stem in open_ids:
            continue
        cwd, name = read_transcript(path)
        if cwd is None or name is None or not cwd.is_dir():
            continue
        found.append(Closed(path.stem, cwd, name, path.stat().st_mtime))
        if len(found) >= limit:
            break
    return found


def ago(then: float, now: float | None = None) -> str:
    seconds = max(0, int((now if now is not None else time.time()) - then))
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return "just now"


def place(cwd: Path, repos: dict[str, Path]) -> str:
    """The repo label whose folder holds cwd (the deepest one), else the folder's own name."""
    best = None
    for label, path in repos.items():
        if cwd == path or path in cwd.parents:
            if best is None or len(path.parts) > len(repos[best].parts):
                best = label
    return best or cwd.name
