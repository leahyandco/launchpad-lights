"""5x7 pixel font and a horizontal text scroller for the 8x8 grid."""
import unicodedata

from .frame import Color, Frame

# Classic 5x7 LCD font, ASCII 0x20-0x7E. Five column bytes per glyph, bit 0 = top row.
_GLYPHS = bytes.fromhex(
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
GLYPH_W = 5
GLYPH_H = 7


_PUNCTUATION = str.maketrans({"–": "-", "—": "-", "‘": "'", "’": "'", "“": '"',
                              "”": '"', "…": "...", " ": " ", "·": "-", "•": "-"})


def ascii_fold(text: str) -> str:
    """Map text onto the font: strip accents, straighten quotes and dashes, '?' for the rest."""
    out = []
    for ch in unicodedata.normalize("NFKD", text.translate(_PUNCTUATION)):
        if " " <= ch <= "~":
            out.append(ch)
        elif not unicodedata.combining(ch):
            out.append("?")
    return "".join(out)


def glyph(ch: str) -> bytes:
    i = ord(ch) - 0x20
    if not 0 <= i < len(_GLYPHS) // GLYPH_W:
        i = ord("?") - 0x20
    return _GLYPHS[i * GLYPH_W:(i + 1) * GLYPH_W]


def render_columns(segments: list[tuple[str, Color]]) -> list[tuple[int, Color]]:
    """Text segments -> list of (column bits, colour), one blank column between characters."""
    cols: list[tuple[int, Color]] = []
    for text, colour in segments:
        for ch in ascii_fold(text):
            cols.extend((b, colour) for b in glyph(ch))
            cols.append((0, colour))
    return cols


def draw_columns(frame: Frame, cols: list[tuple[int, Color]], offset: int, top: int = 0) -> None:
    """Draw 8 columns starting at cols[offset] (wrapping) with the glyph's top row at `top`."""
    if not cols:
        return
    for x in range(8):
        bits, colour = cols[(offset + x) % len(cols)]
        for row in range(GLYPH_H):
            if bits >> row & 1:
                frame.set(x, top + row, colour)


class Scroller:
    """Scrolls text right-to-left forever. Fits without scrolling when 8 columns or fewer."""

    def __init__(self, speed: float = 10.0, gap: int = 6):
        self.speed = speed  # columns per second
        self.gap = gap
        self.pos = 0.0
        self.key = None
        self.cols: list[tuple[int, Color]] = []

    def set(self, segments: list[tuple[str, Color]]) -> None:
        key = tuple(segments)
        if key != self.key:
            self.key = key
            self.cols = render_columns(segments)
            if len(self.cols) > 8:
                self.cols += [(0, (0, 0))] * self.gap
                self.pos = -8.0  # enter from the right edge
            else:
                self.pos = 0.0

    def draw(self, frame: Frame, dt: float, top: int = 0) -> None:
        if len(self.cols) <= 8:
            pad = (8 - len(self.cols)) // 2
            for x, (bits, colour) in enumerate(self.cols):
                for row in range(GLYPH_H):
                    if bits >> row & 1:
                        frame.set(x + pad, top + row, colour)
            return
        self.pos += self.speed * dt
        n = len(self.cols)
        start = int(self.pos)
        for x in range(8):
            i = start + x
            if i < 0:
                continue
            bits, colour = self.cols[i % n]
            for row in range(GLYPH_H):
                if bits >> row & 1:
                    frame.set(x, top + row, colour)
        if self.pos >= n:
            self.pos -= n
