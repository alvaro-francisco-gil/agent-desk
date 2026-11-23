# Dictation on F9 on every machine

**Goal:** the Omarchy workstation's dictation keys work the same on a stock Ubuntu
GNOME machine and on Windows: F9 held to talk, Alt+F9 to start and stop, Shift+F9 to
copy the last dictation, English and Spanish.

## Decided (owner, 2026-11-23)

1. **Ubuntu: voxtype on the machine itself**, the Omarchy engine, so the same words
   and replacements carry. The model is large-v3-turbo on the GPU
   (`voxtype setup gpu --enable`); when the GPU isn't there, voxtype's whisper falls
   back to the CPU. Audio never leaves the machine.
2. **Ubuntu keys:** GNOME custom shortcuts only fire on press, so F9 held is voxtype's
   own evdev watcher (`[hotkey]`, needs the `input` group); Alt+F9 and Shift+F9 are
   GNOME custom shortcuts. Root steps are the README's, done once by hand.
3. **Windows (SSH into a herdr machine, or a WSL distro):** WSL never sees the keys and
   voxtype in WSL can't type into Windows Terminal; AutoHotkey was blocked by Defender
   on one laptop and PowerToys can't hold-to-talk. Try a native Windows dictation app
   (Handy) with F9 held; check what it can do for Alt+F9 and Shift+F9. After Ubuntu.
4. **Here only the portable part**: config with a neutral vocabulary, the keys,
   `voxtype-last`. A person's own words stay in their machine's config, which the
   install writes once and never replaces.

## Steps

1. ✅ `tasks/dictation.yml`, `files/dictation/`, opt-in `-e agent_desk_dictation=true`, tests.
2. On the Ubuntu machine: the README's root steps, `git pull`, the install with the
   flag. Check: F9 held pastes in Ghostty and Chrome (Shift+Insert pastes the
   clipboard in Ghostty only with agent-desk's Ghostty config, `ghostty-everywhere`);
   Alt+F9 is free in GNOME; Shift+F9 copies and does not also start a recording
   through the F9 watcher (if it does, move the watcher to `modifiers` or another key);
   `voxtype doctor` names the typing helper; how quick it is with and without the GPU.
3. Windows: prototype with Handy; a `dictation.ps1` here if it holds up.
4. The Omarchy workstation's own setup uses `files/dictation/voxtype-last` from here
   instead of its copy, so the two stay one.
