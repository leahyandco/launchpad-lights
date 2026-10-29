# Changelog

## Unreleased

- Renamed from lpctl to Launchpad Lights. The command is now `launchpad-lights` and the exe `LaunchpadLights.exe`. Settings move from `%APPDATA%\lpctl` to `%APPDATA%\Launchpad Lights` automatically on first run, and an existing start-with-Windows entry is switched to the new name.
- Windows exe built with PyInstaller (`packaging\build.ps1`).
- Small 3x5 font for scrolling text, now the default. It fits about two characters on screen at once. The 5x7 font is still available in Settings > General.
- Flip clock view: hours, then minutes, with no scrolling.
- Only one copy of Launchpad Lights runs at a time.
- The whole display is resent every 5 seconds, so LEDs another app overwrote correct themselves.
- A crash in the render loop is now written to the log, and the settings window shows an error instead of vanishing.
- A MIDI backend error while reconnecting no longer stops the app.
- Settings window: side-button labels next to the preview, a clear connected/not-found status line, an Advanced section for settings that used to be config-only, Esc hides and Ctrl+Q quits, and sharp text on scaled displays.
- Macro editor: validates key combos and media keys before saving, Browse for programs and files, a 2 s delay when testing hotkeys, and clearer selection.
- Pomodoro runs whichever mode is on screen, catches up after time away, keeps elapsed time when paused, picks up new lengths before starting, and notifies from the tray when a phase ends.
- A mode can only sit on one top button. Unassigning the active mode switches to another one.
- Start with Windows fixes itself if the folder or exe it pointed at has moved.
- Fixed: switching macro page then saving wrote the button to the wrong page.
- Fixed: a long status message made the settings window wider than the screen.
- Fixed: several settings didn't update when changed from the device or tray.
- Fixed: spinboxes showed one value and saved another.
- Fixed: a typo in config.toml, a wrong value type, or a macro button off the grid could stop the app.
- Fixed: a mode that fails no longer takes the app down. It's stopped and logged.
- Fixed: LEDs could stay lit after quitting while audio was shutting down.
- Fixed: the first two visualiser bands were identical at 96 kHz and above.
- Fixed: scrolling text paused for a moment as it entered, and the scrolling clock restarted every minute.

## 0.1.0 (2026-10-29)

First release.

- Visualiser with 13 views: spectrum, mirrored, spectrogram, VU, beat pulse, fire, radial, fountain, sparkle, plasma, centre spectrum, horizontal bars, bouncing dots.
- Auto gain with manual gain, range and noise gate. BPM detection. Auto-cycling views on the beat.
- Capture of the whole system, or of a single app through WASAPI process loopback.
- Now playing from Windows media sessions, with previous, play/pause and next on the side buttons.
- Macro pad: 8 pages, with media keys, hotkeys, commands, URLs and mic mute that shows its state.
- Clock: scrolling, binary and Pomodoro.
- Tray icon and a settings window with a live, clickable preview. Choose which mode each top button selects.
- Start with Windows through a per-user Run key. No admin rights needed.
- Recovers on its own after the Launchpad is unplugged, the MIDI port is blocked, or the default audio device changes.
- Hardware smoke test, terminal simulator and port listing.
