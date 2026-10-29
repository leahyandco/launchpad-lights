"""Typed button events decoded from the device."""
from dataclasses import dataclass
from typing import Literal

Kind = Literal["pad", "top", "side", "standby"]


@dataclass(frozen=True, slots=True)
class ButtonEvent:
    kind: Kind
    index: int  # pad: y*8+x, top: 0-7 left to right, side: 0-7 top to bottom
    pressed: bool
    x: int = -1
    y: int = -1
