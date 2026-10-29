"""Pixel fonts and a horizontal text scroller for the 8x8 grid.

large: classic 5x7, upper and lower case.
small: 3x5 capitals, variable width, so roughly two characters fit on the grid at once.
"""
import math
import unicodedata

from .frame import Color, Frame

# Classic 5x7 LCD font, ASCII 0x20-0x7E. Five column bytes per glyph, bit 0 = top row.
_LARGE = bytes.fromhex(
    "0000000000" "00005f0000" "0007000700" "147f147f14" "242a7f2a12" "2313086462" "3649552250" "0005030000"
    "001c224100" "0041221c00" "082a1c2a08" "08083e0808" "0050300000" "0808080808" "0060600000" "2010080402"
    "3e5149453e" "00427f4000" "4261514946" "2141454b31" "1814127f10" "2745454539" "3c4a494930" "0171090503"
    "3649494936" "064949291e" "0036360000" "0056360000" "0008142241" "1414141414" "4122140800" "0201510906"
    "324979413e" "7e1111117e" "7f49494936" "3e41414122" "7f4141221c" "7f49494941" "7f09090101" "3e41415132"
    "7f0808087f" "00417f4100" "2040413f01" "7f08142241" "7f40404040" "7f0204027f" "7f0408107f" "3e4141413e"
    "7f09090906" "3e4151215e" "7f09192946" "4649494931" "01017f0101" "3f4040403f" "1f2040201f" "7f2018207f"
    "6314081463" "0304780403" "6151494543" "00007f4141" "0204081020" "41417f0000" "0402010204" "4040404040"
    "0001020400" "2054545478" "7f48444438" "3844444420" "384444487f" "3854545418" "087e090102" "081454543c"
    "7f08040478" "00447d4000" "2040443d00" "007f102844" "00417f4000" "7c04180478" "7c08040478" "3844444438"
    "7c14141408" "081414187c" "7c08040408" "4854545420" "043f444020" "3c4040207c" "1c2040201c" "3c4030403c"
    "4428102844" "0c5050503c" "4464544c44" "0008364100" "00007f0000" "0041360800" "08082a1c08"
)

# 3x5 capitals, drawn row by row ("#" = lit). Narrow punctuation is 1-2 columns wide; M, N, W are wider.
_SMALL_ROWS = {
    " ": "../../../../..",
    "0": "###/#.#/#.#/#.#/###", "1": ".#./##./.#./.#./###", "2": "###/..#/###/#../###",
    "3": "###/..#/.##/..#/###", "4": "#.#/#.#/###/..#/..#", "5": "###/#../###/..#/###",
    "6": "###/#../###/#.#/###", "7": "###/..#/.#./.#./.#.", "8": "###/#.#/###/#.#/###",
    "9": "###/#.#/###/..#/###",
    "A": ".#./#.#/###/#.#/#.#", "B": "##./#.#/##./#.#/##.", "C": ".##/#../#../#../.##",
    "D": "##./#.#/#.#/#.#/##.", "E": "###/#../##./#../###", "F": "###/#../##./#../#..",
    "G": ".##/#../#.#/#.#/.##", "H": "#.#/#.#/###/#.#/#.#", "I": "###/.#./.#./.#./###",
    "J": "..#/..#/..#/#.#/.#.", "K": "#.#/#.#/##./#.#/#.#", "L": "#../#../#../#../###",
    "M": "#...#/##.##/#.#.#/#...#/#...#", "N": "#..#/##.#/#.##/#..#/#..#", "O": ".#./#.#/#.#/#.#/.#.",
    "P": "##./#.#/##./#../#..", "Q": ".#./#.#/#.#/##./.##", "R": "##./#.#/##./#.#/#.#",
    "S": ".##/#../.#./..#/##.", "T": "###/.#./.#./.#./.#.", "U": "#.#/#.#/#.#/#.#/###",
    "V": "#.#/#.#/#.#/#.#/.#.", "W": "#...#/#...#/#.#.#/##.##/#...#", "X": "#.#/#.#/.#./#.#/#.#",
    "Y": "#.#/#.#/.#./.#./.#.", "Z": "###/..#/.#./#../###",
    ".": "././././#", ",": "../../../.#/#.", ":": "./#/./#/.", ";": "../.#/../.#/#.",
    "!": "#/#/#/./#", "?": "##./..#/.#./.../.#.", "'": "#/#/././.", '"': "#.#/#.#/.../.../...",
    "-": ".../.../###/.../...", "+": ".../.#./###/.#./...", "/": "..#/..#/.#./#../#..",
    "(": ".#/#./#./#./.#", ")": "#./.#/.#/.#/#.", "[": "##/#./#./#./##", "]": "##/.#/.#/.#/##",
    "&": ".#./#.#/.#./#.#/.##", "_": ".../.../.../.../###", "=": ".../###/.../###/...",
    "#": "#.#/###/#.#/###/#.#", "%": "#.#/..#/.#./#../#.#", "*": "#.#/.#./#.#/.../...",
    "<": "..#/.#./#../.#./..#", ">": "#../.#./..#/.#./#..", "|": "#/#/#/#/#",
    "@": ".#./#.#/###/#../.##", "$": ".##/##./.#./.##/##.",
}


