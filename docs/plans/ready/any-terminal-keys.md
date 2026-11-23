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
