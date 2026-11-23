# Keys and tools that work in any terminal

**Goal:** on a stock Ubuntu desktop (GNOME Terminal, no sudo for some tools, herdr
started from a launcher), every key the README promises works without hand fixes.

## Context

Found on an Ubuntu install, fixed there by hand, not yet in the playbook. Alt+Up/Down
for a machine with no herdr config is handled in `ghostty-everywhere` (PR #5).

- **Alt+R only works in Ghostty and foot.** GNOME Terminal and Windows Terminal over SSH
  get nothing. A herdr key command works in every terminal:

  ```toml
  [[keys.command]]
  key = "alt+r"
  type = "shell"
  command = "~/.local/bin/herdr-type-rename"
  ```

  with the helper:

  ```bash
  #!/usr/bin/env bash
  # Alt+R in herdr: type "/rename " at the focused pane's prompt.
  pane="${HERDR_PANE_ID:-$(herdr pane list | jq -r '.result.panes[] | select(.focused) | .pane_id' | head -1)}"
  [ -n "$pane" ] && herdr pane send-text "$pane" "/rename " >/dev/null
  ```

- **Alt+N / Alt+P close at once when herdr starts from the desktop.** Without sudo, fzf
  comes from Homebrew, which only the login shell puts on PATH. A herdr server started
  from a GNOME launcher has the desktop PATH, so `cs` finds no fzf.
- **Copy did nothing in GNOME Terminal.** herdr copies through `wl-copy`, or else a
  terminal clipboard request (OSC 52) that GNOME Terminal ignores. With `wl-clipboard`
  missing, "selection copied" shows but the clipboard stays empty. `wl-clipboard` is now
  on the README apt line; the playbook could also warn when `wl-copy` is missing.

## Tasks

- [ ] Ship `files/herdr/type-rename` and bind Alt+R through herdr, inside the managed
      block, only while nothing else in the herdr config holds Alt+R. Decide whether the
      Ghostty/foot bindings stay (they do the same thing; keeping both is harmless).
- [ ] When `fzf` resolves to a Homebrew path, link it into `~/.local/bin`.
- [ ] Warn (don't fail) when `wl-copy` isn't on PATH on a Wayland session.
- [ ] Tests with a throwaway `$HOME`; README lines for each.
- [ ] Possibly worth a README line: in GNOME Terminal an Alt chord can arrive as Esc plus
      the letter (herdr logs `flushing lone escape after input timeout`).

## A desktop launcher: herdr in its own Ghostty window

On GNOME the dock icon and Super+C should open herdr in Ghostty, as its own app (the
sheep icon, not grouped under Ghostty), and focus the window when it's already open.
Working version on the Ubuntu machine, to ship from the playbook on non-Omarchy GNOME
machines (Omarchy has its own launcher):

`~/.local/share/applications/dev.herdr.Herdr.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=herdr
Comment=Claude Code sessions in herdr
Exec=<home>/.local/bin/herdr-window
Icon=herdr
Terminal=false
Categories=Development;TerminalEmulator;
StartupWMClass=dev.herdr.Herdr
StartupNotify=true
```

`~/.local/bin/herdr-window`:

```bash
#!/usr/bin/env bash
# Show herdr in its own Ghostty window (dock icon + Super+C).
# Ghostty runs under the app id dev.herdr.Herdr, so GNOME matches its window to
# dev.herdr.Herdr.desktop: the dock shows the sheep and focuses the open window
# instead of grouping it under Ghostty.
set -u
# GNOME starts us without the login-shell PATH; herdr popups (cs -> fzf) need Homebrew.
[ -x /home/linuxbrew/.linuxbrew/bin/brew ] && eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
APP_ID=dev.herdr.Herdr
GHOSTTY=$(command -v ghostty || echo /snap/bin/ghostty)

# A herdr window is open when a herdr client runs under a Ghostty with this app id.
window_open() {
  local term
  for term in $(pgrep -f -- "--class=$APP_ID"); do
    pgrep -P "$term" -x herdr >/dev/null && return 0
    for shell in $(pgrep -P "$term"); do pgrep -P "$shell" -x herdr >/dev/null && return 0; done
  done
  return 1
}

if window_open; then
  # Bring the existing window forward.
  gdbus call --session --dest "$APP_ID" --object-path "/${APP_ID//.//}" \
    --method org.freedesktop.Application.Activate '{}' >/dev/null 2>&1 && exit 0
fi

exec "$GHOSTTY" --class="$APP_ID" --gtk-single-instance=true --maximize=true \
  --title=herdr --quit-after-last-window-closed=true -e "$HOME/.local/bin/herdr"
```

Notes:

- `--class` is what GNOME matches against `StartupWMClass`; with
  `--gtk-single-instance=true` Ghostty also takes that D-Bus name, so `Activate` on it
  raises the open window without opening a second one (checked: no extra window or shell).
- Started from inside a herdr pane (tests, a Claude session), herdr refuses to run nested
  ("nested herdr is disabled by default") because the `HERDR_*` variables are inherited,
  and Ghostty shows "abnormal process exit". From the dock there are none. Test with
  `env -u HERDR_ENV -u HERDR_PANE_ID ...` (all `HERDR_*`).
- The previous version ran a separate `gnome-terminal-server --app-id dev.herdr.Herdr`;
  keep it as the fallback when Ghostty isn't installed.

## Tasks for the launcher

- [ ] Ship `files/herdr/herdr-window` and the desktop file (home path filled in), only
      on GNOME without Omarchy; Ghostty when installed, GNOME Terminal otherwise.
- [ ] Icon: install the sheep as the `herdr` icon if none is there.
- [ ] Tests with a throwaway `$HOME`.
