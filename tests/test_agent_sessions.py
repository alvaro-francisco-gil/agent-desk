"""tasks/agent_sessions.yml and the scripts it installs.

The play runs against a throwaway $HOME with a stub `herdr`; skipped where
ansible-playbook, jq or git are missing.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import threading
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TASKS = REPO / "tasks" / "agent_sessions.yml"
FILES = REPO / "files"
STATUSLINE = FILES / "claude-statusline.sh"
SECRET_DENIES = json.loads((FILES / "claude-secret-denies.json").read_text())
NEW_TERMINAL = FILES / "herdr" / "new-terminal.py"
RENAME = FILES / "herdr" / "rename.bash"
COPY_PANE = FILES / "herdr" / "copy-pane.sh"
PAUSED = FILES / "herdr" / "paused" / "paused.py"
SOURCE_RENAME = (
    "[[ -f ~/.local/share/herdr-rename.bash ]] && source ~/.local/share/herdr-rename.bash"
)
ABOVE = [{"token": "$heading_above", "dim": True}]
BELOW = [{"token": "$heading_below", "dim": True}]

# Does what `herdr integration install claude` does: write the hook, add a SessionStart hook.
# `herdr plugin link` writes the registry.
HERDR_STUB = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
if sys.argv[1:3] == ["plugin", "link"]:
    registry = Path(os.environ["HOME"]) / ".config" / "herdr" / "plugins.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps([{"plugin_root": sys.argv[3]}]))
    sys.exit()
assert sys.argv[1:] == ["integration", "install", "claude"], sys.argv
claude = Path(os.environ["HOME"]) / ".claude"
(claude / "hooks").mkdir(parents=True, exist_ok=True)
(claude / "hooks" / "herdr-agent-state.sh").write_text("#!/bin/bash\\n")
settings = claude / "settings.json"
data = json.loads(settings.read_text()) if settings.exists() else {}
hook = {"type": "command", "command": "herdr-hook"}
data.setdefault("hooks", {})["SessionStart"] = [{"hooks": [hook]}]
settings.write_text(json.dumps(data))
"""


def _need(*tools):
    missing = [t for t in tools if not shutil.which(t)]
    if missing:
        pytest.skip(f"missing: {', '.join(missing)}")


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    (home / ".bashrc").write_text("# mine\n")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    (stubs / "herdr").write_text(HERDR_STUB)
    (stubs / "herdr").chmod(0o755)
    return home


