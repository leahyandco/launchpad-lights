"""Frame buffer: 64 grid pads, 8 side and 8 top LEDs, each a (red, green) pair 0-3.

LED indices follow the rapid-update order: 0-63 grid row by row, 64-71 side, 72-79 top.
"""
Color = tuple[int, int]

OFF: Color = (0, 0)
SIDE = 64
TOP = 72
N_LEDS = 80


class Frame:
    __slots__ = ("leds",)

    def __init__(self, leds: list[Color] | None = None):
        self.leds: list[Color] = list(leds) if leds is not None else [OFF] * N_LEDS

    def set(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < 8 and 0 <= y < 8:
            self.leds[y * 8 + x] = color

    def get(self, x: int, y: int) -> Color:
        return self.leds[y * 8 + x]

    def set_side(self, i: int, color: Color) -> None:
        self.leds[SIDE + i] = color

    def set_top(self, i: int, color: Color) -> None:
        self.leds[TOP + i] = color

    def fill(self, color: Color) -> None:
        self.leds[:SIDE] = [color] * SIDE

    def clear(self) -> None:
        self.leds[:] = [OFF] * N_LEDS

    def copy(self) -> "Frame":
        return Frame(self.leds)

    def diff(self, prev: "Frame | None") -> list[int]:
        """Indices of LEDs that differ from prev (all of them if prev is None)."""
        if prev is None:
            return list(range(N_LEDS))
        return [i for i, (a, b) in enumerate(zip(self.leds, prev.leds)) if a != b]
