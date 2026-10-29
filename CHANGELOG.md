# Changelog

## Unreleased

- Windows exe built with PyInstaller (`packaging\build.ps1`).
- Small 3x5 font for scrolling text, now the default. It fits about two characters on screen at once. The 5x7 font is still available in Settings > General.
- Flip clock view: hours, then minutes, with no scrolling.
- Only one copy of lpctl runs at a time.
- The whole display is resent every 5 seconds, so LEDs another app overwrote correct themselves.
- A crash in the render loop is now written to the log, and the settings window shows an error instead of vanishing.
- A MIDI backend error while reconnecting no longer stops the app.

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
