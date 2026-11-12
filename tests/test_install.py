import os
import subprocess
import tomllib
from pathlib import Path

import pytest

from test_agent_sessions import HERDR_STUB

REPO = Path(__file__).resolve().parents[1]


def _install(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    if not __import__("shutil").which("ansible-playbook"):
        pytest.skip("missing: ansible-playbook")
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True, exist_ok=True)
    (home / ".bashrc").touch()
    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    (stubs / "herdr").write_text(HERDR_STUB)
    (stubs / "herdr").chmod(0o755)
    env = dict(os.environ, HOME=str(home), PATH=f"{stubs}:{os.environ['PATH']}",
               ANSIBLE_LOCALHOST_WARNING="false", ANSIBLE_INVENTORY_UNPARSED_WARNING="false",
               ANSIBLE_LOCAL_TEMP=str(tmp_path / "tmp"), ANSIBLE_REMOTE_TEMP=str(tmp_path / "tmp"))
    return subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(REPO / "install.yml"), *extra],
                          capture_output=True, text=True, env=env, cwd=tmp_path)


def test_install_with_repo_folders_writes_the_config(tmp_path):
    done = _install(tmp_path, "-e", '{"agent_desk_repos_folders": ["~/work"]}')
    assert done.returncode == 0, done.stdout[-3000:]
    config = tmp_path / "home" / ".config" / "agent-desk" / "config.toml"
    assert tomllib.loads(config.read_text()) == {"repos": {"folders": ["~/work"]}}
    assert (tmp_path / "home" / ".local" / "bin" / "cs").is_symlink()


def test_install_without_a_repo_list_fails_and_says_how(tmp_path):
    done = _install(tmp_path)
    assert done.returncode != 0 and "agent_desk_repos_folders" in done.stdout
