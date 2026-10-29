"""Clock and Pomodoro timer.

Side buttons: 1 scrolling clock, 2 binary clock, 3 Pomodoro, 4 flip clock. In Pomodoro, side 6
or any pad starts/pauses and side 7 resets. The timer keeps running when you switch modes.
"""
import logging
import math
import time

from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.font import Scroller, blit, render_columns
from launchpad_lights.launchpad.frame import Frame

from .base import Mode
from .registry import register

log = logging.getLogger(__name__)

RED, GREEN, AMBER, YELLOW = (3, 0), (0, 3), (3, 3), (2, 3)
RED_DIM, GREEN_DIM, AMBER_DIM = (1, 0), (0, 1), (1, 1)
VIEWS = ["clock", "binary", "pomodoro", "flip"]
VIEW_LABELS = ["Scrolling clock", "Binary clock", "Pomodoro", "Flip clock (hours, then minutes)"]
FLIP_S = 2.0
START_BUTTON, RESET_BUTTON = 5, 6
DONE_FLASH_S = 4.0


class Pomodoro:
    """Work/break timer driven by time.monotonic(). Shared across mode instances."""

    def __init__(self):
        self.phase = "work"
        self.completed = 0  # work sessions finished
        self.running = False
        self.remaining = 0.0
        self.total = 0.0
        self._last = 0.0
        self.flash_until = 0.0
        self.cfg: dict = {}
        self.on_phase = None  # called with a short message when a phase ends, e.g. to notify from the tray

    def minutes(self, phase: str) -> float:
        key = {"work": "work_minutes", "break": "break_minutes", "long_break": "long_break_minutes"}[phase]
        try:
            value = float(self.cfg.get(key, {"work": 25, "break": 5, "long_break": 15}[phase]))
        except (TypeError, ValueError):
            value = {"work": 25, "break": 5, "long_break": 15}[phase]
        return max(value, 1 / 60)  # never zero, or tick() would spin through phases forever

    def reset(self) -> None:
        self.phase, self.completed, self.running = "work", 0, False
        self.total = self.remaining = self.minutes("work") * 60

    def refresh_lengths(self) -> None:
        """Pick up changed lengths if the current phase hasn't started counting down yet."""
        if not self.running and self.remaining == self.total:
            self.total = self.remaining = self.minutes(self.phase) * 60

    def toggle(self) -> None:
        if self.total == 0:
            self.reset()
        self.tick()  # bank the time elapsed so far before pausing or resuming
        self.running = not self.running
        self._last = time.monotonic()
        log.info("Pomodoro %s (%s)", "started" if self.running else "paused", self.phase)

    def tick(self) -> None:
        now = time.monotonic()
        if self.running:
            self.remaining -= now - self._last
            while self.remaining <= 0:  # catch up across phases if nothing ticked for a while
                overshoot = -self.remaining
                self._next_phase()
                self.remaining -= overshoot
        self._last = now

    def _next_phase(self) -> None:
        if self.phase == "work":
            self.completed += 1
            self.phase = "long_break" if self.completed % 4 == 0 else "break"
        else:
            self.phase = "work"
        self.total = self.remaining = self.minutes(self.phase) * 60
        self.flash_until = time.monotonic() + DONE_FLASH_S
        log.info("Pomodoro: %s for %.0f min", self.phase.replace("_", " "), self.total / 60)
        if self.on_phase:
            what = "Back to work" if self.phase == "work" else "Long break" if self.phase == "long_break" else "Break"
            try:
                self.on_phase(f"Pomodoro: {what}, {self.total / 60:.0f} minutes.")
            except Exception:
                log.exception("Pomodoro notification failed")

    def left(self) -> float:
        """Seconds remaining right now, without advancing state (safe from other threads)."""
        if self.running:
            return max(0.0, self.remaining - (time.monotonic() - self._last))
        return max(0.0, self.remaining)

    @property
    def fraction(self) -> float:
        return max(0.0, self.remaining / self.total) if self.total else 1.0


POMODORO = Pomodoro()