def _play(home: Path, *extra: str) -> dict:
    """Run the tasks against localhost with HOME=home; returns the localhost recap counts."""
    _need("ansible-playbook")
    play = home.parent / "play.yml"
    play.write_text(
        "- hosts: localhost\n  connection: local\n  gather_facts: false\n"
        f"  vars: {{agent_desk_home: '{home}', agent_desk_dir: '{REPO}'}}\n"
        f"  tasks:\n    - ansible.builtin.include_tasks: '{TASKS}'\n"
    )
    env = dict(
        os.environ,
        HOME=str(home),
        PATH=f"{home.parent / 'bin'}:{os.environ['PATH']}",
        # Core's default callback, and no collections: CI installs ansible-core only.
        ANSIBLE_STDOUT_CALLBACK="default",
        ANSIBLE_COLLECTIONS_PATH=str(home.parent / "no-collections"),
        ANSIBLE_NOCOLOR="1",
        ANSIBLE_LOCALHOST_WARNING="false",
        ANSIBLE_INVENTORY_UNPARSED_WARNING="false",
        ANSIBLE_LOCAL_TEMP=str(home.parent / "tmp"),
        ANSIBLE_REMOTE_TEMP=str(home.parent / "tmp"),
    )
    done = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(play), *extra],
        capture_output=True,
        text=True,
        env=env,
        cwd=home.parent,  # away from the repo's ansible.cfg
    )
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
    recap = re.search(r"^localhost\s*:\s*(.*)$", done.stdout, re.MULTILINE)
    assert recap, done.stdout[-3000:]
    return {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", recap.group(1))}


def test_check_mode_on_a_fresh_home_succeeds_and_writes_nothing(home):
    _play(home, "--check")
    assert not (home / ".claude").exists()
    assert not (home / ".config" / "herdr").exists()
    assert not (home / ".local" / "share" / "herdr-rename.bash").exists()
    assert (home / ".bashrc").read_text() == "# mine\n"


def test_fresh_home_gets_every_piece(home):
    _play(home)
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert settings["statusLine"] == {"type": "command", "command": "~/.claude/statusline.sh"}
    assert settings["autoCompactWindow"] == 450000
    assert settings["preferredNotifChannel"] == "notifications_disabled"
    assert settings["viewMode"] == "focus"
    assert settings["model"] == "opus"
    assert settings["permissions"] == {"deny": SECRET_DENIES}
    assert settings["hooks"]["SessionStart"]
    assert os.access(home / ".claude" / "statusline.sh", os.X_OK)
    herdr = tomllib.loads((home / ".config" / "herdr" / "config.toml").read_text())
    assert herdr["ui"]["toast"]["delivery"] == "off"
    assert herdr["ui"]["sound"]["enabled"] is False
    assert herdr["ui"]["sidebar"]["agents"]["rows"] == [ABOVE, ["pane"], BELOW]
    assert herdr["keys"]["command"] == [
        {
            "key": "alt+enter",
            "type": "shell",
            "command": f"{home}/.local/bin/herdr-new-terminal",
        },
        {
            "key": "alt+n",
            "type": "popup",
            "command": f"{home}/.local/bin/cs",
            "width": "60%",
            "height": "60%",
        },
        {
            "key": "alt+p",
            "type": "popup",
            "command": f"{home}/.local/bin/cs --closed",
            "width": "80%",
            "height": "60%",
        },
        {
            "key": "alt+w",
            "type": "plugin_action",
            "command": "workstation.paused.close",
            "description": "close this tab and go to the next active agent",
        },
        {
            "key": "alt+s",
            "type": "plugin_action",
            "command": "workstation.paused.toggle",
            "description": "pause or bring back this agent",
        },
    ]
    plugin = home / ".local" / "share" / "herdr-paused"
    assert (plugin / "herdr-plugin.toml").exists() and (plugin / "paused.py").exists()
    registry = json.loads((home / ".config" / "herdr" / "plugins.json").read_text())
    assert registry == [{"plugin_root": str(plugin)}]
    assert os.access(home / ".local" / "bin" / "herdr-new-terminal", os.X_OK)
    assert os.access(home / ".local" / "bin" / "herdr-copy-pane", os.X_OK)
    assert (home / ".local" / "share" / "herdr-rename.bash").exists()
    assert (home / ".bashrc").read_text().splitlines() == ["# mine", SOURCE_RENAME]
    assert os.readlink(home / ".local" / "bin" / "cs") == str(REPO / "bin" / "cs")


def test_existing_config_is_kept_and_a_second_run_changes_nothing(home):
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text(
        json.dumps(
            {
                "theme": "dark",
                "model": "sonnet",
                "hooks": {"Stop": ["mine"]},
                "permissions": {
                    "allow": ["Bash(ls *)"],
                    "deny": ["Read(!*.example)", "Bash(rm -rf *)", SECRET_DENIES[0]],
                },
            }
        )
    )
    (home / ".config" / "herdr").mkdir()
    (home / ".config" / "herdr" / "config.toml").write_text(
        '[keys]\nprefix = "ctrl+space"\n\n[ui]\naccent = "blue"\n'
    )
    _play(home)
    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert settings["theme"] == "dark" and settings["hooks"]["Stop"] == ["mine"]
    assert settings["model"] == "sonnet" and settings["viewMode"] == "focus"
    assert "statusLine" in settings and "SessionStart" in settings["hooks"]
    assert settings["permissions"] == {
        "allow": ["Bash(ls *)"],
        "deny": ["Bash(rm -rf *)", *SECRET_DENIES],
    }
    herdr = tomllib.loads((home / ".config" / "herdr" / "config.toml").read_text())
    assert herdr["keys"]["prefix"] == "ctrl+space" and herdr["ui"]["accent"] == "blue"
    assert herdr["ui"]["toast"]["delivery"] == "off"
    assert [c["key"] for c in herdr["keys"]["command"]] == [
        "alt+enter",
        "alt+n",
        "alt+p",
        "alt+w",
        "alt+s",
    ]
    assert _play(home)["changed"] == 0


# The settings files/herdr/agent-sessions.toml adds, as they read once merged.
AGENT_SESSIONS = {
    "toast": {"delivery": "off"},
    "rows": {"claude": [ABOVE, ["state_icon", "terminal_title_stripped"], BELOW]},
}


def _herdr_ui(config: Path) -> dict:
    ui = tomllib.loads(config.read_text())["ui"]
    return {"toast": ui["toast"], "rows": ui["sidebar"]["agents"]["rows_by_agent"]}


@pytest.mark.parametrize(
    ("existing", "kept"),
    [
        (
            '[ui.toast]\nposition = "top"\ndelivery = "terminal"\n\n'
            '[keys]\nprefix = "ctrl+space"\n',
            {"toast": {"position": "top"}},
        ),
        (
            '[ui.sidebar.agents.rows_by_agent]\ncodex = [["state_icon"]]\n',
            {"rows": {"codex": [["state_icon"]]}},
        ),
        (
            '[ui.toast] # mine\nposition = "top"\n[ui.sidebar.agents.rows_by_agent]\n'
            'claude = [["state_icon"]]\ncodex = [["state_icon"]]\n',
            {"toast": {"position": "top"}, "rows": {"codex": [["state_icon"]]}},
        ),
    ],
    ids=["toast-table", "rows-table", "both-tables"],
)
def test_tables_already_in_the_herdr_config_are_updated_not_redeclared(home, existing, kept):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    config.write_text(existing)
    assert _play(home, "--check")["changed"] >= 1
    assert config.read_text() == existing
    _play(home)
    ui = _herdr_ui(config)
    for table, want in AGENT_SESSIONS.items():
        assert ui[table] == {**kept.get(table, {}), **want}
    if "[keys]" in existing:
        assert tomllib.loads(config.read_text())["keys"]["prefix"] == "ctrl+space"
    assert _play(home)["changed"] == 0


def test_multi_line_values_in_the_tables_are_kept_whole(home):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    config.write_text(
        '[ui.toast]\nnote = """\n[fake]\n"""\ndelivery = "terminal"\n\n'
        '# how I bind keys\n[keys]\nprefix = "ctrl+space"\n\n'
        "[ui.sidebar.agents.rows_by_agent]\n"
        'claude = [\n  ["state_icon"],\n]\ncodex = [\n  ["state_icon"],\n  ["name"],\n]\n'
    )
    _play(home)
    text = config.read_text()
    herdr = tomllib.loads(text)
    assert herdr["ui"]["toast"] == {"note": "[fake]\n", "delivery": "off"}
    assert herdr["ui"]["sidebar"]["agents"]["rows_by_agent"] == {
        **AGENT_SESSIONS["rows"],
        "codex": [["state_icon"], ["name"]],
    }
    assert herdr["keys"]["prefix"] == "ctrl+space"
    assert "\n# how I bind keys\n[keys]\n" in text
    assert _play(home)["changed"] == 0


def test_a_key_added_to_a_table_goes_after_its_last_key_not_the_next_comment(home):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    config.write_text(
        '[ui.toast]\nposition = [\n  "top",\n]\n\n# how I bind keys\n[keys]\nprefix = "x"\n'
    )
    _play(home)
    assert config.read_text().startswith(
        '[ui.toast]\nposition = [\n  "top",\n]\ndelivery = "off"\n\n# how I bind keys\n'
    )


def test_the_block_earlier_applies_wrote_becomes_plain_tables(home):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    block = (FILES / "herdr" / "agent-sessions.toml").read_text().strip()
    config.write_text(
        '[ui]\naccent = "blue"\n'
        f"# BEGIN homelab agent-sessions\n{block}\n# END homelab agent-sessions\n"
    )
    _play(home)
    assert "homelab agent-sessions" not in config.read_text()
    assert _herdr_ui(config) == AGENT_SESSIONS
    assert tomllib.loads(config.read_text())["ui"]["accent"] == "blue"
    assert _play(home)["changed"] == 0


def test_a_table_defined_another_way_fails_and_leaves_the_config_alone(home):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    existing = '[ui]\ntoast = { delivery = "terminal" }\n'
    config.write_text(existing)
    with pytest.raises(AssertionError, match=r"\[ui\.toast\]"):
        _play(home)
    assert config.read_text() == existing


OMARCHY_KEYS = """[keys]
prefix = "ctrl+space"
split_horizontal = ["prefix+h", "alt+enter"]
close_tab = "prefix+k"
new_workspace = "prefix+shift+c"
previous_workspace = ["prefix+shift+p", "alt+up"]
next_workspace = ["prefix+shift+n", "alt+down"]
"""


def test_omarchy_keys_are_rebound_and_hand_edited_keys_kept(home):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    config.write_text(OMARCHY_KEYS + 'rename_tab = "prefix+r"\n')
    _play(home)
    keys = tomllib.loads(config.read_text())["keys"]
    assert keys["close_tab"] == "prefix+k"
    assert keys["split_horizontal"] == "prefix+h"
    assert keys["new_workspace"] == "prefix+shift+c"
    assert keys["previous_workspace"] == "prefix+shift+p"
    assert keys["next_workspace"] == "prefix+shift+n"
    assert keys["previous_agent"] == "alt+up" and keys["next_agent"] == "alt+down"
    assert keys["rename_tab"] == "prefix+r"
    assert _play(home)["changed"] == 0

    config.write_text(OMARCHY_KEYS.replace('"prefix+k"', '["prefix+k", "alt+w"]'))
    _play(home)
    assert tomllib.loads(config.read_text())["keys"]["close_tab"] == "prefix+k"

    config.write_text(OMARCHY_KEYS.replace('"prefix+k"', '"prefix+q"'))
    _play(home)
    keys = tomllib.loads(config.read_text())["keys"]
    assert keys["close_tab"] == "prefix+q"


def test_a_hand_bound_split_is_kept(home):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    config.write_text(OMARCHY_KEYS.replace('"alt+enter"]', '"alt+enter", "alt+x"]'))
    _play(home)
    keys = tomllib.loads(config.read_text())["keys"]
    assert keys["split_horizontal"] == ["prefix+h", "alt+enter", "alt+x"]
    assert [command["key"] for command in keys["command"]] == ["alt+n", "alt+p", "alt+w", "alt+s"]
    assert _play(home)["changed"] == 0


def test_alt_enter_is_dropped_from_the_block_once_bound_by_hand(home):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    config.write_text(OMARCHY_KEYS)
    _play(home)
    keys = tomllib.loads(config.read_text())["keys"]
    assert [command["key"] for command in keys["command"]] == [
        "alt+enter",
        "alt+n",
        "alt+p",
        "alt+w",
        "alt+s",
    ]

    config.write_text(
        config.read_text().replace('"prefix+shift+c"', '["prefix+shift+c", "alt+enter"]')
    )
    _play(home)
    keys = tomllib.loads(config.read_text())["keys"]
    assert keys["new_workspace"] == ["prefix+shift+c", "alt+enter"]
    assert [command["key"] for command in keys["command"]] == ["alt+n", "alt+p", "alt+w", "alt+s"]
    assert _play(home)["changed"] == 0


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        (
            (
                'next_workspace = ["prefix+shift+n", "alt+down"]\n',
                'next_workspace = ["prefix+shift+n", "alt+down"]\nprevious_agent = "alt+k"\n',
            ),
            {
                "previous_workspace": ["prefix+shift+p", "alt+up"],
                "previous_agent": "alt+k",
                "next_workspace": "prefix+shift+n",
                "next_agent": "alt+down",
            },
        ),
        (
            (
                'next_workspace = ["prefix+shift+n", "alt+down"]\n',
                'next_workspace = ["prefix+shift+n", "alt+down"]\nnext_agent = "alt+j"\n',
            ),
            {
                "previous_workspace": "prefix+shift+p",
                "previous_agent": "alt+up",
                "next_workspace": ["prefix+shift+n", "alt+down"],
                "next_agent": "alt+j",
            },
        ),
        (
            ('"alt+down"]', '"alt+j"]'),
            {
                "previous_workspace": "prefix+shift+p",
                "previous_agent": "alt+up",
                "next_workspace": ["prefix+shift+n", "alt+j"],
                "next_agent": None,
            },
        ),
        (
            ('"alt+up"]', '"alt+up", "alt+k"]'),
            {
                "previous_workspace": ["prefix+shift+p", "alt+up", "alt+k"],
                "previous_agent": None,
                "next_workspace": "prefix+shift+n",
                "next_agent": "alt+down",
            },
        ),
    ],
    ids=[
        "previous-agent-set",
        "next-agent-set",
        "next-workspace-edited",
        "previous-workspace-edited",
    ],
)
def test_each_alt_arrow_moves_on_its_own_and_never_duplicates_a_key(home, edit, expected):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    config.write_text(OMARCHY_KEYS.replace(*edit))
    _play(home)
    keys = tomllib.loads(config.read_text())["keys"]
    assert {key: keys.get(key) for key in expected} == expected
    assert _play(home)["changed"] == 0


