# Macro pad

The macro pad turns the grid into buttons that run actions. There are 8 pages of 64 pads, and side buttons 1-8 switch between them.

Pressing a pad flashes it and runs its action on a background thread. A slow command can't stall the LEDs.

## Editing buttons

Use Settings > Macro pad.

1. Pick the page.
2. Click a pad.
3. Set the label, action, value and colour.
4. Hit Test to try it without saving.
5. Hit Save.

Clear removes the button. Changes go live on the device as soon as you save.

You can also edit `[[macro_pad.buttons]]` in `config.toml` by hand while lpctl isn't running. Each button looks like this:

```toml
[[macro_pad.buttons]]
page = 1          # 1-8
x = 0             # 0-7, left to right
y = 0             # 0-7, top to bottom
action = "media"
value = "play_pause"
colour = "green"
label = "Play"
```

## Actions

| Action | Value | What it does |
|---|---|---|
| `media` | `play_pause`, `next`, `prev`, `stop`, `mute`, `vol_up`, `vol_down` | Sends the Windows media key. It works with whatever app owns media playback, the same as the keys on a keyboard. |
| `key` | A combo such as `ctrl+shift+m` | Presses the keys in order, then releases them in reverse. The keystroke goes to whichever window has focus. |
| `run` | A command line | Starts the program. Windows parses the command line, so quote paths that contain spaces. |
| `url` | A URL or file path | Opens it with the default app, the same as double-clicking it. |
| `mic_mute` | Nothing | Toggles mute on the default recording device. |

### Key names

Letters and digits are written as themselves: `a`, `7`. Join keys with `+`.

| Type | Names |
|---|---|
| Modifiers | `ctrl`, `shift`, `alt`, `win` |
| Function keys | `f1` to `f24` |
| Navigation | `left`, `right`, `up`, `down`, `home`, `end`, `pageup`, `pagedown`, `insert`, `delete` |
| Other | `esc`, `enter`, `tab`, `space`, `backspace`, `printscreen`, `pause`, `capslock` |
| Media | `play_pause`, `next`, `prev`, `stop`, `mute`, `vol_up`, `vol_down` |

`f13` to `f24` are worth using. No keyboard has them, so they never clash with anything, and most apps let you bind them as global hotkeys. Bind a Discord or OBS hotkey to `ctrl+alt+f13` and put that on a pad.

### Run

`run` doesn't go through a shell. Batch files and executables work as they are. Shell built-ins (`echo`, `start`, `dir`) and pipes need `cmd /c`.

```
notepad.exe
"C:\Program Files\Some App\app.exe" --flag
C:\Scripts\vpn.bat connect
cmd /c start "" "C:\Users\me\Downloads"
powershell -NoProfile -WindowStyle Hidden -File C:\Scripts\toggle-output.ps1
```

The program runs as you, with your permissions. lpctl doesn't wait for it to finish and doesn't capture its output.

### Mic mute

A `mic_mute` pad ignores its colour setting. Its colour shows the state, which lpctl checks twice a second:

| Colour | Meaning |
|---|---|
| Green | Mic live |
| Red | Mic muted |
| Dim amber | No recording device found |

It mutes the Windows endpoint, so every app loses the mic, not just one. If you mute somewhere else, for example in the Sound settings or with a headset button, the pad picks it up within half a second.

## Colours

The Launchpad Mini has a red and a green LED under each pad. Every colour is a mix of the two:

| Name | Red | Green |
|---|---|---|
| `red` | 3 | 0 |
| `orange` | 3 | 1 |
| `light_orange` | 3 | 2 |
| `amber` | 3 | 3 |
| `yellow` | 2 | 3 |
| `lime` | 1 | 3 |
| `green` | 0 | 3 |
| `red_dim` | 1 | 0 |
| `amber_dim` | 1 | 1 |
| `green_dim` | 0 | 1 |

Use dim colours for buttons you rarely press, so the important ones stand out.

## Defaults

Page 1 comes set up with:

- **Row 1:** media controls (previous, play, next, stop, volume down, volume up, mute).
- **Row 3:** mic mute.
- **Row 5:** show desktop, screen snip, Task Manager.
- **Row 7:** Calculator, Notepad, YouTube.

Change or clear any of them.
