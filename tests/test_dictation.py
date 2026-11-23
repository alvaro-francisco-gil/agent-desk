"""tasks/dictation.yml, voxtype-last (Shift+F9) and gnome-shortcuts.py.

The play runs against a throwaway $HOME with stub voxtype, systemctl and gsettings;
skipped where ansible-playbook is missing.
"""

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TASKS = REPO / "tasks" / "dictation.yml"
VOXTYPE_LAST = REPO / "files" / "dictation" / "voxtype-last"
GNOME_SHORTCUTS = REPO / "files" / "dictation" / "gnome-shortcuts.py"
SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
BASE = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/"

# Logs its calls; `setup --download` and `setup systemd` write what voxtype would.
VOXTYPE_STUB = """#!/usr/bin/env python3
import os, sys
from pathlib import Path
home = Path(os.environ["HOME"])
with open(home.parent / "voxtype.log", "a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
if sys.argv[1:3] == ["setup", "--download"]:
    model = sys.argv[sys.argv.index("--model") + 1]
    models = home / ".local/share/voxtype/models"
    models.mkdir(parents=True, exist_ok=True)
    (models / f"ggml-{model}.bin").write_text("")
elif sys.argv[1:3] == ["setup", "systemd"]:
    unit = home / ".config/systemd/user/voxtype.service"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text("[Service]\\nExecStart=/usr/bin/voxtype daemon\\n")
"""

# gsettings over a JSON file: what gsettings prints, GVariant text in and out.
GSETTINGS_STUB = """#!/usr/bin/env python3
import ast, json, os, sys
from pathlib import Path
store = Path(os.environ["HOME"]).parent / "gsettings.json"
data = json.loads(store.read_text()) if store.exists() else {}
cmd, *rest = sys.argv[1:]
if cmd == "list-keys":
    sys.exit(0 if rest == ["%(schema)s"] and not os.environ.get("NO_GNOME") else 1)
def show(v):
    if isinstance(v, list):
        return "@as []" if not v else "[" + ", ".join(repr(x) for x in v) + "]"
    return repr(v)
if cmd == "get":
    schema, key = rest
    print(show(data.get(schema, {}).get(key, [] if key == "custom-keybindings" else "")))
elif cmd == "set":
    schema, key, value = rest
    data.setdefault(schema, {})[key] = ast.literal_eval(value)
    store.write_text(json.dumps(data))
""" % {"schema": SCHEMA}


def _need(*tools):
    missing = [t for t in tools if not shutil.which(t)]
    if missing:
        pytest.skip(f"missing: {', '.join(missing)}")


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name, body in (
        ("voxtype", VOXTYPE_STUB),
        ("gsettings", GSETTINGS_STUB),
        ("systemctl", f'#!/bin/bash\necho "$*" >> {tmp_path / "systemctl.log"}\n'),
    ):
        (stubs / name).write_text(body)
        (stubs / name).chmod(0o755)
    return home


