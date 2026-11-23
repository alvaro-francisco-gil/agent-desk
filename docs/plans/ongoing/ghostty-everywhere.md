# Ghostty and its colours on every machine

**Priority:** medium
**Gate:** none
**Next:** On the Ubuntu machine: `git pull`, install Ghostty, re-run the install and check the look

**Goal:** a machine without Omarchy (a stock Ubuntu GNOME desktop) gets the same Ghostty
terminal, font and colours as the Omarchy workstation, from `git pull` and the usual
install command.

## Context

On the Omarchy workstation, Ghostty and its look come from Omarchy, not from this repo:
Omarchy installs Ghostty, writes `~/.config/ghostty/config` and colours it through its
theme system. agent-desk only adds the Alt+R line to a Ghostty config that already exists.
So a stock Ubuntu machine that runs the install gets herdr in GNOME Terminal with its
default colours, and no Alt+R.

This has to be done on the Omarchy workstation (AGENTS.md: changes are made and tried
there), because only that machine has the config and theme to copy.

## Design

- **Snapshot, don't link.** Copy the Omarchy Ghostty config and the theme it uses into
  `files/ghostty/`, flattened into plain files (no `config-file` include pointing at
  `~/.config/omarchy/...`, which won't exist elsewhere). Omarchy's theme switching stays
  Omarchy-only; other machines get the current theme as a fixed copy.
- **Never touch Omarchy's files.** Install the config only when the machine isn't
  Omarchy (no `~/.config/omarchy` or `~/.local/share/omarchy`) and no Ghostty config
  exists yet (`force: false`). An existing config is left alone, as with the other tasks.
- **Order.** Write the config before the "Type /rename on Alt+R" task, so a fresh machine
  gets Alt+R in the same run.
- **Ghostty itself.** On Ubuntu, `sudo snap install ghostty --classic` (stable is 1.4.0).
  Install it from the playbook only behind a variable that defaults to off
  (`agent_desk_install_ghostty`), since it needs sudo; the README gives the command
  either way.
- **Font.** If the config names a font Ubuntu doesn't ship (for example a Nerd Font),
  either install it to `~/.local/share/fonts` from the playbook or fall back to a stock
  font. Decide after reading the config.
- **Keep it public-safe.** Config and theme only: no host names, paths or anything
  machine-specific. Credit the theme's source and licence in the README, as for
  `sheep.ico` (Omarchy is MIT; check the theme's own licence).

## File Structure

- Create `files/ghostty/config` (flattened config + theme colours)
- Modify `tasks/agent_sessions.yml` (install task before the Alt+R task; optional snap install)
- Modify `tests/test_agent_sessions.py` (cases below)
- Modify `README.md` (Ghostty section, credits)

## Tasks

- [x] On the Omarchy workstation, read `~/.config/ghostty/config` and every file it
      includes; note the theme name, font, and any herdr colour settings
      (`~/.config/herdr/config.toml`) Omarchy sets, which should travel too.
- [x] Write `files/ghostty/config` as one self-contained file.
- [x] Add the install task (skip on Omarchy, skip when a config exists) and the optional
      snap install.
- [x] Tests with a throwaway `$HOME`: empty home gets the config and the Alt+R line;
      existing config untouched; Omarchy marker present means untouched; re-run reports
      no change.
- [x] README: Ghostty install on Ubuntu, what the playbook writes, credits.
- [x] PR, tests green, merge.
- [ ] On the Ubuntu machine: `git pull`, install Ghostty, re-run the install, open
      Ghostty and check colours, font, Alt+R, and that `cs` opens herdr in it.

## Also worth doing in the same PR (done)

Alt+Up/Down are still unbound on a machine that had no herdr config before the install:
the "Move between agents" task only rewrites Omarchy's lines, and there's no `[keys]`
table to rewrite. When neither `previous_agent` nor `next_agent` is set and Alt+Up/Down
are free, add both (through `merge-tables.py`), with a test that starts from an empty
config.

## Decisions taken (2026-11-23)

- The theme snapshotted is Omarchy's current one, Tokyo Night.
- Font: kept JetBrainsMono Nerd Font, not installed; Ghostty's built-in JetBrains Mono
  carries the Nerd Font symbols, so a machine without it looks the same. Size 9 kept.
- Dropped `async-backend = epoll` (a Hyprland-only fix) and the Alt+R line (the Alt+R
  task adds it).
- herdr's look travels too (`files/herdr/omarchy-look.toml`: theme `terminal`, blue
  accent, no pane gaps or outer borders), only while the herdr config has no `[theme]`.
- Omarchy is detected by `~/.config/omarchy`, `~/.local/share/omarchy` or
  `/usr/share/omarchy`.
