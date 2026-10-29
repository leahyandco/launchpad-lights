# lpctl

lpctl turns an original Novation Launchpad Mini into a desktop controller for Windows. It does audio visualisation, now playing, a macro pad, and a clock with a Pomodoro timer. It runs from the system tray.

It targets the red/green Launchpad Mini (MK1 and MK2). The Mini MK3, Launchpad X and other RGB models use a different protocol and are not supported.

## What it does

| Mode | What you get |
|---|---|
| Visualiser | 13 views driven by whatever the PC is playing. Auto gain keeps it readable at any volume. BPM detection, auto-cycling views and single-app capture. |
| Now playing | Scrolls the current track from Spotify, browsers, Netflix or anything else that shows up in Windows media controls. Side buttons skip and pause. |
| Macro pad | 8 pages of 64 buttons: media keys, hotkeys, commands, URLs and mic mute. Edit them in the settings window. |
| Clock | Scrolling clock, binary clock, and a Pomodoro timer that drains the grid as it runs. |
| Test pattern | Lights every LED in every colour and echoes every button press. Use it to check the hardware. |

You can unplug the Launchpad, switch from headphones to speakers, or restart Spotify. lpctl recovers on its own within a few seconds.

## Requirements

- Windows 10 or 11. Single-app capture needs Windows 10 2004 or later.
- [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and the dependencies for you.
- A Launchpad Mini MK1 or MK2. The built-in Windows USB MIDI driver works, so you don't need the Novation driver.

## Install

```
git clone https://github.com/leahyandco/launchpad-lights.git
cd launchpad-lights
uv run lpctl
```

The first run downloads Python and the dependencies. After that, the settings window opens and the icon appears in the tray.

Windows lets only one app open the Launchpad at a time. Close Ableton, Novation Components and any other MIDI software first. If something else has the port, lpctl logs the problem and retries every 2 seconds until the port is free.

## Running it

| Command | What it does |
|---|---|
| `uv run lpctl` | Tray icon and settings window. |
| `uv run lpctl --hidden` | Tray icon only. Start with Windows uses this. |
| `uv run lpctl --no-gui` | Headless. Ctrl+C to quit. |
| `uv run lpctl --test` | Hardware smoke test. Lights every LED and prints every button press. |
| `uv run lpctl --simulate` | Draws the Launchpad in the terminal instead of using the device. Keys 1-8 are the top buttons, a-h are the side buttons and space toggles standby. |
| `uv run lpctl --list-ports` | Lists MIDI ports and audio devices. |
| `uv run lpctl --mode clock` | Starts in a specific mode. |
| `uv run pytest` | Runs the unit tests. |

`flash_test.py` is a standalone check that the Launchpad responds. It doesn't need the rest of the app: `uv run flash_test.py`.

## On the device

The 8 round top buttons pick the mode, and the active one is lit green. Assign modes to them in Settings > Top buttons. The default layout is:

| Top button | Mode |
|---|---|
| 1 | Visualiser |
| 2 | Now playing |
| 3 | Macro pad |
| 4 | Clock |
| 8 | Test pattern |

Holding top button 8 for a second toggles standby, which turns every LED off and stops audio capture. A short press still selects its mode.

The 8 round side buttons belong to whichever mode is active:

| Mode | Side buttons |
|---|---|
| Visualiser | 1-6 pick a view. 7 cycles through the other 7 views and lights amber while one of them is showing. 8 cycles auto-gain speed: green is low, amber medium, red high. |
| Now playing | 1 previous, 2 play/pause, 3 next. |
| Macro pad | 1-8 switch pages. Pages that have buttons are lit dim green. |
| Clock | 1 scrolling clock, 2 binary clock, 3 Pomodoro. In Pomodoro, 6 starts and pauses, 7 resets, and any pad also starts and pauses. |

## Settings window

The preview on the left mirrors the Launchpad live. Clicking it works the same as pressing the real buttons.

Closing the window hides it to the tray, and lpctl keeps running. To exit, use Quit in the window or the tray menu. Quitting turns all the LEDs off.

The tabs:

- **Visualiser**: view, auto-cycle, live BPM.
- **Audio**: capture source (whole system or one app), auto gain, gain, range, noise gate.
- **Macro pad**: click a pad and set its label, action, value and colour. Test runs the action without saving it.
- **Clock**: view, 24-hour time, Pomodoro lengths, start/pause and reset.
- **Top buttons**: which mode each top button selects.
- **General**: start with Windows, and buttons to open the config folder and the logs.

The tray menu covers the quick stuff: modes, visualiser view, auto-cycle, auto gain, standby, start with Windows and quit.

## Start with Windows

Tick Settings > General > Start with Windows, or use the tray menu. This adds a per-user `Run` registry entry that starts `pythonw.exe -m lpctl --hidden` from this folder's virtual environment. It doesn't need admin rights.

The path is fixed when you tick the box. If you move the folder, untick it and tick it again.

## Config and logs

Settings live in `%APPDATA%\lpctl\config.toml`. lpctl creates the file on first run and rewrites it whenever you change something, so comments you add get lost. Use the settings window. `config.example.toml` documents every key.

Logs go to `%APPDATA%\lpctl\logs\lpctl.log`. That file is rotated at 1 MB and three old copies are kept. It records device connects and disconnects, audio device changes, mode switches and errors. It doesn't log per frame.

## Docs

- [Macro pad](docs/macro-pad.md): actions, key names, colours, examples.
- [Audio](docs/audio.md): capture, gain, single-app capture, BPM, auto-cycle.
- [Writing a mode](docs/writing-a-mode.md): adding your own mode.
- [Troubleshooting](docs/troubleshooting.md)
- [Changelog](CHANGELOG.md)

## Licence

MIT. See [LICENSE](LICENSE).