@pytest.mark.parametrize(
    "spelling", ['  {key} = "alt+k"', '"{key}" = "alt+k"', "'{key}' = \"alt+k\""]
)
@pytest.mark.parametrize(
    ("key", "workspace"),
    [("previous_agent", "previous_workspace"), ("next_agent", "next_workspace")],
)
def test_an_agent_key_in_any_toml_spelling_is_kept(home, spelling, key, workspace):
    (home / ".config" / "herdr").mkdir()
    config = home / ".config" / "herdr" / "config.toml"
    config.write_text(OMARCHY_KEYS + spelling.format(key=key) + "\n")
    _play(home)
    keys = tomllib.loads(config.read_text())["keys"]
    assert keys[key] == "alt+k"
    assert isinstance(keys[workspace], list)


FOOT = "[cursor]\nstyle=beam\n\n[text-bindings]\n\\x1b[13;2u=Shift+Return\n"
GHOSTTY = "keybind = shift+enter=csi:13;2u\n"
FOOT_RENAME = "\\x2frename\\x20=Mod1+r"
GHOSTTY_RENAME = "keybind = alt+r=text:/rename\\x20"


def _terminals(home: Path, foot: str = FOOT, ghostty: str = GHOSTTY) -> tuple[Path, Path]:
    (home / ".config" / "foot").mkdir(parents=True, exist_ok=True)
    (home / ".config" / "ghostty").mkdir(parents=True, exist_ok=True)
    foot_ini = home / ".config" / "foot" / "foot.ini"
    ghostty_config = home / ".config" / "ghostty" / "config"
    foot_ini.write_text(foot)
    ghostty_config.write_text(ghostty)
    return foot_ini, ghostty_config


