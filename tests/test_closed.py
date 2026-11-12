import json
import os
from pathlib import Path

from agent_desk.closed import ago, closed_sessions, place, read_transcript


def transcript(projects: Path, session: str, cwd: Path, *entries: dict, mtime: float = 1000.0) -> Path:
    path = projects / "-dir" / f"{session}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "user", "cwd": str(cwd), "sessionId": session}, *entries]
    path.write_text("".join(json.dumps(e, separators=(",", ":")) + "\n" for e in lines), encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_name_prefers_rename_then_claude_title_then_last_prompt(tmp_path):
    p = transcript(tmp_path, "a", tmp_path,
                   {"type": "last-prompt", "lastPrompt": "fix\nthe  bug"},
                   {"type": "ai-title", "aiTitle": "Bug fix"},
                   {"type": "custom-title", "customTitle": "old"},
                   {"type": "custom-title", "customTitle": "bugfix"})
    assert read_transcript(p) == (tmp_path, "bugfix")
    p = transcript(tmp_path, "b", tmp_path, {"type": "last-prompt", "lastPrompt": "fix\nthe  bug"})
    assert read_transcript(p) == (tmp_path, "fix the bug")


def test_closed_skips_open_unnamed_and_gone_sessions_newest_first(tmp_path):
    projects, repo = tmp_path / "projects", tmp_path / "repo"
    repo.mkdir()
    named = {"type": "custom-title", "customTitle": "x"}
    transcript(projects, "old", repo, named, mtime=100)
    transcript(projects, "new", repo, named, mtime=300)
    transcript(projects, "open", repo, named, mtime=400)
    transcript(projects, "empty", repo, mtime=500)
    transcript(projects, "gone", tmp_path / "deleted-worktree", named, mtime=600)
    found = closed_sessions(projects, {"open"})
    assert [s.session_id for s in found] == ["new", "old"]
    assert closed_sessions(projects, {"open"}, limit=1)[0].session_id == "new"


def test_place_picks_the_deepest_repo_holding_the_folder(tmp_path):
    repos = {"githubs": tmp_path, "infra": tmp_path / "infra"}
    assert place(tmp_path / "infra" / ".claude" / "worktrees" / "w", repos) == "infra"
    assert place(tmp_path, repos) == "githubs"
    assert place(Path("/elsewhere/notes"), repos) == "notes"


def test_ago():
    assert ago(0, 30) == "just now"
    assert ago(0, 120) == "2m ago"
    assert ago(0, 7200) == "2h ago"
    assert ago(0, 3 * 86400) == "3d ago"
