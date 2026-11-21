import subprocess
import sys
from pathlib import Path

import pytest

from agent_desk import repos
from agent_desk.session import main, match


def config(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def git_repo(path: Path) -> Path:
    (path / ".git").mkdir(parents=True)
    return path


@pytest.fixture
def work(tmp_path) -> Path:
    root = tmp_path / "work"
    git_repo(root / "zeta")
    git_repo(root / "Alpha")
    git_repo(root / "client" / "app")
    (root / "client" / "notes").mkdir()
    (root / "scratch").mkdir()
    git_repo(root / ".hidden")
    return root


def test_folders_list_the_folder_then_its_repos_one_or_two_levels_down(tmp_path, work):
    found = repos.load(config(tmp_path, f'[repos]\nfolders = ["{work}"]\n'))
    assert list(found) == ["work", "Alpha", "client/app", "zeta"]
    assert found["work"] == work and found["client/app"] == work / "client" / "app"


def test_command_lines_become_the_list_in_order(tmp_path):
    script = tmp_path / "list"
    script.write_text("#!/bin/sh\nprintf 'githubs\\t/g\\ninfra\\t/g/infra\\n\\n'\n")
    script.chmod(0o755)
    found = repos.load(config(tmp_path, f'[repos]\ncommand = "{script}"\n'))
    assert found == {"githubs": Path("/g"), "infra": Path("/g/infra")}


@pytest.mark.parametrize(
    ("body", "error"),
    [
        (None, "is missing"),
        ("[repos]\n", "exactly one"),
        ('[repos]\ncommand = "x"\nfolders = ["/"]\n', "exactly one"),
        ("[repos\n", "not valid TOML"),
        ('[repos]\nfolders = ["/no/such/folder"]\n', "is not a folder"),
        ('[repos]\ncommand = "echo oops; exit 3"\n', "failed"),
        ('[repos]\ncommand = "echo no-tab"\n', "not label<TAB>path"),
    ],
)
def test_a_bad_or_missing_config_fails_loudly(tmp_path, body, error):
    path = config(tmp_path, body) if body is not None else tmp_path / "none.toml"
    with pytest.raises(repos.ConfigError, match=error):
        repos.load(path)


def test_two_repos_with_one_label_fail(tmp_path):
    git_repo(tmp_path / "a" / "x")
    git_repo(tmp_path / "b" / "x")
    with pytest.raises(repos.ConfigError, match="both called 'x'"):
        repos.load(config(tmp_path, f'[repos]\nfolders = ["{tmp_path / "a"}", "{tmp_path / "b"}"]\n'))


def test_match_prefers_exact_then_last_segment_then_unique_substring():
    labels = ["githubs", "client/app", "infra", "acme/ci", "acme/acme-apps"]
    assert match(labels, "infra") == "infra"
    assert match(labels, "app") == "client/app"
    assert match(labels, "inf") == "infra"
    assert match(labels, "acme") is None
    assert match(labels, "nothing") is None


def test_unknown_repo_fails_before_touching_herdr(tmp_path, work, capsys):
    assert main(["nothing"], config(tmp_path, f'[repos]\nfolders = ["{work}"]\n')) == 1
    assert "no single repo" in capsys.readouterr().err


def test_a_missing_config_fails_before_touching_herdr(tmp_path, capsys):
    assert main(["zeta"], tmp_path / "none.toml") == 1
    assert "is missing" in capsys.readouterr().err


def test_run_without_a_repo_or_line_fails_before_touching_herdr(tmp_path, work, capsys):
    path = config(tmp_path, f'[repos]\nfolders = ["{work}"]\n')
    assert main(["--run", "echo hi"], path) == 1
    assert main(["zeta", "--run"], path) == 1
    assert "--run needs a repo" in capsys.readouterr().err


def test_run_types_the_line_instead_of_claude(tmp_path, work, monkeypatch):
    import agent_desk.session as session

    opened = []
    monkeypatch.setattr(session, "ensure_server", lambda: None)
    monkeypatch.setattr(session, "open_session", lambda label, path, command: opened.append((label, path, command)))
    monkeypatch.setenv("HERDR_ENV", "1")
    assert main(["zeta", "--run", "echo hi"], config(tmp_path, f'[repos]\nfolders = ["{work}"]\n')) == 0
    assert opened == [("zeta", work / "zeta", "echo hi")]


def test_the_cs_entry_point_runs_through_a_symlink(tmp_path):
    link = tmp_path / "cs"
    link.symlink_to(Path(__file__).resolve().parents[1] / "bin" / "cs")
    done = subprocess.run([sys.executable, str(link), "--help"], capture_output=True, text=True)
    assert done.returncode == 0 and "usage: cs" in done.stdout


# ── Accounts ───────────────────────────────────────────────────────────────


def _opened(monkeypatch) -> list:
    import agent_desk.session as session

    opened = []
    monkeypatch.setattr(session, "ensure_server", lambda: None)
    monkeypatch.setattr(session, "open_session", lambda label, path, command: opened.append((label, path, command)))
    monkeypatch.setenv("HERDR_ENV", "1")
    return opened


def test_without_accounts_only_the_login_one_is_offered(tmp_path, work):
    from agent_desk import accounts

    assert accounts.load(config(tmp_path, f'[repos]\nfolders = ["{work}"]\n')) == {"login": None}


def test_accounts_come_after_login_in_config_order(tmp_path, work):
    from agent_desk import accounts

    body = f'[repos]\nfolders = ["{work}"]\n[accounts.b]\ntoken_file = "/t/b.json"\n[accounts.a]\ntoken_file = "/t/a.json"\n'
    assert list(accounts.load(config(tmp_path, body))) == ["login", "b", "a"]


@pytest.mark.parametrize(("entry", "error"), [("[accounts.login]\ntoken_file = \"/x\"\n", "reserved"),
                                               ("[accounts.x]\n", "needs a token_file")])
def test_a_bad_account_fails_loudly(tmp_path, work, capsys, entry, error):
    assert main(["zeta"], config(tmp_path, f'[repos]\nfolders = ["{work}"]\n' + entry)) == 1
    assert error in capsys.readouterr().err


def test_as_starts_claude_with_that_accounts_token_read_from_its_file(tmp_path, work, monkeypatch):
    token = tmp_path / "second.json"
    token.write_text('{"token": "sk-secret"}')
    opened = _opened(monkeypatch)
    body = f'[repos]\nfolders = ["{work}"]\n[accounts.second]\ntoken_file = "{token}"\n'
    assert main(["zeta", "--as", "second"], config(tmp_path, body)) == 0
    (label, _, command), = opened
    assert label == "zeta" and "sk-secret" not in command
    assert command.startswith("CLAUDE_ACCOUNT=second ") and command.endswith(" claude")
    done = subprocess.run(["bash", "-c", command.removesuffix(" claude") + ' printenv CLAUDE_CODE_OAUTH_TOKEN'],
                          capture_output=True, text=True)
    assert done.stdout.strip() == "sk-secret"


def test_as_login_or_no_flag_is_plain_claude(tmp_path, work, monkeypatch):
    opened = _opened(monkeypatch)
    path = config(tmp_path, f'[repos]\nfolders = ["{work}"]\n')
    assert main(["zeta"], path) == 0 and main(["zeta", "--as", "login"], path) == 0
    assert [c for _, _, c in opened] == ["claude", "claude"]


def test_unknown_account_or_missing_token_fails_before_touching_herdr(tmp_path, work, monkeypatch, capsys):
    opened = _opened(monkeypatch)
    body = f'[repos]\nfolders = ["{work}"]\n[accounts.second]\ntoken_file = "{tmp_path / "none.json"}"\n'
    assert main(["zeta", "--as", "nobody"], config(tmp_path, body)) == 1
    assert main(["zeta", "--as", "second"], config(tmp_path, body)) == 1
    assert opened == []
    err = capsys.readouterr().err
    assert "--as needs one of: login, second" in err and "is missing" in err


def test_the_picker_starts_alt_2_on_the_second_account(tmp_path, work, monkeypatch):
    import agent_desk.session as session

    token = tmp_path / "second.json"
    token.write_text('{"token": "t"}')
    seen = {}

    def fzf(argv, input, stdout, text):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="alt-2\nzeta\n")

    monkeypatch.setattr(session.shutil, "which", lambda _: "/usr/bin/fzf")
    monkeypatch.setattr(session.subprocess, "run", fzf)
    opened = _opened(monkeypatch)
    body = f'[repos]\nfolders = ["{work}"]\n[accounts.second]\ntoken_file = "{token}"\n'
    assert main([], config(tmp_path, body)) == 0
    assert "alt+2: second" in " ".join(seen["argv"])
    assert opened[0][2].startswith("CLAUDE_ACCOUNT=second ")


