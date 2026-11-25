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

## Ubuntu findings (2026-11-23, Ubuntu 26.04 GNOME, Intel Iris Xe)

- Install with `-e agent_desk_dictation=true` ran clean; model downloaded, service active.
- `voxtype doctor` before ydotool: "No text output method available for mode 'paste'"
  (wtype doesn't work on GNOME) and no readable input device. Fixed by `ydotool` from
  apt (ships the `/dev/uinput` rule and a `ydotool` user service) plus the `input` group.
- With lingering on, logging out doesn't refresh the user services' groups: `ydotoold`
  exits with status 2 until a reboot. README now says reboot.
- After the reboot (2026-11-24): `voxtype doctor` all green (24 of 24 input devices,
  output method paste, Vulkan GPU), and the journal shows the paste going through
  ydotool (`Paste keystroke sent via ydotool`, Shift+Insert). No playbook change needed.
- Still to check by hand: F9 held in Ghostty and Chrome, Alt+F9, Shift+F9 without a
  stray recording, speed on the GPU.
- **Speed (2026-11-24).** This laptop has Intel Iris Xe and an NVIDIA RTX 3050 Ti.
  Whisper large-v3-turbo ran on the Intel one (Vulkan0) and reloaded per dictation:
  7.6 s of audio took 10 s, 2.5 s took 18.7 s. Switched to Parakeet
  (`parakeet-tdt-0.6b-v3-Q8_0.gguf`, English and Spanish): it loads once on the NVIDIA
  card (Vulkan1) in 1.1 s, and 35.7 s of audio took 8.7 s. Candidate default for a
  machine with a dedicated GPU; check what the Omarchy workstation uses and how fast.
- **Words.** Parakeet ignores `whisper.initial_prompt`; only `[text] replacements` apply
  (`voxtype history rule "<heard>" "<meant>"` adds one). Added here: "homear key",
  "homarchy", "omar key" -> "Omarchy".
- **Popup.** Omarchy's voxtype popup is the Quickshell frontend; Ubuntu has no
  Quickshell package and GNOME lacks layer-shell, so Ubuntu keeps the gtk4 popup.

## Next, on the Omarchy workstation

- [ ] Compare its voxtype engine, model and `[text] replacements` with
      `files/dictation/voxtype.toml.j2`. Move the general words (tool and product names)
      into the template, so every machine gets them; personal ones stay in that machine's
      config and the owner copies them across by hand.
- [ ] Decide the default engine: Parakeet where a dedicated GPU exists, or keep whisper
      and point it at the right GPU.

- **Shortcuts never reached GNOME (bug).** With Homebrew installed, `gsettings` on PATH
  is Homebrew's (`/home/linuxbrew/.linuxbrew/bin/gsettings`), whose glib has no dconf
  module: it falls back to `~/.config/glib-2.0/settings/keyfile`, which GNOME never
  reads, and reading back with the same binary shows the shortcuts as set. Alt+F9,
  Shift+F9 (and a hand-made Super+C) were dead until rewritten with `/usr/bin/gsettings`.
  Fix: `gnome-shortcuts.py` and the `list-keys` check in `tasks/dictation.yml` call
  `/usr/bin/gsettings` (or check `G_MESSAGES_DEBUG=all gsettings ...` picks
  `GDconfSettingsBackend`); add a test with a fake `gsettings` earlier on PATH.
- **Alt+F9 vs the F9 watcher (bug).** voxtype's evdev watcher sees Alt+F9 as F9: it
  starts a recording on the press and stops it on the release, so `voxtype record
  toggle` from GNOME is ignored ("daemon is Recording") and the release ends it. Worked
  around here with a helper bound to Alt+F9:

  ```bash
  #!/usr/bin/env bash
  # Alt+F9: start dictation, stop it on the next press, around the F9 watcher's blip.
  set -u
  flag="${XDG_RUNTIME_DIR:-/tmp}/voxtype-toggle.on"
  wait_not_recording() {
    for _ in $(seq 40); do
      [ "$(voxtype status 2>/dev/null)" = recording ] || return 0
      sleep 0.05
    done
  }
  if [ -e "$flag" ]; then
    rm -f "$flag"
    sleep 0.4
    [ "$(voxtype status 2>/dev/null)" = recording ] && voxtype record stop
  else
    sleep 0.3
    wait_not_recording
    voxtype record start && touch "$flag"
  fi
  ```

  Verified by hand on Ubuntu (2026-11-24): F9 held, Alt+F9 start/stop and Shift+F9 all
  work. Ship it as `files/dictation/voxtype-toggle` (or drop Alt+F9 if Omarchy doesn't have
  the same clash). Shift+F9 has the same blip but it is harmless (0.2 s, ignored).
- **NVIDIA card fell off the bus (2026-11-25).** After a day of use, a 33 s Parakeet
  dictation on the RTX 3050 Ti hit `ErrorOutOfDeviceMemory`, then kernel Xid 79 "GPU has
  fallen off the bus" (laptop dGPU failing to wake from runtime power saving; needs a
  reboot). The gguf worker crashed and the daemon stayed in `transcribing` forever, so
  every F9 press was ignored. Worked around here with a guard (owner wants the GPU, CPU
  only as fallback): `voxtype-gpu-guard pick` as `ExecStartPre` of voxtype sets
  `parakeet.gguf_backend` to `auto` when `nvidia-smi -L` answers, else `cpu`; a
  `voxtype-gpu-guard.service` loop switches to `cpu`, restarts voxtype and notifies when
  a transcription runs over 30 s or the card stops answering. Candidate for the playbook
  wherever the default model runs on a dedicated GPU.