def _play(home: Path, *extra: str, env: dict | None = None, ok: bool = True):
    _need("ansible-playbook")
    play = home.parent / "play.yml"
    play.write_text(
        "- hosts: localhost\n  connection: local\n  gather_facts: false\n"
        f"  vars: {{agent_desk_home: '{home}', agent_desk_dir: '{REPO}'}}\n"
        f"  tasks:\n    - ansible.builtin.include_tasks: '{TASKS}'\n"
    )
    full_env = dict(
        os.environ,
        HOME=str(home),
        PATH=f"{home.parent / 'bin'}:{os.environ['PATH']}",
        ANSIBLE_STDOUT_CALLBACK="default",
        ANSIBLE_COLLECTIONS_PATH=str(home.parent / "no-collections"),
        ANSIBLE_NOCOLOR="1",
        ANSIBLE_LOCALHOST_WARNING="false",
        ANSIBLE_INVENTORY_UNPARSED_WARNING="false",
        ANSIBLE_LOCAL_TEMP=str(home.parent / "tmp"),
        ANSIBLE_REMOTE_TEMP=str(home.parent / "tmp"),
    )
    full_env.update(env or {})
    done = subprocess.run(
        [shutil.which("ansible-playbook"), "-i", "localhost,", str(play), *extra],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=home.parent,
    )
    if not ok:
        assert done.returncode != 0
        return done.stdout
    assert done.returncode == 0, done.stdout[-3000:] + done.stderr[-2000:]
    recap = re.search(r"^localhost\s*:\s*(.*)$", done.stdout, re.MULTILINE)
    return {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", recap.group(1))}


def _gsettings(home: Path) -> dict:
    return json.loads((home.parent / "gsettings.json").read_text())


def test_fresh_home_gets_dictation_on_f9(home):
    _play(home)
    config = tomllib.loads((home / ".config/voxtype/config.toml").read_text())
    assert config["hotkey"] == {"enabled": True, "key": "F9", "mode": "push_to_talk"}
    assert config["whisper"]["model"] == "large-v3-turbo"
    assert config["whisper"]["language"] == ["en", "es"]
    assert config["output"]["paste_keys"] == "shift+insert"
    override = home / ".config/systemd/user/voxtype.service.d/agent-desk.conf"
    assert "ExecStart=/usr/bin/voxtype -v daemon" in override.read_text()
    assert (home / ".local/share/voxtype/models/ggml-large-v3-turbo.bin").exists()
    assert (home / ".config/systemd/user/voxtype.service").exists()
    assert "restart voxtype" in (home.parent / "systemctl.log").read_text()
    last = home / ".local/bin/voxtype-last"
    assert last.read_text() == VOXTYPE_LAST.read_text() and os.access(last, os.X_OK)
    data = _gsettings(home)
    toggle = data[f"{SCHEMA}.custom-keybinding:{BASE}agent-desk-dictation-toggle/"]
    copy = data[f"{SCHEMA}.custom-keybinding:{BASE}agent-desk-dictation-last/"]
    assert toggle == {"name": "Dictation on/off", "command": "voxtype record toggle", "binding": "<Alt>F9"}
    assert copy["binding"] == "<Shift>F9" and copy["command"] == str(last)
    assert data[SCHEMA]["custom-keybindings"] == [
        f"{BASE}agent-desk-dictation-toggle/",
        f"{BASE}agent-desk-dictation-last/",
    ]


def test_a_rerun_changes_nothing_and_keeps_your_words(home):
    _play(home)
    config = home / ".config/voxtype/config.toml"
    config.write_text(config.read_text() + "# my words\n")
    (home.parent / "systemctl.log").unlink()
    recap = _play(home)
    assert recap["changed"] == 0
    assert config.read_text().endswith("# my words\n")
    assert not (home.parent / "systemctl.log").exists()


def test_the_model_can_be_chosen(home):
    _play(home, "-e", "agent_desk_dictation_model=small")
    config = tomllib.loads((home / ".config/voxtype/config.toml").read_text())
    assert config["whisper"]["model"] == "small"
    assert "--model small" in (home.parent / "voxtype.log").read_text()


def test_without_gnome_the_shortcuts_are_left_out(home):
    _play(home, env={"NO_GNOME": "1"})
    assert not (home.parent / "gsettings.json").exists()
    assert (home / ".local/bin/voxtype-last").exists()


def test_omarchy_is_left_alone(home):
    (home / ".local/share/omarchy").mkdir(parents=True)
    _play(home)
    assert not (home / ".config/voxtype").exists()
    assert not (home.parent / "voxtype.log").exists()


def test_without_voxtype_it_says_how(home):
    # PATH without voxtype, even one installed on this machine: every other tool linked.
    stubs = home.parent / "bin"
    (stubs / "voxtype").unlink()
    for folder in os.environ["PATH"].split(":"):
        for tool in Path(folder).glob("*") if Path(folder).is_dir() else ():
            if tool.name != "voxtype" and not (stubs / tool.name).exists():
                (stubs / tool.name).symlink_to(tool)
    out = _play(home, env={"PATH": str(stubs)}, ok=False)
    assert "voxtype is not installed" in out


def test_check_mode_writes_nothing(home):
    _play(home, "--check")
    assert not (home / ".config/voxtype").exists()
    assert not (home.parent / "gsettings.json").exists()


# gnome-shortcuts.py on its own


def _shortcuts(tmp_path: Path, wanted: list[dict], existing: dict | None = None):
    stubs = tmp_path / "bin"
    stubs.mkdir(exist_ok=True)
    (stubs / "gsettings").write_text(GSETTINGS_STUB)
    (stubs / "gsettings").chmod(0o755)
    (tmp_path / "home").mkdir(exist_ok=True)
    if existing is not None:
        (tmp_path / "gsettings.json").write_text(json.dumps(existing))
    done = subprocess.run(
        ["python3", str(GNOME_SHORTCUTS), json.dumps(wanted)],
        capture_output=True,
        text=True,
        env=dict(os.environ, HOME=str(tmp_path / "home"), PATH=f"{stubs}:{os.environ['PATH']}"),
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip(), json.loads((tmp_path / "gsettings.json").read_text())


TOGGLE = {"id": "t", "name": "Toggle", "command": "voxtype record toggle", "binding": "<Alt>F9"}


def test_shortcuts_keep_the_ones_already_there(tmp_path):
    mine = f"{BASE}custom0/"
    said, data = _shortcuts(tmp_path, [TOGGLE], {SCHEMA: {"custom-keybindings": [mine]}})
    assert said == "changed"
    assert data[SCHEMA]["custom-keybindings"] == [mine, f"{BASE}t/"]
    said, _ = _shortcuts(tmp_path, [TOGGLE])
    assert said == "ok"


def test_shortcuts_update_in_place(tmp_path):
    _shortcuts(tmp_path, [TOGGLE])
    said, data = _shortcuts(tmp_path, [dict(TOGGLE, binding="<Ctrl>F9")])
    assert said == "changed"
    assert data[f"{SCHEMA}.custom-keybinding:{BASE}t/"]["binding"] == "<Ctrl>F9"
    assert data[SCHEMA]["custom-keybindings"] == [f"{BASE}t/"]


# voxtype-last (Shift+F9)


def _last(tmp_path, journal, journal_status=0, copy_status=0, replacements=None, wayland=True):
    """Press Shift+F9 with stubs; returns the result, what was copied (None if nothing
    was) and what was notified."""
    home, stubs = tmp_path / "home", tmp_path / "stubs"
    shutil.rmtree(home, ignore_errors=True)
    shutil.rmtree(stubs, ignore_errors=True)
    stubs.mkdir()
    home.mkdir()
    if replacements is not None:
        (home / ".config" / "voxtype").mkdir(parents=True)
        (home / ".config" / "voxtype" / "config.toml").write_text(
            f"[text]\nreplacements = {replacements}\n"
        )
    (tmp_path / "journal").write_text(journal)
    copied, notified = tmp_path / "copied", tmp_path / "notified"
    copied.unlink(missing_ok=True)
    notified.write_text("")
    (stubs / "journalctl").write_text(f"#!/bin/bash\ncat {tmp_path / 'journal'}\nexit {journal_status}\n")
    clip = f"#!/bin/bash\necho \"$0 $*\" > {tmp_path / 'clip'}\ncat > {copied}\nexit {copy_status}\n"
    (stubs / "wl-copy").write_text(clip)
    (stubs / "xclip").write_text(clip)
    (stubs / "notify-send").write_text(f'#!/bin/bash\nprintf "%s\\n" "$*" >> {notified}\n')
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    env = dict(os.environ, HOME=str(home), PATH=f"{stubs}:{os.environ['PATH']}")
    env.pop("WAYLAND_DISPLAY", None)
    if wayland:
        env["WAYLAND_DISPLAY"] = "wayland-1"
    done = subprocess.run([str(VOXTYPE_LAST)], capture_output=True, text=True, env=env)
    return done, copied.read_text() if copied.exists() else None, notified.read_text()


def _said(text: str) -> str:
    return f'2026-11-20T00:14:05Z  INFO Transcribed: "{text}"\n'


def _counted(chars: int) -> str:
    return (
        "INFO Recording started (external trigger), model_override = None\n"
        f"INFO Transcribed {chars} chars (whisper engine)\n"
    )


def test_last_dictation_copies_the_newest_with_its_quotes(tmp_path):
    journal = _said("first one") + "INFO Recording started\n" + _said('she said "hi" twice')
    done, copied, notified = _last(tmp_path, journal)
    assert done.returncode == 0, done.stderr
    assert copied == 'she said "hi" twice'
    assert "(copied)" in notified
    assert "wl-copy" in (tmp_path / "clip").read_text()


def test_last_dictation_on_x11_copies_with_xclip(tmp_path):
    done, copied, _ = _last(tmp_path, _said("on x11"), wayland=False)
    assert done.returncode == 0, done.stderr
    assert copied == "on x11"
    assert "xclip -selection clipboard" in (tmp_path / "clip").read_text()


def test_last_dictation_applies_voxtypes_replacements(tmp_path):
    done, copied, _ = _last(
        tmp_path, _said("open cloud code here"), replacements='{ "cloud code" = "Claude Code" }'
    )
    assert done.returncode == 0, done.stderr
    assert copied == "open Claude Code here"


def test_last_dictation_refuses_an_older_one_when_the_newest_has_no_text(tmp_path):
    done, copied, notified = _last(tmp_path, _said("an older one") + _counted(868))
    assert done.returncode == 1
    assert copied is None
    assert "without its text" in notified and "an older one" not in notified


def test_last_dictation_refuses_a_length_only_journal_cut_before_its_start(tmp_path):
    done, copied, notified = _last(tmp_path, "INFO Transcribed 868 chars (whisper engine)\n")
    assert done.returncode == 1 and copied is None
    assert "without its text" in notified


def test_last_dictation_reads_the_text_logged_beside_the_length(tmp_path):
    started = "INFO Recording started (external trigger)\n"
    for newest in (
        started + _said("the newest") + "INFO Transcribed 10 chars (whisper engine)\n",
        started + "INFO Transcribed 10 chars (whisper engine)\n" + _said("the newest"),
    ):
        done, copied, _ = _last(tmp_path, _said("an older one") + newest)
        assert done.returncode == 0, done.stderr
        assert copied == "the newest"


def test_last_dictation_without_one_says_so(tmp_path):
    done, copied, notified = _last(tmp_path, "INFO Recording started\n")
    assert done.returncode == 0 and copied is None
    assert "Nothing dictated" in notified


def test_last_dictation_says_so_when_the_journal_fails(tmp_path):
    done, copied, notified = _last(tmp_path, "", journal_status=1)
    assert done.returncode == 1 and copied is None
    assert "Could not read" in notified


def test_last_dictation_still_shows_the_text_when_copying_fails(tmp_path):
    done, _, notified = _last(tmp_path, _said("keep this"), copy_status=1)
    assert done.returncode == 1
    assert "(not copied)" in notified and "keep this" in notified
