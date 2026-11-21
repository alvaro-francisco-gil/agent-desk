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
