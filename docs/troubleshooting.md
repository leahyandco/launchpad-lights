# Troubleshooting

Check the log first. It's at `%APPDATA%\Launchpad Lights\logs\launchpad-lights.log`, or click Settings > General > Open logs. Launchpad Lights logs every connect, disconnect, device change and error.

## "Windows protected your PC"

That's Windows SmartScreen. It warns about any exe that isn't code-signed and that it hasn't seen many people run, which is most small free apps. It's fine to get past it. Click **More info**, then **Run anyway**. Windows only asks the first time.

## Launchpad not found

The status line at the top of the settings window says "Launchpad not found", and the log says `No MIDI output matching 'Launchpad Mini'`.

Both also list the MIDI outputs Windows can see. If no Launchpad is in that list, Windows hasn't picked it up:

1. Try another USB port or cable. Plug it straight into the PC, not a hub.
2. Open Device Manager and look under "Sound, video and game controllers". The Launchpad should be there.

If the Launchpad is in the list under a different name, put part of that name in Settings > General > Advanced > MIDI port name.

## Port blocked

The log says `Found 'Launchpad Mini 1' but could not open it`.

Another app has the port, and this Windows build allows only one. The usual cause is Ableton, Novation Components or a DAW. Close it. Launchpad Lights keeps retrying and connects on its own once the port is free.

Newer Windows 11 builds let several apps share the port, so you won't see this error there. If the LEDs flicker or show the wrong thing, another app is drawing on the grid at the same time. Close it. Launchpad Lights resends the whole display every 5 seconds, so anything another app overwrote corrects itself.

## "Launchpad Lights is already running"

Launchpad Lights allows only one copy of itself at a time. The other copy is in the tray, so open it from there or quit it first. If no tray icon is visible, check Task Manager for a leftover `LaunchpadLights.exe`. When running from source it shows as `pythonw.exe`, `python.exe` or `launchpad-lights.exe`.

## LEDs work, buttons don't

Windows exposes input and output as separate ports. If the log says `Opened output but not input`, something else has the input port. Same fix as above.

## Visualiser is flat

1. Switch to the Visualiser, then check the status line at the top of the settings window. It shows which device or app Launchpad Lights is capturing.
2. If it's capturing the wrong device, make sure the right output is the Windows default. Then wait 3 seconds of silence, or restart Launchpad Lights.
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

Start with Windows remembers where `LaunchpadLights.exe` (or your source folder) was when you ticked the box. If you've moved it since, start Launchpad Lights once from the new place and it fixes the entry itself. If that doesn't do it, untick and retick Start with Windows.

To see the exact command, look at the `Launchpad Lights` value under `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` in regedit.

## LEDs lag or tear

The visualiser runs at 40 fps by default, and big changes are sent as a single rapid update. If it can't keep up on your machine, lower Visualiser frame rate in Settings > General > Advanced.

If the LEDs show garbage after a big change, turn off rapid updates. That's slower, but every LED is addressed individually. It's only in the config file, so quit Launchpad Lights first, set `rapid_update = false` under `[device]` in `config.toml`, then start it again.

## Settings went back to defaults

`config.toml` had a syntax error, usually from a hand edit. The broken file is next to it as `config.bad.toml`, and the log says what was wrong with it. Copy your changes across, or set them again in the settings window.

## "Launchpad Lights hit an error and stopped"

The render loop crashed. The full error is in the log. Restart Launchpad Lights. If it happens again, [open an issue](https://github.com/leahyandco/launchpad-lights/issues/new/choose) and attach the log.

## Nothing above helped

Rule out the hardware. Select Test pattern (top button 8 by default). It walks every LED through red, green and amber, then every colour level, and any button you hold lights red. If all of that works, the Launchpad is fine.

If you're running from source, quit the tray copy first and run `uv run launchpad-lights --test`. It does the same and prints every button press.

Still stuck? [Open an issue](https://github.com/leahyandco/launchpad-lights/issues/new/choose) with the log attached.