# ── Switching a conversation to another account ────────────────────────────


from agent_desk import switch  # noqa: E402


def _s(sid: str, name: str, pane: str | None = None, cwd: Path = Path("/r")) -> switch.Session:
    return switch.Session(sid, cwd, name, pane)


def test_find_takes_id_then_prefix_then_name_then_part_of_a_name():
    sessions = [_s("aaaaaaaa-1111", "spend-credits", "w1:p1"), _s("bbbbbbbb-2222", "calendar")]
    assert switch.find("bbbbbbbb-2222", sessions).name == "calendar"
    assert switch.find("aaaaaaaa", sessions).name == "spend-credits"
    assert switch.find("calendar", sessions).session_id == "bbbbbbbb-2222"
    assert switch.find("SPEND", sessions).session_id == "aaaaaaaa-1111"


def test_find_refuses_a_short_prefix_an_unknown_name_and_two_matches():
    sessions = [_s("aaaaaaaa-1", "plan one"), _s("aaaaaaaa-2", "plan two")]
    with pytest.raises(switch.NotFound, match="no session matches"):
        switch.find("aaa", [_s("aaaaaaaa-1", "x")])
    with pytest.raises(switch.NotFound, match="2 sessions match 'plan'"):
        switch.find("plan", sessions)


def test_all_sessions_lists_open_ones_by_pane_then_closed_ones(tmp_path):
    projects = tmp_path / "projects" / "-r"
    projects.mkdir(parents=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    for sid, title in (("open-1", "running"), ("shut-1", "finished")):
        (projects / f"{sid}.jsonl").write_text(
            f'{{"cwd": "{repo}"}}\n{{"type":"custom-title","customTitle":"{title}"}}\n')

    def herdr(*args):
        return {"agents": [{"pane_id": "w1:p1", "terminal_title_stripped": "running", "cwd": str(repo),
                            "agent_session": {"value": "open-1"}}]}

    found = switch.all_sessions(herdr, tmp_path / "projects")
    assert [(s.session_id, s.pane_id, s.cwd) for s in found] == [("open-1", "w1:p1", repo), ("shut-1", None, repo)]


def test_run_closes_an_open_session_then_resumes_it_on_the_account(tmp_path):
    token = tmp_path / "t.json"
    token.write_text('{"token": "x"}')
    calls, opened, running = [], [], {"value": True}

    def herdr(*args):
        calls.append(args)
        if args[:2] == ("pane", "close"):
            running["value"] = False
        agents = [{"pane_id": "w1:p1", "agent_session": {"value": "sid-1"}}] if running["value"] else []
        return {"agents": agents}

    switch.run(_s("sid-1", "n", "w1:p1", tmp_path), "repo", "second", token, herdr,
               lambda label, cwd, command: opened.append((label, cwd, command)))
    assert ("pane", "close", "w1:p1") in calls
    (label, cwd, command), = opened
    assert (label, cwd) == ("repo", tmp_path)
    assert command.startswith("CLAUDE_ACCOUNT=second ") and command.endswith(" claude --resume sid-1")


def test_run_on_the_login_account_is_plain_resume_and_a_closed_one_closes_nothing(tmp_path):
    calls, opened = [], []
    switch.run(_s("sid-2", "n", None, tmp_path), "repo", "login", None,
               lambda *a: calls.append(a) or {}, lambda *a: opened.append(a))
    assert calls == [] and opened == [("repo", tmp_path, "claude --resume sid-2")]


def test_switch_checks_the_account_before_closing_anything(tmp_path, work, monkeypatch, capsys):
    import agent_desk.session as session

    monkeypatch.setattr(session, "ensure_server", lambda: None)
    monkeypatch.setattr(switch, "all_sessions", lambda herdr: [_s("sid-1", "spend", "w1:p1")])
    detached = []
    monkeypatch.setattr(switch, "detach", detached.append)
    body = f'[repos]\nfolders = ["{work}"]\n[accounts.second]\ntoken_file = "{tmp_path / "none.json"}"\n'
    path = config(tmp_path, body)
    assert main(["--switch", "spend"], path) == 1
    assert main(["--switch", "spend", "--as", "second"], path) == 1
    assert detached == []
    assert "usage: cs --switch" in capsys.readouterr().err
    assert main(["--switch", "spend", "--as", "login"], path) == 0
    assert detached == [["--switch-now", "sid-1", "--as", "login"]]
    assert "closing it and reopening it on login" in capsys.readouterr().out


def test_alt_p_reopens_on_the_account_its_key_names(tmp_path, work, monkeypatch):
    import agent_desk.session as session

    token = tmp_path / "second.json"
    token.write_text('{"token": "t"}')
    monkeypatch.setattr(session, "closed_sessions",
                        lambda *a, **k: [__import__("agent_desk.closed", fromlist=["Closed"]).Closed("sid-9", work / "zeta", "old", 0.0)])
    monkeypatch.setattr(session, "open_ids", lambda: set())
    monkeypatch.setattr(session.shutil, "which", lambda _: "/usr/bin/fzf")
    monkeypatch.setattr(session.subprocess, "run",
                        lambda argv, input, stdout, text: subprocess.CompletedProcess(argv, 0, stdout="alt-2\n0\tx\n"))
    opened = _opened(monkeypatch)
    body = f'[repos]\nfolders = ["{work}"]\n[accounts.second]\ntoken_file = "{token}"\n'
    assert main(["--closed"], config(tmp_path, body)) == 0
    assert opened[0][0] == "zeta" and opened[0][2].endswith("claude --resume sid-9")
    assert opened[0][2].startswith("CLAUDE_ACCOUNT=second ")


def test_here_is_the_callers_own_session(tmp_path, work, monkeypatch, capsys):
    import agent_desk.session as session

    monkeypatch.setattr(session, "ensure_server", lambda: None)
    monkeypatch.setattr(switch, "all_sessions", lambda herdr: [_s("sid-1", "a", "w1:p1"), _s("sid-2", "b", "w1:p2")])
    detached = []
    monkeypatch.setattr(switch, "detach", detached.append)
    path = config(tmp_path, f'[repos]\nfolders = ["{work}"]\n')
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "sid-2")
    assert main(["--switch", "here", "--as", "login"], path) == 0
    assert detached == [["--switch-now", "sid-2", "--as", "login"]]
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    assert main(["--switch", "here", "--as", "login"], path) == 1
    assert "only works from inside" in capsys.readouterr().err