def test_keybindings_are_installed_once_and_hand_made_ones_kept(home):
    _play(home)
    keybindings = home / ".claude" / "keybindings.json"
    assert json.loads(keybindings.read_text())["bindings"] == [
        {"context": "Scroll", "bindings": {"home": "scroll:top", "end": "scroll:bottom"}}
    ]

    keybindings.write_text('{"bindings": []}\n')
    assert _play(home)["changed"] == 0
    assert keybindings.read_text() == '{"bindings": []}\n'


def test_alt_r_types_rename_in_both_terminals(home):
    foot_ini, ghostty_config = _terminals(home)
    _play(home)
    assert foot_ini.read_text().splitlines()[4] == FOOT_RENAME
    assert ghostty_config.read_text().splitlines() == [GHOSTTY.strip(), GHOSTTY_RENAME]
    assert _play(home)["changed"] == 0


@pytest.mark.parametrize(
    ("foot_line", "ghostty_line"),
    [
        ("\\x1b[1;3r=Mod1+r", "keybind = alt+r=reload_config"),
        ("\\x1b[1;3r=Alt+r", "keybind = opt+r=reload_config"),
        ("\\x1b[1;3r=Mod1+r Control+x", "keybind = global:alt+r=reload_config"),
    ],
    ids=["mod1", "alias", "several-combos-or-prefixed"],
)
def test_a_hand_bound_alt_r_is_kept(home, foot_line, ghostty_line):
    foot = FOOT + foot_line + "\n"
    ghostty = GHOSTTY + ghostty_line + "\n"
    foot_ini, ghostty_config = _terminals(home, foot, ghostty)
    _play(home)
    assert foot_ini.read_text() == foot
    assert ghostty_config.read_text() == ghostty


def test_a_foot_ini_without_text_bindings_is_left_alone(home):
    foot = "[key-bindings]\nscrollback-up-page=Shift+Page_Up\n"
    foot_ini, ghostty_config = _terminals(home, foot=foot)
    _play(home)
    assert foot_ini.read_text() == foot
    assert ghostty_config.read_text().endswith(GHOSTTY_RENAME + "\n")


def test_only_the_terminal_that_exists_is_changed(home):
    foot_ini, _ = _terminals(home)
    shutil.rmtree(home / ".config" / "ghostty")
    _play(home)
    assert FOOT_RENAME in foot_ini.read_text()
    assert not (home / ".config" / "ghostty").exists()


def test_missing_terminal_configs_are_skipped(home):
    _play(home)
    assert not (home / ".config" / "foot").exists()
    assert not (home / ".config" / "ghostty").exists()


# ── Alt+Enter terminal and /rename ─────────────────────────────────────────

# Answers `herdr` with the reply stored for its first two arguments, empty if none, and
# logs every call; HERDR_REPLIES and HERDR_CALLS name the two files.
HERDR_RECORDER = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["HERDR_CALLS"], "a") as calls:
    calls.write(json.dumps(sys.argv[1:]) + "\\n")
replies = json.loads(open(os.environ["HERDR_REPLIES"]).read())
if sys.argv[1:3] == ["pane", "read"]:
    print(os.environ.get("HERDR_READ_TEXT", ""))
reply = replies.get(" ".join(sys.argv[1:3]))
if reply is not None:
    print(json.dumps(reply))
