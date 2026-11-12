# agent-desk

Keyboard shortcuts and small tools for running Claude Code sessions in
[herdr](https://herdr.dev), the same way on every machine.

It holds the shortcuts and the tools, never a list of repos: which repos a machine
works on is a file on that machine.

## Install on Linux

Needs [herdr](https://herdr.dev), Claude Code, Python 3.11+, `fzf`, `jq` and
`ansible-core`. Then:

```sh
git clone https://github.com/alvaro-francisco-gil/agent-desk ~/agent-desk
cd ~/agent-desk
ansible-playbook -i localhost, -c local install.yml -e '{"agent_desk_repos_folders": ["~/work"]}'
```

`~/work` is wherever your repos are: `cs` (Alt+N in herdr) offers that folder and every
git repo one or two levels inside it. Update with `git pull` and the same command.

What you get in herdr: Alt+N starts Claude in a repo, Alt+P reopens a closed session,
Alt+S parks an agent in a paused list, Alt+W closes a tab and lands on the next active
agent, Alt+Enter opens a shell, Alt+Up/Down move between agents. Alt+R types `/rename `
in Ghostty and foot. Claude Code gets a status line and settings defaults.

## Windows Terminal (SSH into a herdr machine)

Windows Terminal keeps Alt+Enter, Alt+arrows and Alt+Shift+arrows for itself, so herdr
never sees them. In PowerShell on the Windows machine:

```powershell
irm https://raw.githubusercontent.com/alvaro-francisco-gil/agent-desk/main/wt.ps1 | iex
```

It frees those keys, makes Alt+R type `/rename `, and keeps a copy of the old
settings next to `settings.json`. Running it again changes nothing more. Alt+Esc stays
with Windows; in herdr, Ctrl+Space then X closes a pane.

## Open herdr on another machine with one key

```powershell
irm https://raw.githubusercontent.com/alvaro-francisco-gil/agent-desk/main/wt-ssh.ps1 | iex
```

It asks for the SSH target (`user@host`), a name and a key (Win+H by default), then
adds a Windows Terminal profile that runs `herdr` there over SSH, a Start menu shortcut,
and the key, which opens it from anywhere. A key with Win in it runs through
[AutoHotkey](https://www.autohotkey.com), installed with winget when missing; Win+H
takes over Windows voice typing. Everything carries a sheep icon.

## Credits

`sheep.ico` is the 🐑 from [Twemoji](https://github.com/jdecked/twemoji), © Twitter and
contributors, [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).