@register
class Clock(Mode):
    name = "clock"
    fps = 20
    side_labels = ("Scrolling clock", "Binary clock", "Pomodoro", "Flip clock", "", "Pomodoro start/pause",
                   "Pomodoro reset", "")

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.section("clock")
        POMODORO.cfg = self.cfg
        if POMODORO.total == 0:
            POMODORO.reset()
        self.view = self._configured_view()
        self.scroller = Scroller(speed=8.0, gap=4, font=self._text_size())
        self.t = 0.0

    def _configured_view(self) -> int:
        return min(max(int(self.cfg.get("view", 1)) - 1, 0), len(VIEWS) - 1)

    def _text_size(self) -> str:
        return self.ctx.config.section("app").get("text_size", "small")

    def on_config_changed(self) -> None:
        self.view = self._configured_view()
        self.scroller.set_font(self._text_size())

    def on_event(self, event: ButtonEvent) -> None:
        if not event.pressed:
            return
        if event.kind == "side" and event.index < len(VIEWS):
            self.view = event.index
            self.cfg["view"] = event.index + 1
            self.ctx.save()
        elif VIEWS[self.view] == "pomodoro":
            if event.kind == "pad" or (event.kind == "side" and event.index == START_BUTTON):
                POMODORO.toggle()
            elif event.kind == "side" and event.index == RESET_BUTTON:
                POMODORO.reset()

    def render(self, frame: Frame, dt: float) -> None:
        self.t += dt
        getattr(self, f"_{VIEWS[self.view]}")(frame, dt)
        frame.set_side(self.view, GREEN)
        if VIEWS[self.view] == "pomodoro":
            frame.set_side(START_BUTTON, GREEN if POMODORO.running else AMBER)
            frame.set_side(RESET_BUTTON, RED_DIM)

    def _clock(self, frame, dt):
        now = time.localtime()
        h = now.tm_hour if self.cfg.get("24h", True) else (now.tm_hour % 12 or 12)
        # keep_position: when the minute ticks over, carry on scrolling instead of restarting.
        self.scroller.set([(f"{h:02d}", AMBER), (":", RED), (f"{now.tm_min:02d}", GREEN)], keep_position=True)
        self.scroller.draw(frame, dt)
        # Seconds as a dot travelling along the bottom row.
        frame.set(now.tm_sec * 8 // 60, 7, RED_DIM)

    def _flip(self, frame, dt):
        # Hours in amber, then minutes in green, two still 3x5 digits each. No scrolling.
        now = time.localtime()
        hours = int(self.t / FLIP_S) % 2 == 0
        h = now.tm_hour if self.cfg.get("24h", True) else (now.tm_hour % 12 or 12)
        value, colour = (h, AMBER) if hours else (now.tm_min, GREEN)
        cols = render_columns([(f"{value:02d}", colour)], "small")[:-1]
        blit(frame, cols, (8 - len(cols)) // 2, 1, 5)
        for x in range(0, 4) if hours else range(4, 8):  # bottom row says which half you're looking at
            frame.set(x, 7, AMBER_DIM if hours else GREEN_DIM)

    def _binary(self, frame, dt):
        now = time.localtime()
        digits = [now.tm_hour // 10, now.tm_hour % 10, now.tm_min // 10, now.tm_min % 10,
                  now.tm_sec // 10, now.tm_sec % 10]
        colours = [RED, RED, AMBER, AMBER, GREEN, GREEN]
        dims = [RED_DIM, RED_DIM, AMBER_DIM, AMBER_DIM, GREEN_DIM, GREEN_DIM]
        for i, d in enumerate(digits):
            for bit in range(4):  # each bit is two pads tall, least significant at the bottom
                colour = colours[i] if d >> bit & 1 else dims[i]
                frame.set(i + 1, 7 - 2 * bit, colour)
                frame.set(i + 1, 6 - 2 * bit, colour)

    def _pomodoro(self, frame, dt):
        p = POMODORO
        if time.monotonic() < p.flash_until:
            if int(self.t * 4) % 2 == 0:
                frame.fill(GREEN if p.phase != "work" else RED)
            return
        colour = RED if p.phase == "work" else GREEN
        lit = math.ceil(p.fraction * 64)
        if not p.running and int(self.t * 2) % 2:
            colour = AMBER_DIM if p.phase == "work" else GREEN_DIM  # blink while paused
        for i in range(64):
            if i >= 64 - lit:  # drains from the top-left
                frame.set(i % 8, i // 8, colour)
        # Completed sessions in this cycle as amber dots on the top row's right side.
        for k in range(p.completed % 4):
            frame.set(7 - k, 0, AMBER)