def _columns(rows: list[str]) -> bytes:
    return bytes(sum(1 << r for r, row in enumerate(rows) if row[c] == "#") for c in range(len(rows[0])))


_SMALL = {ch: _columns(src.split("/")) for ch, src in _SMALL_ROWS.items()}

FONT_HEIGHT = {"large": 7, "small": 5}
DEFAULT_FONT = "small"

_PUNCTUATION = str.maketrans({"\u2013": "-", "\u2014": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"',
                              "\u201d": '"', "\u2026": "...", "\u00a0": " ", "\u00b7": "-", "\u2022": "-"})


def ascii_fold(text: str) -> str:
    """Map text onto the font: strip accents, straighten quotes and dashes, '?' for the rest."""
    out = []
    for ch in unicodedata.normalize("NFKD", text.translate(_PUNCTUATION)):
        if " " <= ch <= "~":
            out.append(ch)
        elif not unicodedata.combining(ch):
            out.append("?")
    return "".join(out)


def glyph(ch: str, font: str = "large") -> bytes:
    if font == "small":
        return _SMALL.get(ch.upper(), _SMALL["?"])
    i = ord(ch) - 0x20
    if not 0 <= i < len(_LARGE) // 5:
        i = ord("?") - 0x20
    return _LARGE[i * 5:(i + 1) * 5]


def render_columns(segments: list[tuple[str, Color]], font: str = "large") -> list[tuple[int, Color]]:
    """Text segments -> list of (column bits, colour), one blank column after each character."""
    cols: list[tuple[int, Color]] = []
    for text, colour in segments:
        for ch in ascii_fold(text):
            cols.extend((b, colour) for b in glyph(ch, font))
            cols.append((0, colour))
    return cols


def blit(frame: Frame, cols: list[tuple[int, Color]], x: int, top: int, height: int) -> None:
    """Draw columns starting at grid column x. Anything off the grid is clipped."""
    for i, (bits, colour) in enumerate(cols):
        for row in range(height):
            if bits >> row & 1:
                frame.set(x + i, top + row, colour)


class Scroller:
    """Scrolls text right-to-left forever. Text that fits on the grid is centred and stays still."""

    def __init__(self, speed: float = 10.0, gap: int = 6, font: str = DEFAULT_FONT):
        self.speed = speed  # columns per second
        self.gap = gap
        self.font = font if font in FONT_HEIGHT else DEFAULT_FONT
        self.pos = 0.0
        self.key = None
        self.cols: list[tuple[int, Color]] = []

    @property
    def height(self) -> int:
        return FONT_HEIGHT[self.font]

    def set_font(self, font: str) -> None:
        font = font if font in FONT_HEIGHT else DEFAULT_FONT
        if font != self.font:
            self.font, self.key = font, None  # force a re-render on the next set()

    def set(self, segments: list[tuple[str, Color]], keep_position: bool = False) -> None:
        """keep_position: if the new text is the same width, carry on from the current scroll position."""
        key = tuple(segments)
        if key != self.key:
            old_len = len(self.cols)
            self.key = key
            self.cols = render_columns(segments, self.font)
            if self.cols and self.cols[-1][0] == 0:
                self.cols.pop()  # trailing gap only matters when wrapping
            if len(self.cols) > 8:
                self.cols += [(0, (0, 0))] * self.gap
                if not (keep_position and len(self.cols) == old_len):
                    self.pos = -8.0  # enter from the right edge
            else:
                self.pos = 0.0

    def draw(self, frame: Frame, dt: float, top: int | None = None) -> None:
        """Small text sits on rows 1-5, large on rows 0-6, unless top is given."""
        if top is None:
            top = 1 if self.font == "small" else 0
        if len(self.cols) <= 8:
            blit(frame, self.cols, (8 - len(self.cols)) // 2, top, self.height)
            return
        self.pos += self.speed * dt
        n = len(self.cols)
        start = math.floor(self.pos)  # int() would round -0.5 up to 0 and stall a column on entry
        visible = [self.cols[(start + x) % n] if start + x >= 0 else (0, (0, 0)) for x in range(8)]
        blit(frame, visible, 0, top, self.height)
        if self.pos >= n:
            self.pos -= n
