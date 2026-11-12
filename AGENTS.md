# agent-desk: agent notes

The portable part of a herdr + Claude Code setup: keys, small tools, settings.
Machines take it with `git pull`; only the owner pushes.

## Rules

- **Public repo, no private facts.** No host or network names, no repo names or repo
  lists, no paths of one person's machine, no secrets. A machine's own facts (which repos
  it works on, local key overrides) live in files on that machine that this repo reads
  and never ships.
- **Changes are made and tried on the main workstation**, then pulled elsewhere. A
  machine that only pulls never needs a GitHub login.
- `wt.ps1` must stay safe to re-run: it replaces only what it added and backs up first.
- Plan for the rest of the move: `_workspace/docs/plans/ongoing/agent-desk.md` in the
  owner's private workspace.
