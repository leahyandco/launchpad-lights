"""Hardware smoke test: walks every LED in red, green and amber, cycles all 16 colour levels
across the whole device, and echoes every button press. Held buttons light red."""
import logging
import sys

from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.frame import N_LEDS, SIDE, TOP, Frame

from .base import Mode
from .registry import register

log = logging.getLogger(__name__)

WALK_COLOURS = [(3, 0), (0, 3), (3, 3)]
WALK_STEP_S = 0.03
LEVEL_STEP_S = 0.5
LEVELS = [(r, g) for g in range(4) for r in range(4)]
WALK_S = N_LEDS * WALK_STEP_S * len(WALK_COLOURS)
CYCLE_S = WALK_S + LEVEL_STEP_S * len(LEVELS)


def led_index(event: ButtonEvent) -> int:
    return {"pad": 0, "side": SIDE, "top": TOP}[event.kind] + event.index


@register
class TestPattern(Mode):
    name = "test_pattern"
    fps = 40
    side_labels = ("Lights red while held",) * 8

    def __init__(self, ctx):
        super().__init__(ctx)
        self.t = 0.0
        self.held: set[int] = set()

    def on_event(self, event: ButtonEvent) -> None:
        if event.kind == "standby":
            return
        where = f"pad x={event.x} y={event.y}" if event.kind == "pad" else f"{event.kind} {event.index + 1}"
        msg = f"{where} {'pressed' if event.pressed else 'released'}"
        log.info(msg)
        if sys.stdout:
            print(msg, flush=True)
        (self.held.add if event.pressed else self.held.discard)(led_index(event))

    def render(self, frame: Frame, dt: float) -> None:
        self.t = (self.t + dt) % CYCLE_S
        if self.t < WALK_S:
            step = int(self.t / WALK_STEP_S)
            colour = WALK_COLOURS[step // N_LEDS]
            frame.leds[step % N_LEDS] = colour
        else:
            colour = LEVELS[int((self.t - WALK_S) / LEVEL_STEP_S)]
            frame.leds[:] = [colour] * N_LEDS
        for i in self.held:
            frame.leds[i] = (3, 0) if frame.leds[i] != (3, 0) else (0, 3)
