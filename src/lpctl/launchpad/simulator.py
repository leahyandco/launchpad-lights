"""Terminal stand-in for LaunchpadDevice, for developing modes without hardware.

Keys: 1-8 top buttons, a-h side buttons, space toggles standby, Ctrl+C quits.
"""
import os
import queue
import sys
import time

from .events import ButtonEvent
from .frame import OFF, SIDE, TOP, Color, Frame

try:
    import msvcrt
except ImportError:  # not Windows
    msvcrt = None


def _cell(c: Color) -> str:
    if c == OFF:
        return "\x1b[38;2;60;60;60m·"
    r, g = c
    return f"\x1b[38;2;{85 * r};{70 * g};0m●"


class TerminalDevice:
    connected = True
    status = "Simulator"

    def __init__(self, max_fps: float = 30):
        self.events: queue.Queue = queue.Queue()
        self._min_interval = 1 / max_fps
        self._next_draw = 0.0
        self._last: list[Color] | None = None
        os.system("")  # enables ANSI escape handling in the Windows console
        sys.stdout.write("\x1b[2J\x1b[?25l")

    def maintain(self, now: float) -> None:
        while msvcrt and msvcrt.kbhit():
            ch = msvcrt.getwch().lower()
            if ch in "12345678":
                self._click("top", int(ch) - 1)
            elif ch in "abcdefgh":
                self._click("side", ord(ch) - ord("a"))
            elif ch == " ":
                self.events.put(ButtonEvent("standby", 0, True))

    def _click(self, kind, index) -> None:
        self.events.put(ButtonEvent(kind, index, True))
        self.events.put(ButtonEvent(kind, index, False))

    def show(self, frame: Frame) -> None:
        now = time.monotonic()
        if frame.leds == self._last or now < self._next_draw:
            return
        self._next_draw = now + self._min_interval
        self._last = list(frame.leds)
        leds = frame.leds
        lines = ["\x1b[H " + " ".join(_cell(c) for c in leds[TOP:TOP + 8]), ""]
        for y in range(8):
            row = " ".join(_cell(c) for c in leds[y * 8:y * 8 + 8])
            lines.append(f" {row}  {_cell(leds[SIDE + y])}")
        lines.append("\x1b[0m\n 1-8 top  a-h side  space standby  Ctrl+C quit")
        sys.stdout.write("\n".join(lines))
        sys.stdout.flush()

    def close(self) -> None:
        sys.stdout.write("\x1b[0m\x1b[?25h\n")
        sys.stdout.flush()
