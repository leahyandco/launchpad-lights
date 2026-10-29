import mido
import pytest

from lpctl.launchpad import protocol
from lpctl.launchpad.frame import SIDE, TOP, Frame


@pytest.mark.parametrize("color,expected", [
    ((0, 0), 12), ((1, 0), 13), ((3, 0), 15), ((3, 3), 63), ((2, 3), 62), ((0, 1), 28), ((0, 3), 60),
])
def test_velocity_table(color, expected):
    assert protocol.velocity(color) == expected


def test_velocity_clamps_and_flags():
    assert protocol.velocity((9, -1)) == 15
    assert protocol.velocity((3, 3), flags=0) == 51


def test_grid_side_top_mapping():
    assert protocol.led_message(0, (3, 0)).note == 0
    m = protocol.led_message(7 * 8 + 7, (3, 0))
    assert (m.type, m.note) == ("note_on", 16 * 7 + 7)
    assert [protocol.led_message(SIDE + i, (0, 0)).note for i in range(8)] == [8, 24, 40, 56, 72, 88, 104, 120]
    top = protocol.led_message(TOP + 3, (0, 3))
    assert (top.type, top.control, top.value) == ("control_change", 107, 60)


def test_rapid_update_order():
    f = Frame()
    f.leds[0], f.leds[1], f.leds[79] = (3, 0), (0, 3), (3, 3)
    msgs = protocol.rapid_messages(f)
    assert len(msgs) == 40
    assert all(m.channel == 2 and m.type == "note_on" for m in msgs)
    assert (msgs[0].note, msgs[0].velocity) == (15, 60)
    assert msgs[-1].velocity == 63


def test_decode_buttons():
    pad = protocol.decode(mido.Message("note_on", note=16 * 2 + 5, velocity=127))
    assert (pad.kind, pad.x, pad.y, pad.index, pad.pressed) == ("pad", 5, 2, 21, True)
    side = protocol.decode(mido.Message("note_on", note=40, velocity=0))
    assert (side.kind, side.index, side.pressed) == ("side", 2, False)
    top = protocol.decode(mido.Message("control_change", control=111, value=127))
    assert (top.kind, top.index, top.pressed) == ("top", 7, True)
    assert protocol.decode(mido.Message("control_change", control=0, value=0)) is None
    assert protocol.decode(mido.Message("note_on", note=9, velocity=127)) is None
