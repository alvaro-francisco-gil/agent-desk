# agent-desk

Keyboard shortcuts and small tools for running Claude Code sessions in
[herdr](https://herdr.dev), the same way on every machine.

It holds the shortcuts and the tools, never a list of repos: which repos a machine
works on is a file on that machine.

## Windows Terminal (SSH into a herdr machine)

Windows Terminal keeps Alt+Enter, Alt+arrows and Alt+Shift+arrows for itself, so herdr
never sees them. In PowerShell on the Windows machine:

```powershell
irm https://raw.githubusercontent.com/alvaro-francisco-gil/agent-desk/main/wt.ps1 | iex
```

It frees those keys, makes Alt+R type `/rename `, and keeps a copy of the old
settings next to `settings.json`. Running it again changes nothing more. Alt+Esc stays
with Windows; in herdr, Ctrl+Space then X closes a pane.
