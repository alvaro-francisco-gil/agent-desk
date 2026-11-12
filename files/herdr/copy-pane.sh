#!/bin/bash
# SUPER+C in herdr (bound in workstation/hypr/code-left.lua): the focused pane's
# text to the clipboard, long lines unwrapped. herdr hands out at most the last
# 1000 lines, and a Claude pane only what is on screen.
set -euo pipefail

pane=$(herdr pane list | jq -r 'first(.result.panes[] | select(.focused) | .pane_id) // empty')
if [[ -z $pane ]]; then
  notify-send "Nothing copied" "No herdr pane has focus."
  exit 1
fi
text=$(herdr pane read "$pane" --source recent-unwrapped --lines 1000)
printf '%s\n' "$text" | wl-copy
notify-send -t 2000 "Copied the terminal" "$(printf '%s\n' "$text" | wc -l) lines"
