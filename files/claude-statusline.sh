#!/bin/bash
# Claude Code status line: session name · repo · branch · context used. Installed to
# ~/.claude/statusline.sh by tasks/agent_sessions.yml.
input=$(cat)
name=$(jq -r '.session_name // empty' <<<"$input")
dir=$(jq -r '.workspace.project_dir // .cwd' <<<"$input")
repo=${dir#"$HOME/githubs/"}
[[ $dir == "$HOME/githubs" ]] && repo=githubs
branch=$(git -C "$dir" branch --show-current 2>/dev/null)
ctx=$(jq -r '.context_window.used_percentage // empty | floor' <<<"$input")

printf '\e[1;36m%s\e[0m' "${name:-unnamed — /rename to name it}"
printf ' · %s' "$repo"
if [[ -n $branch ]]; then
  printf ' · \e[2m%s\e[0m' "$branch"
fi
# Yellow from 35%: auto-compact runs at 45% (autoCompactWindow in settings.json).
if [[ -n $ctx ]]; then
  if ((ctx >= 35)); then
    printf ' · \e[33m%s%%\e[0m' "$ctx"
  else
    printf ' · \e[2m%s%%\e[0m' "$ctx"
  fi
fi
