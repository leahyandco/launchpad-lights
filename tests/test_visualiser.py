import copy

import pytest

from lpctl.config import DEFAULTS, Config
from lpctl.launchpad.events import ButtonEvent
from lpctl.launchpad.frame import Frame
from lpctl.modes.base import ModeContext
from lpctl.modes.visualiser import DIRECT_BUTTONS, SUB_MODES, Visualiser
from lpctl.services.analysis import Snapshot


class FakeAudio:
    def __init__(self):
        self.beats = 0

    def configure(self, cfg):
        pass

    def latest(self):
        self.beats += 1
        return Snapshot(bands=(0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2), level=0.7, level_l=0.8, level_r=0.6,
                        stereo=True, beat_count=self.beats // 5)


class FakeServices:
    def __init__(self):
        self.audio = FakeAudio()

    def get(self, name):
        return self.audio


def make(tmp_path):
    ctx = ModeContext(Config(tmp_path / "c.toml", copy.deepcopy(DEFAULTS)), FakeServices())
    mode = Visualiser(ctx)
    mode.on_enter()
    return mode


@pytest.mark.parametrize("view", range(len(SUB_MODES)))
def test_every_view_renders_something(tmp_path, view):
    mode = make(tmp_path)
    mode.sub = view
    lit = 0
    for _ in range(40):
        frame = Frame()
        mode.render(frame, 0.025)
        assert all(0 <= r <= 3 and 0 <= g <= 3 for r, g in frame.leds)
        lit = max(lit, sum(c != (0, 0) for c in frame.leds[:64]))
    assert lit > 0, SUB_MODES[view]


def test_auto_cycle_changes_view_on_beats(tmp_path):
    mode = make(tmp_path)
    mode.cfg.update(auto_cycle=True, cycle_beats=4)
    mode.audio.latest = lambda: Snapshot(bands=(0.5,) * 8, bpm=120.0, beat_count=mode.t_beats)
    mode.t_beats = 0
    start = mode.sub
    for i in range(3):
        mode.t_beats += 1
        mode.render(Frame(), 0.5)
    assert mode.sub == start
    mode.t_beats += 1
    mode.render(Frame(), 0.5)
    mode.t_beats += 1
    mode.render(Frame(), 0.5)
    assert mode.sub != start


def test_side_buttons_select_and_cycle(tmp_path):
    mode = make(tmp_path)
    mode.on_event(ButtonEvent("side", 2, True))
    assert mode.sub == 2 and mode.cfg["sub_mode"] == 3
    seen = []
    for _ in range(len(SUB_MODES) - DIRECT_BUTTONS + 1):
        mode.on_event(ButtonEvent("side", 6, True))
        seen.append(mode.sub)
    assert seen == list(range(DIRECT_BUTTONS, len(SUB_MODES))) + [DIRECT_BUTTONS]
