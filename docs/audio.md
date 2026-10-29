# Audio

The visualiser listens to what the PC is playing, not to a microphone. It uses WASAPI loopback, which needs no cables and no virtual audio device.

## Capture source

Set it in Settings > Audio > Capture from.

**System (all apps)** is the default. It captures the default output device. If you change the default, for example from speakers to headphones, apps move their playback and the old device goes silent. After 3 seconds of silence Launchpad Lights reopens on the new default, so it follows the switch in about 3 to 5 seconds.

**A single app** captures one program and ignores everything else. Discord pings, YouTube in another tab and system sounds don't show up. The list shows apps that are making sound right now. You can also type an executable name such as `Spotify.exe` into the box and press Enter.

Single-app capture includes the app's child processes. That matters for browsers, because Chrome, Edge and Firefox play audio from a child process, not the main one. If the app isn't running, Launchpad Lights logs it once and keeps retrying. If the app restarts, Launchpad Lights reattaches after 3 seconds of silence.

Single-app capture needs Windows 10 2004 or later.

## Gain

Auto gain is on by default. Leave it on. The display adapts to the volume, so it looks the same at 10% and 100%.

| Setting | Default | What it does |
|---|---|---|
| Auto gain | On | Tracks the loudest recent sound and scales the bars to it. Off uses a fixed reference instead, and loud mastered music fills the bars at 0 dB gain. |
| Speed | Medium | How fast auto gain lets go after a loud part. Low recovers at 1.5 dB/s, medium 4 dB/s, high 10 dB/s. High suits music with big dynamics. Low keeps quiet intros quiet. |
| Gain | 0 dB | Shifts everything up or down, with or without auto gain. Raise it if the bars never reach the top. |
| Range | 32 dB | How far below the loudest sound a pad still lights. Lower is punchier, with more contrast and fewer lit pads. Higher shows more detail. |
| Noise gate | -75 dB | Anything quieter than this never lights a pad. Raise it if hiss or a noisy source leaves the display flickering when nothing is playing. |

Reset to defaults puts all of these back.

Side button 8 on the device cycles the speed. Its LED is green for low, amber for medium and red for high.

## Bands

The spectrum is split into 8 bands from 40 Hz to 16 kHz, spaced logarithmically, so each band covers roughly an octave. Higher bands get a small boost because music carries less energy up there. Without it the right-hand columns would barely move.

Bars rise instantly and fall over about a quarter of a second.

## BPM

BPM comes from kicks in the two lowest bands. Launchpad Lights takes the median gap between the last few beats and folds it into the 70-180 BPM range.

- It needs about 4 beats before it shows a number.
- It drops back to "listening" after 4 seconds without a beat.
- It reports the pulse it hears. A 170 BPM drum and bass track with a half-time feel can read as 85. A 60 BPM ballad reads as 120.
- Music without a clear kick (ambient, solo piano, a lot of classical) won't produce a stable reading.

## Auto-cycle

Settings > Visualiser > Auto-cycle jumps to a random view every N beats (32 by default, which is 8 bars of 4/4). Because it counts beats, the switch lands on a beat. If there's no clear beat, it falls back to a timer (20 seconds by default).

## Idle

After 30 seconds of silence the visualiser switches to a slow, dim idle animation and drops its frame rate. It switches back the moment sound returns. Set `idle_style = "blank"` in the config to turn the grid off instead.