"""


@pytest.fixture
def recorder(tmp_path):
    stubs = tmp_path / "recorder"
    stubs.mkdir()
    (stubs / "herdr").write_text(HERDR_RECORDER)
    # What reaches the clipboard and the notifications, beside the herdr calls.
    (stubs / "wl-copy").write_text('#!/bin/sh\ncat > "$HERDR_CALLS.clipboard"\n')
    # CLIPBOARD_HANG makes it hang like a stuck compositor.
    (stubs / "wl-paste").write_text(
        '#!/bin/sh\n[ -n "$CLIPBOARD_HANG" ] && exec sleep 30\nprintf %s "$CLIPBOARD_TEXT"\n'
    )
    (stubs / "notify-send").write_text('#!/bin/sh\necho "$@" >> "$HERDR_CALLS.notified"\n')
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    calls = tmp_path / "calls.jsonl"

    def run(argv: list[str], replies: dict, **env: str) -> tuple[subprocess.CompletedProcess, list]:
        (tmp_path / "replies.json").write_text(json.dumps(replies))
        calls.write_text("")
        base = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            env={
                **base,
                "PATH": f"{stubs}:{os.environ['PATH']}",
                "HOME": str(tmp_path),
                "HERDR_REPLIES": str(tmp_path / "replies.json"),
                "HERDR_CALLS": str(calls),
                **env,
            },
        )
        return done, [json.loads(line) for line in calls.read_text().splitlines()]

    return run


def _pane(pane_id: str, focused: bool = False) -> dict:
    workspace = pane_id.split(":")[0]
    return {
        "pane_id": pane_id,
        "workspace_id": workspace,
        "cwd": f"/{workspace}",
        "focused": focused,
    }


def _new_terminal_replies(panes: list[dict], workspaces: list[dict] | None = None) -> dict:
    return {
        "pane list": {"result": {"panes": panes}},
        "workspace list": {"result": {"workspaces": workspaces or []}},
        "tab create": {"result": {"root_pane": {"pane_id": "w9:p9", "tab_id": "w9:t9"}}},
        # A second bash is in front of the pane's own shell.
        "pane process-info": {"result": {"process_info": {"shell_pid": 1, "foreground_process_group_id": 2}}},
        "tab list": {"result": {"tabs": []}},
    }


def _indent() -> str:
    match = re.search(r'^INDENT = "(.*)"$', NEW_TERMINAL.read_text(), re.MULTILINE)
    assert match
    return match.group(1).encode().decode("unicode_escape")


def _opened(calls: list) -> list:
    looks = (["pane", "list"], ["workspace", "list"], ["pane", "read"], ["pane", "wait-output"], ["pane", "process-info"])
    return [call for call in calls if call[:2] not in looks]


@pytest.mark.parametrize(
    ("panes", "env", "workspace"),
    [
        ([_pane("w1:p1"), _pane("w2:p2", focused=True)], {}, "w2"),
        ([_pane("w1:p1"), _pane("w2:p2", focused=True)], {"HERDR_PANE_ID": "w1:p1"}, "w2"),
        ([_pane("w1:p1"), _pane("w2:p2")], {"HERDR_PANE_ID": "w1:p1"}, "w1"),
    ],
    ids=["focused", "focused-over-env", "env-without-focus"],
)
def test_new_terminal_opens_a_named_terminal_agent_beside_the_source_pane(
    recorder, panes, env, workspace
):
    done, calls = recorder([str(NEW_TERMINAL)], _new_terminal_replies(panes), **env)
    assert done.returncode == 0, done.stderr
    assert _opened(calls) == [
        [
            "tab",
            "create",
            "--workspace",
            workspace,
            "--cwd",
            f"/{workspace}",
            "--label",
            "terminal",
            "--no-focus",
        ],
        ["pane", "rename", "w9:p9", _indent() + "terminal"],
        ["pane", "run", "w9:p9", "clear; bash; exit"],
        [
            "pane",
            "report-agent",
            "w9:p9",
            "--source",
            "workstation:terminal",
            "--agent",
            "terminal",
            "--state",
            "idle",
        ],
        ["tab", "focus", "w9:t9"],
    ]


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ([], "app-dev"),
        (["other"], "app-dev"),
        (["app-dev"], "app-dev-1"),
        (["app-dev", "app-dev-1"], "app-dev-2"),
        (["app-dev", "app-dev-2"], "app-dev-1"),
    ],
)
def test_new_terminal_names_an_app_tab_and_runs_its_command(recorder, labels, expected):
    replies = _new_terminal_replies([_pane("w1:p1", focused=True)])
    replies["tab list"] = {"result": {"tabs": [{"label": label} for label in labels]}}
    args = ["--cwd", "/app", "--name", "app-dev", "--run", "pnpm app:start"]
    done, calls = recorder([str(NEW_TERMINAL), *args], replies)
    assert done.returncode == 0, done.stderr
    opened = [call for call in _opened(calls) if call[:2] != ["tab", "list"]]
    assert opened[0] == [
        "tab",
        "create",
        "--workspace",
        "w1",
        "--cwd",
        "/app",
        "--label",
        expected,
        "--no-focus",
    ]
    assert opened[1] == ["pane", "rename", "w9:p9", _indent() + expected]
    assert opened[-1] == ["pane", "run", "w9:p9", "pnpm app:start"]


SHOWN = "⏺ Run this:\n\n  $ sudo   ntfsfix -d /dev/sda1\n\n> "


@pytest.mark.parametrize(
    ("clipboard", "typed"),
    [
        ("$ sudo ntfsfix -d /dev/sda1\n", "sudo ntfsfix -d /dev/sda1"),
        ("  ntfsfix -d", "ntfsfix -d"),
        ("Run this:", "Run this:"),
        ("rm -rf ~/old", None),
        ("this: $ sudo", None),
        ("Run this:\n\n$ sudo ntfsfix -d /dev/sda1", None),
        ("", None),
    ],
    ids=["prompt-line", "part", "prose", "not-shown", "across-lines", "multi-line", "empty"],
)
def test_new_terminal_types_the_line_highlighted_in_the_source_pane(recorder, clipboard, typed):
    # No more rows than the screen holds: more makes herdr scroll a Claude pane through its history.
    pane = {**_pane("w1:p1", focused=True), "scroll": {"viewport_rows": 83}}
    replies = _new_terminal_replies([pane])
    done, calls = recorder(
        [str(NEW_TERMINAL)], replies, CLIPBOARD_TEXT=clipboard, HERDR_READ_TEXT=SHOWN
    )
    assert done.returncode == 0, done.stderr
    read = ["pane", "read", "w1:p1", "--source", "recent-unwrapped", "--lines", "83"]
    one_line = bool(clipboard.strip()) and "\n" not in clipboard.strip()
    assert (read in calls) == one_line
    sent = [call for call in _opened(calls) if call[:2] == ["pane", "send-text"]]
    assert sent == ([["pane", "send-text", "w9:p9", typed]] if typed else [])


@pytest.mark.parametrize(
    "scroll", [{}, {"scroll": {}}, {"scroll": None}], ids=["missing", "empty", "null"]
)
def test_new_terminal_reads_24_rows_when_the_pane_gives_no_screen_height(recorder, scroll):
    pane = {**_pane("w1:p1", focused=True), **scroll}
    done, calls = recorder(
        [str(NEW_TERMINAL)],
        _new_terminal_replies([pane]),
        CLIPBOARD_TEXT="ntfsfix -d",
        HERDR_READ_TEXT=SHOWN,
    )
    assert done.returncode == 0, done.stderr
    assert ["pane", "read", "w1:p1", "--source", "recent-unwrapped", "--lines", "24"] in calls
    assert _opened(calls)[0][:2] == ["tab", "create"]
    assert _opened(calls)[-1] == ["pane", "send-text", "w9:p9", "ntfsfix -d"]


def test_new_terminal_opens_the_tab_when_the_clipboard_cannot_be_read(recorder):
    replies = _new_terminal_replies([_pane("w1:p1", focused=True)])
    done, calls = recorder([str(NEW_TERMINAL)], replies, CLIPBOARD_HANG="1", HERDR_READ_TEXT=SHOWN)
    assert done.returncode == 0, done.stderr
    assert [call[:2] for call in _opened(calls)] == [
        ["tab", "create"],
        ["pane", "rename"],
        ["pane", "run"],
        ["pane", "report-agent"],
        ["tab", "focus"],
    ]


def test_new_terminal_running_an_app_types_no_highlighted_line(recorder):
    replies = _new_terminal_replies([_pane("w1:p1", focused=True)])
    done, calls = recorder(
        [str(NEW_TERMINAL), "--run", "pnpm dev"],
        replies,
        CLIPBOARD_TEXT="ntfsfix",
        HERDR_READ_TEXT=SHOWN,
    )
    assert done.returncode == 0, done.stderr
    assert _opened(calls)[-1] == ["pane", "run", "w9:p9", "pnpm dev"]
    assert not [call for call in calls if call[:2] in (["pane", "read"], ["pane", "send-text"])]


def test_new_terminal_without_a_source_pane_opens_home_in_the_focused_workspace(recorder, tmp_path):
    workspaces = [{"workspace_id": "w1", "focused": False}, {"workspace_id": "w3", "focused": True}]
    replies = _new_terminal_replies([_pane("w1:p1")], workspaces)
    done, calls = recorder([str(NEW_TERMINAL)], replies, HERDR_PANE_ID="w7:p7")
    assert done.returncode == 0, done.stderr
    assert _opened(calls)[0][:6] == ["tab", "create", "--workspace", "w3", "--cwd", str(tmp_path)]


def test_new_terminal_without_any_focus_fails_and_opens_nothing(recorder):
    done, calls = recorder([str(NEW_TERMINAL)], _new_terminal_replies([]))
    assert done.returncode != 0
    assert "no focused herdr workspace" in done.stderr
    assert _opened(calls) == []


def test_new_terminal_stops_on_a_herdr_error(recorder):
    replies = _new_terminal_replies([_pane("w1:p1", focused=True)])
    replies["tab create"] = {"error": {"message": "workspace gone"}}
    done, calls = recorder([str(NEW_TERMINAL)], replies)
    assert done.returncode != 0
    assert "workspace gone" in done.stderr
    assert [call[:2] for call in _opened(calls)] == [["tab", "create"]]


def _rename(recorder, args: str, **env: str):
    _need("bash")
    return recorder(["bash", "-c", f'source "{RENAME}"; /rename {args}'], {}, **env)


def test_rename_names_the_pane_with_the_terminal_indent_and_the_tab_plainly(recorder):
    done, calls = _rename(recorder, "my shell", HERDR_PANE_ID="w1:p1", HERDR_TAB_ID="w1:t1")
    assert done.returncode == 0, done.stderr
    assert calls == [
        ["pane", "rename", "w1:p1", _indent() + "my shell"],
        ["tab", "rename", "w1:t1", "my shell"],
    ]


def test_rename_without_a_name_prints_usage_and_renames_nothing(recorder):
    done, calls = _rename(recorder, "", HERDR_PANE_ID="w1:p1", HERDR_TAB_ID="w1:t1")
    assert done.returncode == 2
    assert "usage: /rename <name>" in done.stderr
    assert calls == []


@pytest.mark.parametrize("env", [{}, {"HERDR_PANE_ID": "w1:p1"}], ids=["outside", "no-tab-id"])
def test_rename_is_not_defined_outside_a_herdr_pane(recorder, env):
    done, calls = _rename(recorder, "x", **env)
    assert done.returncode != 0
    assert calls == []


def _copy_pane(recorder, tmp_path, panes: list[dict], text: str = "") -> tuple:
    _need("bash", "jq")
    replies = {"pane list": {"result": {"panes": panes}}}
    done, calls = recorder([str(COPY_PANE)], replies, HERDR_READ_TEXT=text)
    clipboard = tmp_path / "calls.jsonl.clipboard"
    notified = tmp_path / "calls.jsonl.notified"
    return (
        done,
        calls,
        clipboard.read_text() if clipboard.exists() else None,
        notified.read_text() if notified.exists() else "",
    )


def test_copy_pane_copies_the_focused_pane_unwrapped(recorder, tmp_path):
    panes = [_pane("w1:p1"), _pane("w2:p2", focused=True)]
    done, calls, clipboard, notified = _copy_pane(recorder, tmp_path, panes, "one\ntwo")
    assert done.returncode == 0, done.stderr
    assert calls[1] == ["pane", "read", "w2:p2", "--source", "recent-unwrapped", "--lines", "1000"]
    assert clipboard == "one\ntwo\n"
    assert "2 lines" in notified


def test_copy_pane_without_focus_copies_nothing(recorder, tmp_path):
    done, calls, clipboard, notified = _copy_pane(recorder, tmp_path, [_pane("w1:p1")])
    assert done.returncode == 1
    assert clipboard is None
    assert len(calls) == 1
    assert "No herdr pane has focus" in notified


# ── Status line ────────────────────────────────────────────────────────────


def _statusline(home: Path, payload: dict) -> str:
    _need("bash", "jq", "git")
    done = subprocess.run(
        [str(STATUSLINE)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=dict(os.environ, HOME=str(home)),
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


def _strip(text: str) -> str:

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture
def githubs(tmp_path):
    repo = tmp_path / "githubs" / "infra"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "feat/x", str(repo)], check=True)
    return tmp_path


def test_named_session_shows_name_repo_and_branch(githubs):
    out = _statusline(
        githubs,
        {
            "session_name": "fix-backups",
            "cwd": "/x",
            "workspace": {"project_dir": str(githubs / "githubs" / "infra")},
        },
    )
    assert _strip(out) == "fix-backups · infra · feat/x"


def test_unnamed_session_and_null_project_dir_fall_back_to_cwd(githubs):
    out = _statusline(
        githubs, {"cwd": str(githubs / "githubs" / "infra"), "workspace": {"project_dir": None}}
    )
    assert _strip(out) == "unnamed — /rename to name it · infra · feat/x"


def test_workspace_root_and_a_directory_without_git(githubs):
    root = githubs / "githubs"
    assert _strip(_statusline(githubs, {"session_name": "s", "cwd": str(root)})) == "s · githubs"
    elsewhere = githubs / "notes"
    elsewhere.mkdir()
    assert (
        _strip(_statusline(githubs, {"session_name": "s", "cwd": str(elsewhere)}))
        == f"s · {elsewhere}"
    )


@pytest.mark.parametrize(
    ("context", "shown"),
    [({}, ""), ({"used_percentage": None}, ""), ({"used_percentage": 12.7}, " · 12%")],
)
def test_context_used_is_shown_once_known(githubs, context, shown):
    out = _statusline(
        githubs,
        {
            "session_name": "s",
            "cwd": str(githubs / "githubs" / "infra"),
            "context_window": context,
        },
    )
    assert _strip(out) == "s · infra · feat/x" + shown


@pytest.mark.parametrize(("used", "style"), [(34, "2"), (35, "33")])
def test_context_used_turns_yellow_near_auto_compact(githubs, used, style):
    payload = {
        "session_name": "s",
        "cwd": str(githubs),
        "context_window": {"used_percentage": used},
    }
    assert f"\x1b[{style}m{used}%" in _statusline(githubs, payload)


def _agent(pane: str, session: str | None = None) -> dict:
    agent = {"pane_id": pane, "terminal_id": f"term-{pane}", "tokens": {}}
    return agent | ({"agent_session": {"value": session}} if session else {})


def _run_paused(
    tmp_path: Path, command: str, panes: list[str], agents: list[dict], tabs=None, **env
) -> list:
    """Run paused.py against a fake herdr socket; returns the (method, params) it called.

    Each pane is its own tab unless `tabs` maps it to another."""
    calls = []
    tabs = tabs or {}
    replies = {
        "agent.list": {"agents": agents},
        "pane.list": {
            "panes": [
                {
                    "pane_id": pane,
                    "workspace_id": pane.split(":")[0],
                    "tab_id": tabs.get(pane, pane),
                }
                for pane in panes
            ]
        },
    }

    def serve(server: socket.socket) -> None:
        while True:
            client, _ = server.accept()
            with client, client.makefile("rb") as requests:
                request = json.loads(requests.readline())
                calls.append((request["method"], request["params"]))
                reply = {"result": replies.get(request["method"], {})}
                client.sendall(json.dumps(reply).encode() + b"\n")

    path = tmp_path / "s"
    with socket.socket(socket.AF_UNIX) as server:
        server.bind(str(path))
        server.listen()
        threading.Thread(target=serve, args=(server,), daemon=True).start()
        done = subprocess.run(
            ["python3", str(PAUSED), command],
            capture_output=True,
            text=True,
            env=dict(
                os.environ,
                HERDR_SOCKET_PATH=str(path),
                HERDR_PLUGIN_ID="workstation.paused",
                HERDR_PLUGIN_STATE_DIR=str(tmp_path / "state"),
                **env,
            ),
        )
    path.unlink()
    assert done.returncode == 0, done.stderr
    return calls


def _lists(calls: list) -> dict:
    return {p["pane_id"]: p["tokens"] for m, p in calls if m == "pane.report_metadata"}


def _focused(calls: list) -> list:
    return [p["target"] for m, p in calls if m == "agent.focus"]


def _write_paused(tmp_path: Path, sessions=(), terminals=()) -> None:
    (tmp_path / "state").mkdir()
    state = {"sessions": list(sessions), "terminals": list(terminals)}
    (tmp_path / "state" / "paused.json").write_text(json.dumps(state))


def test_paused_sync_with_nothing_paused_ranks_every_pane_without_a_heading(tmp_path):
    calls = _run_paused(tmp_path, "sync", ["w1:p1", "w1:p2"], [_agent("w1:p2", "s2")])
    assert _lists(calls) == {
        "w1:p1": {"list": "00000", "heading_below": None, "heading_above": None},
        "w1:p2": {"list": "00001", "heading_below": None, "heading_above": None},
    }
    view = next(p for m, p in calls if m == "agent.view.set")
    assert view["source"] == "plugin:workstation.paused"
    assert view["sort"] == [{"field": {"token": "list"}}]


def test_paused_toggle_moves_the_agent_down_and_focus_to_the_next_active_one(tmp_path):
    panes = ["w1:p1", "w1:p2", "w1:p3"]
    agents = [_agent("w1:p1", "s1"), _agent("w1:p2", "s2"), _agent("w1:p3", "s3")]
    calls = _run_paused(tmp_path, "toggle", panes, agents, HERDR_PANE_ID="w1:p2")
    lists = _lists(calls)
    assert lists["w1:p2"]["list"] == "10001"
    assert lists["w1:p3"]["heading_below"] and lists["w1:p3"]["list"] == "00002"
    assert _focused(calls) == ["w1:p3"]
    assert json.loads((tmp_path / "state" / "paused.json").read_text())["sessions"] == ["s2"]


def test_paused_toggle_wraps_focus_to_the_first_active_agent(tmp_path):
    agents = [_agent("w1:p1", "s1"), _agent("w1:p2", "s2")]
    calls = _run_paused(tmp_path, "toggle", ["w1:p1", "w1:p2"], agents, HERDR_PANE_ID="w1:p2")
    assert _focused(calls) == ["w1:p1"]


def test_paused_toggle_brings_a_paused_agent_back_and_leaves_focus_on_it(tmp_path):
    _write_paused(tmp_path, sessions=["s2"])
    agents = [_agent("w1:p1", "s1"), _agent("w1:p2", "s2")]
    calls = _run_paused(tmp_path, "toggle", ["w1:p1", "w1:p2"], agents, HERDR_PANE_ID="w1:p2")
    assert _lists(calls)["w1:p2"]["list"] == "00001"
    assert not any(tokens["heading_below"] for tokens in _lists(calls).values())
    assert _focused(calls) == []
    assert json.loads((tmp_path / "state" / "paused.json").read_text())["sessions"] == []


def test_paused_new_session_in_a_paused_pane_starts_active(tmp_path):
    _write_paused(tmp_path, sessions=["old"])
    calls = _run_paused(tmp_path, "sync", ["w1:p1"], [_agent("w1:p1", "new")])
    assert _lists(calls)["w1:p1"]["list"] == "00000"


def test_paused_heading_tops_the_list_when_everything_is_paused(tmp_path):
    _write_paused(tmp_path, sessions=["s1", "s2"])
    agents = [_agent("w1:p1", "s1"), _agent("w1:p2", "s2")]
    lists = _lists(_run_paused(tmp_path, "sync", ["w1:p1", "w1:p2"], agents))
    assert lists["w1:p1"]["heading_above"] and not lists["w1:p2"]["heading_above"]


def test_paused_agent_without_a_session_is_kept_by_terminal(tmp_path):
    agents = [_agent("w1:p1"), _agent("w1:p2", "s2")]
    calls = _run_paused(tmp_path, "toggle", ["w1:p1", "w1:p2"], agents, HERDR_PANE_ID="w1:p1")
    state = json.loads((tmp_path / "state" / "paused.json").read_text())
    assert state == {"sessions": [], "terminals": ["term-w1:p1"]}
    assert _lists(calls)["w1:p1"]["list"] == "10000"


def test_paused_toggle_on_a_pane_without_an_agent_does_nothing(tmp_path):
    calls = _run_paused(tmp_path, "toggle", ["w1:p1"], [], HERDR_PANE_ID="w1:p1")
    assert _lists(calls) == {} and not (tmp_path / "state" / "paused.json").exists()


def test_paused_tokens_already_in_place_are_not_written_again(tmp_path):
    agent = _agent("w1:p1", "s1") | {"tokens": {"list": "00000"}}
    assert _lists(_run_paused(tmp_path, "sync", ["w1:p1"], [agent])) == {}


def test_paused_toggle_keeps_focus_inside_the_workspace(tmp_path):
    panes = ["w1:p1", "w2:p1", "w2:p2"]
    agents = [_agent("w1:p1", "s1"), _agent("w2:p1", "s2"), _agent("w2:p2", "s3")]
    calls = _run_paused(tmp_path, "toggle", panes, agents, HERDR_PANE_ID="w2:p2")
    assert _focused(calls) == ["w2:p1"]


def test_paused_toggle_on_a_workspaces_only_agent_leaves_focus_alone(tmp_path):
    agents = [_agent("w1:p1", "s1"), _agent("w2:p1", "s2")]
    calls = _run_paused(tmp_path, "toggle", ["w1:p1", "w2:p1"], agents, HERDR_PANE_ID="w2:p1")
    assert _focused(calls) == []


def test_paused_heading_hangs_under_the_last_active_agent_of_any_workspace(tmp_path):
    # The sort is flat across workspaces, checked in a real herdr, so one heading is right.
    _write_paused(tmp_path, sessions=["s1"])
    agents = [_agent("w1:p1", "s1"), _agent("w2:p1", "s2")]
    lists = _lists(_run_paused(tmp_path, "sync", ["w1:p1", "w2:p1"], agents))
    assert lists["w2:p1"]["heading_below"] and lists["w2:p1"]["list"] == "00001"
    assert lists["w1:p1"]["list"] == "10000" and not lists["w1:p1"]["heading_below"]


def _closed(calls: list) -> list:
    return [p["tab_id"] for m, p in calls if m == "tab.close"]


FOUR = ["w1:p1", "w1:p2", "w1:p3", "w2:p1"]
FOUR_AGENTS = [_agent(p, "s-" + p) for p in FOUR]


def test_paused_close_lands_on_the_next_active_agent_skipping_paused_ones(tmp_path):
    _write_paused(tmp_path, sessions=["s-w1:p3"])
    calls = _run_paused(tmp_path, "close", FOUR, FOUR_AGENTS, HERDR_PANE_ID="w1:p2")
    assert _closed(calls) == ["w1:p2"]
    assert _focused(calls) == ["w2:p1"]
    assert calls.index(("tab.close", {"tab_id": "w1:p2"})) < len(calls) - 1


def test_paused_close_of_the_last_active_agent_goes_up_not_into_the_paused_list(tmp_path):
    _write_paused(tmp_path, sessions=["s-w1:p3"])
    calls = _run_paused(tmp_path, "close", FOUR, FOUR_AGENTS, HERDR_PANE_ID="w2:p1")
    assert _focused(calls) == ["w1:p2"]


def test_paused_close_of_a_paused_agent_lands_on_the_last_active_one(tmp_path):
    _write_paused(tmp_path, sessions=["s-w1:p1", "s-w1:p3"])
    calls = _run_paused(tmp_path, "close", FOUR, FOUR_AGENTS, HERDR_PANE_ID="w1:p1")
    assert _closed(calls) == ["w1:p1"]
    assert _focused(calls) == ["w2:p1"]


def test_paused_close_skips_the_other_panes_of_the_closed_tab(tmp_path):
    tabs = {"w1:p1": "w1:t1", "w1:p2": "w1:t1"}
    calls = _run_paused(tmp_path, "close", FOUR, FOUR_AGENTS, tabs=tabs, HERDR_PANE_ID="w1:p1")
    assert _closed(calls) == ["w1:t1"]
    assert _focused(calls) == ["w1:p3"]


def test_paused_close_with_no_active_agent_left_only_closes(tmp_path):
    _write_paused(tmp_path, sessions=["s-w1:p2"])
    agents = [_agent("w1:p1", "s-w1:p1"), _agent("w1:p2", "s-w1:p2")]
    calls = _run_paused(tmp_path, "close", ["w1:p1", "w1:p2"], agents, HERDR_PANE_ID="w1:p1")
    assert _closed(calls) == ["w1:p1"] and _focused(calls) == []


def test_paused_close_of_a_plain_pane_closes_its_tab(tmp_path):
    calls = _run_paused(
        tmp_path, "close", ["w1:p1", "w1:p2"], [_agent("w1:p2", "s2")], HERDR_PANE_ID="w1:p1"
    )
    assert _closed(calls) == ["w1:p1"] and _focused(calls) == ["w1:p2"]


@pytest.mark.parametrize(
    ("panes", "env"),
    [
        (FOUR, {}),
        (FOUR, {"HERDR_PANE_ID": "w9:p9"}),
        ([], {"HERDR_PANE_ID": "w1:p1"}),
    ],
    ids=["no-focused-pane", "stale-pane", "no-panes"],
)
def test_paused_close_without_a_known_focused_pane_does_nothing(tmp_path, monkeypatch, panes, env):
    monkeypatch.delenv("HERDR_PANE_ID", raising=False)
    calls = _run_paused(tmp_path, "close", panes, FOUR_AGENTS, **env)
    assert _closed(calls) == [] and _focused(calls) == []


def test_a_plugin_missing_from_the_registry_is_linked_again(home):
    _play(home)
    registry = home / ".config" / "herdr" / "plugins.json"
    registry.write_text("[]")
    assert _play(home)["changed"] == 1
    assert "herdr-paused" in registry.read_text()
