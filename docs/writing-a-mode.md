# Writing a mode

A mode is one Python file in `src/launchpad_lights/modes/`. Drop it in, restart Launchpad Lights, and assign it to a top button in Settings > Top buttons. Nothing else needs registering.

This needs the source version (see Run from source in the README). The exe has its modes built in, so a new mode only gets into an exe if you build one yourself.

Modes never talk to MIDI. They draw into a frame, and the app works out which LEDs changed and sends only those. That keeps MIDI traffic down and means you can build and test a mode without the Launchpad plugged in.

## Minimal example

`src/launchpad_lights/modes/paint.py`:

```python
"""Toggle pads on and off by pressing them."""
from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.frame import Frame
from launchpad_lights.modes.base import Mode
from launchpad_lights.modes.registry import register


@register
class Paint(Mode):
    name = "paint"  # must match the file name
    fps = 30

    def __init__(self, ctx):
        super().__init__(ctx)
        self.lit: set[int] = set()

    def on_event(self, event: ButtonEvent) -> None:
        if event.kind == "pad" and event.pressed:
            self.lit ^= {event.index}

    def render(self, frame: Frame, dt: float) -> None:
        for i in self.lit:
            frame.leds[i] = (3, 3)
```

Try it:

```
uv run launchpad-lights --mode paint
```

You don't need the Launchpad plugged in. Click the pads in the preview on the left of the settings window and they act like the real buttons. There's also `--simulate`, which draws the grid in the terminal, but it only has keys for the top and side buttons, so it can't press pads.

## The Mode class

| Member | Purpose |
|---|---|
| `name` | Mode name. Must match the module name, because that's how the registry finds it. |
| `fps` | Target frame rate, from 1 to 120. You can change it at runtime. The visualiser drops to 15 fps when idle. |
| `side_labels` | Up to 8 short strings saying what each side button does. The settings window shows them next to the preview. |
| `services` | Tuple of services the mode needs, such as `("audio",)`. The app starts them before `on_enter` and stops them after `on_exit` if nothing else needs them. |
| `on_enter()` | Called when the mode becomes active. |
| `on_exit()` | Called when the mode is switched away from, or when the app enters standby or quits. |
| `on_event(event)` | Pad and side-button presses and releases. The app keeps the top buttons for itself. |
| `on_config_changed()` | The settings window or tray changed something. Re-read anything you cached from config. |
| `render(frame, dt)` | Draw the current frame. `dt` is the number of seconds since the last frame. |

A new mode instance is created every time the mode is selected. Anything that has to survive a switch, like the Pomodoro timer, goes in a module-level object.

`render` runs on the render thread. Don't block it. Do network calls, file I/O and process launches on another thread, or in a service.

## Frames

A frame is 80 LEDs. Each one is a `(red, green)` tuple with values 0 to 3. Every frame starts blank, so draw everything, every time.

```python
frame.set(x, y, (3, 0))       # grid pad, x and y 0-7 from the top-left. Out-of-range is ignored.
frame.get(x, y)
frame.fill((0, 1))            # whole grid, not the round buttons
frame.set_side(i, (0, 3))     # right-hand side button i, 0-7 from the top
frame.leds[i] = (3, 3)        # raw index: 0-63 grid row by row, 64-71 side, 72-79 top
```

Don't draw on the round top buttons (`frame.leds[72:80]`). The app draws the mode indicator there. The top row of the grid is yours.

There's no real RGB. Red and green mix to orange, amber and yellow. See the colour table in [macro-pad.md](macro-pad.md).

## Events

`ButtonEvent` has `kind` (`"pad"` or `"side"`), `index`, `pressed`, and `x` and `y` for pads. Releases arrive with `pressed=False`. Ignore them unless you need hold behaviour.

## Config

Each mode gets its own config section:

```python
self.cfg = self.ctx.config.section("paint")
speed = float(self.cfg.get("speed", 1.0))
self.cfg["last_colour"] = "green"
self.ctx.save()
```

Add defaults to `DEFAULTS` in `src/launchpad_lights/config.py` so the key shows up in a fresh config file.

## Services

Ask for shared resources through `services` and get them from the context:

```python
services = ("audio",)

def render(self, frame, dt):
    snap = self.ctx.services.get("audio").latest()
    snap.bands        # 8 floats, 0-1, low to high
    snap.level        # overall level 0-1
    snap.bpm          # 0 when unknown
    snap.beat_count   # increments on every beat
```

| Service | `latest()` returns |
|---|---|
| `audio` | `Snapshot`: bands, level, stereo levels, beat count, BPM, silent seconds |
| `media` | `NowPlaying`: title, artist, app, playing |

`latest()` never blocks. The service fills it in on its own thread, and you read whatever is newest.

To add a service, write a class with `start()` and `stop()` and register a factory for it in `App.__init__` in `src/launchpad_lights/app.py`. Services start only while a mode that needs them is active, so a service that polls an API costs nothing when nobody is using it.

## Text

`launchpad_lights.launchpad.font.Scroller` scrolls text across the grid. Text 8 columns wide or less is centred and doesn't move.

There are 2 fonts. `"small"` is 3x5 and capitals only, so lowercase comes out in capitals. `"large"` is 5x7 with upper and lower case. Use whichever the user picked in Settings > General, the same as the built-in modes do:

```python
from launchpad_lights.launchpad.font import Scroller

def __init__(self, ctx):
    super().__init__(ctx)
    self.scroller = Scroller(speed=10, font=ctx.config.section("app").get("text_size", "small"))  # speed in columns per second

def on_config_changed(self):
    self.scroller.set_font(self.ctx.config.section("app").get("text_size", "small"))

def render(self, frame, dt):
    self.scroller.set([("Hello ", (3, 3)), ("world", (0, 3))])  # call every frame; it only restarts when the text changes
    self.scroller.draw(frame, dt)
```

Small text sits on rows 1-5 and large text on rows 0-6. Pass `top=` to `draw` to move it. `set(..., keep_position=True)` carries on from the current scroll position when new text is the same width, which is how the clock updates without jumping back to the start.

## Testing

Unit test modes with a fake context, the same way `tests/test_modes.py` does. Build the mode, call `render` into a `Frame`, and check the LEDs. That needs no hardware, no audio and no Windows APIs.
