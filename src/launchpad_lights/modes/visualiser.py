"""Audio visualiser.

Side buttons 1-6 pick a view directly, side 7 cycles through the remaining views, side 8 cycles
auto-gain speed. Every view is also selectable from the tray menu and the settings window.
"""
import logging
import math
import random
from collections import deque

from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.frame import OFF, Frame
from launchpad_lights.services.analysis import SENSITIVITY

from .base import Mode
from .registry import register

log = logging.getLogger(__name__)

GREEN, YELLOW, AMBER, RED = (0, 3), (2, 3), (3, 3), (3, 0)
DIM_GREEN, DIM_RED = (0, 1), (1, 0)
HEAT = [OFF, (0, 1), (0, 2), (0, 3), (2, 3), (3, 3), (3, 2), (3, 1), (3, 0)]
FIRE = [OFF, (1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (3, 3), (2, 3)]
PLASMA = [(1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (3, 3), (2, 3), (1, 3), (0, 3), (0, 2)]
MIRROR = [GREEN, GREEN, YELLOW, RED]

VIEWS = [
    ("spectrum", "Spectrum bars"),
    ("mirrored", "Mirrored"),
    ("spectrogram", "Spectrogram"),
    ("vu", "VU meter"),
    ("beat", "Beat pulse"),
    ("fire", "Fire"),
    ("radial", "Radial"),
    ("fountain", "Fountain"),
    ("sparkle", "Sparkle"),
    ("plasma", "Plasma"),
    ("centre", "Centre spectrum"),
    ("horizontal", "Horizontal bars"),
    ("dots", "Bouncing dots"),
]
SUB_MODES = [key for key, _ in VIEWS]
SUB_MODE_LABELS = [label for _, label in VIEWS]
DIRECT_BUTTONS = 6  # side buttons 1-6 select views 1-6
MORE_BUTTON = 6  # side button 7 cycles views 7+
SENSITIVITY_BUTTON = 7
SENSITIVITY_COLOURS = {"low": GREEN, "medium": AMBER, "high": RED}
SPECTROGRAM_HZ = 16
FIRE_HZ = 25
PEAK_HOLD_S = 0.4
PEAK_FALL_ROWS_S = 10.0
IDLE_FPS = 15
GRAVITY = 30.0  # rows/s^2 for the fountain


def bar_colour(row: int) -> tuple[int, int]:
    """Colour for the row-th lit pad counted from the bottom."""
    return GREEN if row < 4 else YELLOW if row < 6 else RED


def scaled(colour: tuple[int, int], s: float) -> tuple[int, int]:
    return round(colour[0] * s), round(colour[1] * s)


class PeakHold:
    def __init__(self, n: int):
        self.peak = [0.0] * n
        self.hold = [0.0] * n

    def update(self, i: int, height: float, dt: float) -> int:
        if height >= self.peak[i]:
            self.peak[i], self.hold[i] = height, PEAK_HOLD_S
        elif self.hold[i] > 0:
            self.hold[i] -= dt
        else:
            self.peak[i] = max(0.0, self.peak[i] - PEAK_FALL_ROWS_S * dt)
        return round(self.peak[i])


def draw_bar(frame: Frame, x: int, rows: int, peak: int = 0) -> None:
    for i in range(rows):
        frame.set(x, 7 - i, bar_colour(i))
    if peak > rows:
        frame.set(x, 8 - peak, AMBER)


@register
class Visualiser(Mode):
    name = "visualiser"
    services = ("audio",)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.section("visualiser")
        self.active_fps = float(self.cfg.get("fps", 40))
        self.fps = self.active_fps
        self.sub = self._configured_sub()
        self.peaks = PeakHold(8)
        self.vu_peaks = PeakHold(2)
        self.history: deque[tuple[float, ...]] = deque(maxlen=8)
        self.scroll = 0.0
        self.rings: list[float] = []
        self.flash = 0.0
        self.last_beat: int | None = None
        self.t = 0.0
        self.phase = 0.0
        self.heat = [[0.0] * 8 for _ in range(8)]
        self.fire_step = 0.0
        self.particles: list[list[float]] = []  # x, y, vy
        self.sparks: dict[tuple[int, int], list] = {}  # (x, y) -> [colour, life]
        self.cycle_beats = 0
        self.cycle_time = 0.0

    def _configured_sub(self) -> int:
        return min(max(int(self.cfg.get("sub_mode", 1)) - 1, 0), len(SUB_MODES) - 1)

    @property
    def audio(self):
        return self.ctx.services.get("audio")

    def on_enter(self) -> None:
        self.audio.configure(self.cfg)
        log.info("Visualiser view: %s", SUB_MODES[self.sub])

    def on_config_changed(self) -> None:
        self.sub = self._configured_sub()
        self.active_fps = float(self.cfg.get("fps", 40))
        self.audio.configure(self.cfg)

    def on_event(self, event: ButtonEvent) -> None:
        if event.kind != "side" or not event.pressed:
            return
        if event.index < DIRECT_BUTTONS:
            self._set_view(event.index)
        elif event.index == MORE_BUTTON:
            nxt = self.sub + 1 if self.sub >= DIRECT_BUTTONS else DIRECT_BUTTONS
            self._set_view(nxt if nxt < len(SUB_MODES) else DIRECT_BUTTONS)
        elif event.index == SENSITIVITY_BUTTON:
            names = list(SENSITIVITY)
            current = self.cfg.get("sensitivity", "medium")
            nxt = names[(names.index(current) + 1) % len(names)] if current in names else "medium"
            self.cfg["sensitivity"] = nxt
            self.audio.configure(self.cfg)
            log.info("Visualiser sensitivity: %s", nxt)
            self.ctx.save()

    def _set_view(self, i: int) -> None:
        self.sub = i
        self.cfg["sub_mode"] = i + 1
        log.info("Visualiser view: %s", SUB_MODES[i])
        self.ctx.save()

    def render(self, frame: Frame, dt: float) -> None:
        self.t += dt
        snap = self.audio.latest()
        new_beat = self.last_beat is not None and snap.beat_count != self.last_beat
        self.last_beat = snap.beat_count
        if snap.silent_seconds >= float(self.cfg.get("idle_timeout", 30)):
            self.fps = IDLE_FPS
            if self.cfg.get("idle_style", "animation") == "animation":
                self._idle(frame)
            return  # side buttons dark too while idle
        self.fps = self.active_fps
        self._auto_cycle(snap, dt, new_beat)
        getattr(self, f"_{SUB_MODES[self.sub]}")(frame, snap, dt, new_beat)
        if self.sub < DIRECT_BUTTONS:
            frame.set_side(self.sub, GREEN)
        else:
            frame.set_side(MORE_BUTTON, AMBER)
        frame.set_side(SENSITIVITY_BUTTON, SENSITIVITY_COLOURS.get(self.cfg.get("sensitivity"), AMBER))

    def _auto_cycle(self, snap, dt, beat) -> None:
        """Jump to a random other view every N beats, or every N seconds when there's no clear beat."""
        if not self.cfg.get("auto_cycle", False):
            return
        self.cycle_time += dt
        self.cycle_beats += beat
        if snap.bpm:
            due = self.cycle_beats >= int(self.cfg.get("cycle_beats", 32))
        else:
            due = self.cycle_time >= float(self.cfg.get("cycle_seconds", 20))
        if due and len(SUB_MODES) > 1:
            self.cycle_beats, self.cycle_time = 0, 0.0
            # Only switch on a beat when there is one, so the change lands on the music.
            self.sub = random.choice([i for i in range(len(SUB_MODES)) if i != self.sub])
            self.cfg["sub_mode"] = self.sub + 1  # shown in the GUI; written with the next save

    # Views. Each takes (frame, snapshot, dt, new_beat).

    def _spectrum(self, frame, snap, dt, beat):
        for x, level in enumerate(snap.bands):
            h = level * 8
            draw_bar(frame, x, round(h), self.peaks.update(x, h, dt))

    def _mirrored(self, frame, snap, dt, beat):
        for x, level in enumerate(snap.bands):
            for i in range(round(level * 4)):
                frame.set(x, 3 - i, MIRROR[i])
                frame.set(x, 4 + i, MIRROR[i])

    def _spectrogram(self, frame, snap, dt, beat):
        self.scroll += dt
        if not self.history:
            self.history.append(snap.bands)
        while self.scroll >= 1 / SPECTROGRAM_HZ:
            self.scroll -= 1 / SPECTROGRAM_HZ
            self.history.append(snap.bands)
        for k, bands in enumerate(reversed(self.history)):
            for b, level in enumerate(bands):
                frame.set(7 - k, 7 - b, HEAT[round(level * (len(HEAT) - 1))])

    def _vu(self, frame, snap, dt, beat):
        left, right = (snap.level_l, snap.level_r) if snap.stereo else (snap.level, snap.level)
        for side, level in enumerate((left, right)):
            h = level * 8
            peak = self.vu_peaks.update(side, h, dt)
            for x in range(side * 4, side * 4 + 4):
                draw_bar(frame, x, round(h), peak)

    def _beat(self, frame, snap, dt, beat):
        if beat:
            self.flash = 1.0
            self.rings.append(0.0)
        self.flash = max(0.0, self.flash - dt / 0.15)
        self.rings = [r + dt * 14 for r in self.rings if r < 6]
        level = math.ceil(self.flash * 3)
        if level:
            frame.fill((level, level))
        for y in range(8):
            for x in range(8):
                d = math.hypot(x - 3.5, y - 3.5)
                for r in self.rings:
                    if abs(d - r) < 0.7:
                        frame.set(x, y, RED if r < 2 else AMBER if r < 4 else GREEN)

    def _fire(self, frame, snap, dt, beat):
        # Classic fire: seed the bottom row from the bands, let heat rise and cool.
        self.fire_step += dt
        while self.fire_step >= 1 / FIRE_HZ:
            self.fire_step -= 1 / FIRE_HZ
            h = self.heat
            for x in range(8):
                h[7][x] = snap.bands[x] * random.uniform(0.75, 1.0) + (0.4 if beat else 0.0)
            for y in range(7):
                for x in range(8):
                    below = h[y + 1]
                    avg = (below[max(x - 1, 0)] + below[x] * 2 + below[min(x + 1, 7)]) / 4
                    h[y][x] = max(0.0, avg * random.uniform(0.80, 0.97) - 0.02)
        for y in range(8):
            for x in range(8):
                frame.set(x, y, FIRE[min(len(FIRE) - 1, round(self.heat[y][x] * (len(FIRE) - 1)))])

    def _radial(self, frame, snap, dt, beat):
        # Bass in the middle, treble at the corners.
        for y in range(8):
            for x in range(8):
                d = math.hypot(x - 3.5, y - 3.5)  # 0.7 .. 4.95
                band = min(7, int((d - 0.7) / 4.3 * 8))
                frame.set(x, y, HEAT[round(snap.bands[band] * (len(HEAT) - 1))])

    def _fountain(self, frame, snap, dt, beat):
        for x, level in enumerate(snap.bands):
            if level > 0.35 and random.random() < level * level * 14 * dt:
                self.particles.append([x, 7.5, -(4 + level * 14)])
        if beat:
            for x in range(8):
                self.particles.append([x, 7.5, -random.uniform(10, 16)])
        alive = []
        for p in self.particles[-120:]:
            p[2] += GRAVITY * dt
            p[1] += p[2] * dt
            if p[1] < 8:
                alive.append(p)
                row = int(p[1])
                frame.set(int(p[0]), row, bar_colour(7 - row))
        self.particles = alive

    def _sparkle(self, frame, snap, dt, beat):
        colours = [RED, RED, RED, AMBER, AMBER, YELLOW, GREEN, GREEN]
        for b, level in enumerate(snap.bands):
            if random.random() < level * level * 30 * dt:
                self.sparks[(random.randrange(8), random.randrange(8))] = [colours[b], 1.0]
        if beat:
            for _ in range(12):
                self.sparks[(random.randrange(8), random.randrange(8))] = [AMBER, 1.0]
        for pos, spark in list(self.sparks.items()):
            spark[1] -= dt / 0.35
            if spark[1] <= 0:
                del self.sparks[pos]
            else:
                frame.set(*pos, scaled(spark[0], min(1.0, spark[1] + 0.34)))

    def _plasma(self, frame, snap, dt, beat):
        energy = max(snap.level, max(snap.bands))
        self.phase += dt * (0.5 + energy * 4 + (3 if beat else 0))
        p = self.phase
        brightness = min(1.0, 0.34 + energy)
        for y in range(8):
            for x in range(8):
                v = (math.sin(x * 0.5 + p) + math.sin(y * 0.4 - p * 0.7)
                     + math.sin((x + y) * 0.3 + p * 1.3) + math.sin(math.hypot(x - 3.5, y - 3.5) * 0.8 - p * 2))
                colour = PLASMA[min(len(PLASMA) - 1, int((v + 4) / 8 * len(PLASMA)))]
                frame.set(x, y, scaled(colour, brightness))

    def _centre(self, frame, snap, dt, beat):
        # Bass in the two middle columns, treble at the edges.
        for k in range(4):
            h = max(snap.bands[2 * k], snap.bands[2 * k + 1]) * 8
            for x in (3 - k, 4 + k):
                draw_bar(frame, x, round(h), self.peaks.update(x, h, dt))

    def _horizontal(self, frame, snap, dt, beat):
        for b, level in enumerate(snap.bands):
            length = round(level * 8)
            for i in range(length):
                frame.set(i, 7 - b, bar_colour(i))

    def _dots(self, frame, snap, dt, beat):
        for x, level in enumerate(snap.bands):
            h = level * 8
            peak = self.peaks.update(x, h, dt)
            for i in range(round(h)):
                frame.set(x, 7 - i, DIM_GREEN)
            if peak:
                frame.set(x, 8 - peak, bar_colour(peak - 1))

    def _idle(self, frame):
        for y in range(8):
            for x in range(8):
                v = math.sin(x * 0.6 + y * 0.4 + self.t * 1.2)
                if v > 0.7:
                    frame.set(x, y, DIM_GREEN)
                elif v < -0.85:
                    frame.set(x, y, DIM_RED)
