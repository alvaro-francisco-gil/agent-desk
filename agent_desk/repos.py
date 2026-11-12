"""Which repos `cs` offers on this machine: ~/.config/agent-desk/config.toml.

Exactly one of:

    [repos]
    command = "some-command"   # prints one `label<TAB>path` line per repo, in picker order
    folders = ["~/work"]       # each folder, then every git repo one or two levels inside it

The list belongs to the machine, never to this repo.
"""
from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

CONFIG = Path("~/.config/agent-desk/config.toml")


class ConfigError(RuntimeError):
    pass


def load(config: Path = CONFIG) -> dict[str, Path]:
    """Label → folder, in the order the picker shows them."""
    config = config.expanduser()
    if not config.is_file():
        raise ConfigError(f"{config} is missing; it says where this machine's repos are (see agent_desk/repos.py)")
    try:
        repos = tomllib.loads(config.read_text(encoding="utf-8")).get("repos", {})
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{config} is not valid TOML: {e}") from e
    command, folders = repos.get("command"), repos.get("folders")
    if bool(command) == bool(folders):
        raise ConfigError(f"{config}: set exactly one of repos.command and repos.folders")
    return from_command(command) if command else from_folders(folders)


def from_command(command: str) -> dict[str, Path]:
    done = subprocess.run(command, shell=True, capture_output=True, text=True)
    if done.returncode != 0:
        raise ConfigError(f"repos.command `{command}` failed: {done.stderr.strip()}")
    found: dict[str, Path] = {}
    for line in done.stdout.splitlines():
        if not line.strip():
            continue
        label, tab, path = line.partition("\t")
        if not tab:
            raise ConfigError(f"repos.command printed {line!r}, not label<TAB>path")
        found[label] = Path(path).expanduser()
    return found


def from_folders(folders: list[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}

    def add(label: str, path: Path) -> None:
        if label in found:
            raise ConfigError(f"two repos are both called {label!r}: {found[label]} and {path}")
        found[label] = path

    for folder in folders:
        root = Path(folder).expanduser()
        if not root.is_dir():
            raise ConfigError(f"repos.folders: {root} is not a folder")
        add(root.name, root)
        repos: list[Path] = []
        for child in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            if (child / ".git").exists():
                repos.append(child)
            else:
                repos += [g for g in sorted(child.iterdir()) if g.is_dir() and (g / ".git").exists()]
        for repo in sorted(repos, key=lambda p: str(p.relative_to(root)).lower()):
            add(str(repo.relative_to(root)), repo)
    return found
