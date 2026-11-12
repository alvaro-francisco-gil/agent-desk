# agent-desk: agent notes

The portable part of a herdr + Claude Code setup: keys, small tools, settings.
Machines take it with `git pull`; only the owner pushes.

## Rules

- **Public repo, no private facts.** No host or network names, no repo names or repo
  lists, no paths of one person's machine, no secrets. A machine's own facts (which repos
  it works on) live in `~/.config/agent-desk/config.toml` on that machine
  (`agent_desk/repos.py`), never here.
- **Changes are made and tried on the main workstation**, then pulled elsewhere. A
  machine that only pulls never needs a GitHub login.
- **Code changes go through a PR whose tests pass** (`.github/workflows/test.yml`);
  Markdown-only changes go straight to `main`.
- `wt.ps1` and `wt-ssh.ps1` must stay safe to re-run: they replace only what they added
  and back up first.
- Plan for the rest of the move: `_workspace/docs/plans/ongoing/agent-desk.md` in the
  owner's private workspace.

## Layout

- `install.yml` installs on this machine; `tasks/agent_sessions.yml` is the work, also
  included by a machine's own setup play (variables `agent_desk_home`, `agent_desk_dir`).
- `files/` what the tasks install: herdr helpers and paused-agents plugin, Claude Code
  status line, keybindings and secret-file denies.
- `bin/cs` + `agent_desk/`: the repo picker (`cs`, `cs --closed`).
- `wt.ps1`, `wt-ssh.ps1`, `sheep.ico`: Windows Terminal, for a Windows machine that
  SSHes into a herdr one.

## Setup

`pip install pytest ansible-core` (or your package manager), then `pytest -q`. The
ansible tests run against a throwaway `$HOME` with a stub `herdr`; they take ~6 minutes.
