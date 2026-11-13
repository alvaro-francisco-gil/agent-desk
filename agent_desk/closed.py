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
# What each transcript has been read up to, so a large one is read once, not on every Alt+P.
CACHE = Path("~/.cache/agent-desk/transcripts.json").expanduser()


@dataclass(frozen=True)
class Closed:
    session_id: str
    cwd: Path
    name: str
    closed_at: float


def read_transcript(path: Path, cache: dict | None = None) -> tuple[Path | None, str | None]:
    """The session's folder and its name: the last /rename, else Claude's title, else the last prompt.

    Transcripts only grow, so with a cache (path -> what was read so far) only the lines
    added since the last call are read; a file shorter than what was read is read again.
    """
    key = str(path)
    state = (cache or {}).get(key)
    try:
        size = path.stat().st_size
        if not state or state.get("offset", 0) > size:
            state = {"offset": 0, "cwd": None, "custom": None, "ai": None, "prompt": None}
        with path.open("rb") as f:
            f.seek(state["offset"])
            data = f.read()
    except OSError:
        return None, None
    end = data.rfind(b"\n") + 1  # a line still being written waits for the next call
    for raw in data[:end].splitlines():
        line = raw.decode("utf-8", errors="replace")
        try:
            if state["cwd"] is None and '"cwd":' in line:
                state["cwd"] = json.loads(line).get("cwd")
            if '"type":"custom-title"' in line:
                state["custom"] = json.loads(line).get("customTitle") or state["custom"]
            elif '"type":"ai-title"' in line:
                state["ai"] = json.loads(line).get("aiTitle") or state["ai"]
            elif '"type":"last-prompt"' in line:
                state["prompt"] = json.loads(line).get("lastPrompt") or state["prompt"]
        except ValueError:
            continue
    state["offset"] += end
    if cache is not None:
        cache[key] = state
    name = state["custom"] or state["ai"] or state["prompt"]
    return (Path(state["cwd"]) if state["cwd"] else None), (" ".join(name.split()) if name else None)


def load_cache(cache_file: Path | None) -> dict:
    if cache_file is None:
        return {}
    try:
        cache = json.loads(cache_file.read_text(encoding="utf-8"))
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(cache_file: Path | None, cache: dict, transcripts: list[Path]) -> None:
    """Keep only transcripts still on disk; a failed write only costs speed next time."""
    if cache_file is None:
        return
    live = {str(p) for p in transcripts}
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({k: v for k, v in cache.items() if k in live}), encoding="utf-8")
        tmp.replace(cache_file)
    except OSError:
        pass


def closed_sessions(projects: Path, open_ids: set[str], limit: int = LIMIT,
                    cache_file: Path | None = None) -> list[Closed]:
    """Newest first: transcripts no herdr pane runs, with a prompt typed and a folder still on disk."""
    transcripts = sorted(projects.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    cache = load_cache(cache_file)
    found: list[Closed] = []
    for path in transcripts:
        if path.stem in open_ids:
            continue
        cwd, name = read_transcript(path, cache)
        if cwd is None or name is None or not cwd.is_dir():
            continue
        found.append(Closed(path.stem, cwd, name, path.stat().st_mtime))
        if len(found) >= limit:
            break
    save_cache(cache_file, cache, transcripts)
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
