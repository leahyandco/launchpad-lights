# Troubleshooting

Check the log first: `%APPDATA%\Launchpad Lights\logs\launchpad-lights.log`, or Settings > General > Open logs. Launchpad Lights logs every connect, disconnect, device change and error.

## Launchpad not found

The log says `No MIDI output matching 'Launchpad Mini'`.

Run `uv run launchpad-lights --list-ports`. If no Launchpad is listed, Windows hasn't picked it up. Try another USB port or cable, and check that it shows in Device Manager under "Sound, video and game controllers". If Windows lists it under a different name, set `port_name` in `[device]` to part of that name.

## Port blocked

The log says `Found 'Launchpad Mini 1' but could not open it`.

Another app has the port, and this Windows build allows only one. The usual cause is Ableton, Novation Components or a DAW. Close it. Launchpad Lights keeps retrying and connects on its own once the port is free.

Newer Windows 11 builds let several apps share the port, so you won't see this error there. If the LEDs flicker or show the wrong thing, another app is drawing on the grid at the same time. Close it. Launchpad Lights resends the whole display every 5 seconds, so anything another app overwrote corrects itself.

## "Launchpad Lights is already running"

Launchpad Lights allows only one copy of itself at a time. The other copy is in the tray, so open it from there or quit it first. If no tray icon is visible, check Task Manager for a leftover `LaunchpadLights.exe` or `pythonw.exe`.

## LEDs work, buttons don't

Windows exposes input and output as separate ports. If the log says `Opened output but not input`, something else has the input port. Same fix as above.

## Visualiser is flat

1. Check the status line at the top of the settings window. It shows which device or app Launchpad Lights is capturing.
2. If it's capturing the wrong device, make sure the right output is the Windows default. Then wait 3 seconds of silence, or restart launchpad_lights.
3. If Capture from is set to an app, make sure that app is the one playing. Set it back to System to rule it out.
4. If the bars move but never fill, raise Gain or lower Range in Settings > Audio.
5. If the bars flicker with nothing playing, raise the noise gate.

After 30 seconds of silence the visualiser switches to a dim idle animation. That's normal.

## Single-app capture fails

`<app>.exe is not running`: the app isn't running, or the name is wrong. Pick it from the list instead of typing it.

`Process loopback activation failed`: Windows is older than 10 2004. Update Windows or use System capture.

## Now playing shows nothing

Now playing reads Windows media sessions. It only shows something if the app shows up in the volume flyout's media controls. Spotify, Chrome, Edge, Firefox and most media apps do. Some games and old players don't.

## Mic mute pad is dim amber

Windows reports no default recording device. Plug one in or set one in Sound settings. The pad updates within half a second.

## Hotkey macro does nothing

The keystroke goes to the focused window. If that window belongs to an app running as administrator and Launchpad Lights isn't, Windows blocks the input. That's Windows UI isolation, and Launchpad Lights can't get around it. Use a global hotkey that the target app registers, or run Launchpad Lights at the same privilege level.

## Start with Windows doesn't start

The registry entry points at this folder's `.venv`. If you moved or recloned the folder, or deleted `.venv`, untick and retick Start with Windows. Check `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\Launchpad Lights` if you want to see the exact command.

## LEDs lag or tear

The visualiser runs at 40 fps by default, and big changes are sent as a single rapid update. If it can't keep up on your machine, lower `fps` in `[visualiser]`. If the LEDs show garbage after a big change, set `rapid_update = false` in `[device]`. That's slower, but every LED is addressed individually.

## Settings went back to defaults

`config.toml` had a syntax error, usually from a hand edit. The broken file is next to it as `config.bad.toml`, and the log says what was wrong with it. Copy your changes across, or set them again in the settings window.

## "Launchpad Lights hit an error and stopped"

The render loop crashed. The full traceback is in the log. Restart launchpad_lights. If it happens again, the log entry is what's needed to fix it.

## Nothing above helped

Run `uv run launchpad-lights --no-gui -v` from a terminal for debug logging. Then run `uv run launchpad-lights --test` to rule out the hardware. If every LED lights in every colour and every press is echoed, the Launchpad is fine.
