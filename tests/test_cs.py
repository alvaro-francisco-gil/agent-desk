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
