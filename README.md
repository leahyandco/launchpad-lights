# lpctl

A Windows controller for the original Novation Launchpad Mini (MK1/MK2, red/green LEDs) with
pluggable modes: an audio visualiser, now playing, a macro pad, a clock and Pomodoro timer.
Runs from the system tray with a settings window.

## Features

- **Audio visualiser**: 13 views (spectrum, mirrored, spectrogram, VU, beat pulse, fire, radial,
  fountain, sparkle, plasma, centre spectrum, horizontal bars, bouncing dots). Auto gain works
  at any volume, with manual gain, range and noise gate controls. BPM detection. Optionally
  cycles views on the beat.
- **Single-app capture**: visualise just Spotify, a browser or any other app instead of
  everything the PC plays (Windows 10 2004 or later).
- **Now playing**: scrolls the current track from any app with Windows media controls.
- **Macro pad**: 8 pages of 64 buttons. Each button can be a media key, hotkey, command, URL
  or mic mute (lit red/green to show the mute state). Edit them in the settings window.
- **Clock**: scrolling clock, binary clock, and a Pomodoro timer that drains the grid.
- **Tray icon and settings window**: live clickable preview, every option, start with Windows.
- Survives unplugging the Launchpad and changes of default audio device.

## Install and run

Requires Windows 10/11 and [uv](https://docs.astral.sh/uv/).

```
uv run lpctl               # tray icon + settings window
uv run lpctl --hidden      # tray icon only
uv run lpctl --no-gui      # headless
uv run lpctl --test        # hardware smoke test, echoes button presses
uv run lpctl --simulate    # draw in the terminal instead of the device
uv run lpctl --list-ports  # MIDI ports and audio devices
uv run pytest              # unit tests
```

The Launchpad Mini works with the built-in Windows USB MIDI driver. Close Ableton, Novation
Components or anything else using the Launchpad first: Windows only lets one app open it.

`flash_test.py` is a standalone quick check that the Launchpad responds: `uv run flash_test.py`.

## On the device

- Top buttons 1-8 select modes (assign them in Settings > Top buttons). The active one is lit.
- Hold top button 8 for 1 s: standby (all LEDs off). Hold again to wake.
- The right-hand side buttons belong to the active mode:
  - Visualiser: 1-6 pick a view, 7 cycles the other views, 8 cycles auto-gain speed.
  - Now playing: 1 previous, 2 play/pause, 3 next.
  - Macro pad: 1-8 switch pages.
  - Clock: 1 clock, 2 binary clock, 3 Pomodoro (6 start/pause, 7 reset; any pad also starts/pauses).

## Config and logs

`%APPDATA%\lpctl\config.toml` is created on first run. See `config.example.toml`. Everything in
it can also be changed in the settings window. Logs: `%APPDATA%\lpctl\logs\lpctl.log`.

## Adding a mode

Create `src/lpctl/modes/<name>.py` with a `@register`ed `Mode` subclass whose `name` is `<name>`.
It then shows up under Settings > Top buttons. Modes draw into a `Frame` (8x8 grid plus 8 side
and 8 top LEDs, each a `(red, green)` pair from 0 to 3) and never touch MIDI. Shared resources
(audio capture, media info) are services listed in `Mode.services`, and they only run while a
mode that needs them is active.

## Licence

MIT
