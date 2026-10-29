"""Launchpad / Launchpad S protocol as used by the older Launchpad Mini (MIDI channel 1)."""
import mido

from .events import ButtonEvent
from .frame import N_LEDS, SIDE, TOP, Color, Frame

FLAGS_NORMAL = 12  # clear + copy: plain single-buffered write
TOP_CC = 104

RESET = mido.Message("control_change", control=0, value=0)


def velocity(color: Color, flags: int = FLAGS_NORMAL) -> int:
    r, g = (min(3, max(0, int(c))) for c in color)
    return 16 * g + r + flags


def all_on(level: int = 3) -> mido.Message:
    """All LEDs on at low (1) / medium (2) / full (3)."""
    return mido.Message("control_change", control=0, value=0x7C + level)


def pad_note(x: int, y: int) -> int:
    return 16 * y + x


def side_note(i: int) -> int:
    return 16 * i + 8


def led_message(index: int, color: Color) -> mido.Message:
    v = velocity(color)
    if index < SIDE:
        y, x = divmod(index, 8)
        return mido.Message("note_on", note=pad_note(x, y), velocity=v)
    if index < TOP:
        return mido.Message("note_on", note=side_note(index - SIDE), velocity=v)
    return mido.Message("control_change", control=TOP_CC + index - TOP, value=v)


def rapid_messages(frame: Frame) -> list[mido.Message]:
    """40 channel-3 note-ons carrying two LED velocities each, covering all 80 LEDs."""
    v = [velocity(c) for c in frame.leds]
    return [mido.Message("note_on", channel=2, note=v[i], velocity=v[i + 1]) for i in range(0, N_LEDS, 2)]


def decode(msg: mido.Message) -> ButtonEvent | None:
    if getattr(msg, "channel", None) != 0:
        return None
    if msg.type in ("note_on", "note_off"):
        pressed = msg.type == "note_on" and msg.velocity > 0
        row, col = divmod(msg.note, 16)
        if row > 7:
            return None
        if col == 8:
            return ButtonEvent("side", row, pressed)
        if col < 8:
            return ButtonEvent("pad", row * 8 + col, pressed, col, row)
    elif msg.type == "control_change" and TOP_CC <= msg.control < TOP_CC + 8:
        return ButtonEvent("top", msg.control - TOP_CC, msg.value > 0)
    return None
