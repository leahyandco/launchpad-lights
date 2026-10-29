import copy
import time

from lpctl.config import DEFAULTS, Config
from lpctl.launchpad.events import ButtonEvent
from lpctl.launchpad.font import Scroller, ascii_fold, render_columns
from lpctl.launchpad.frame import Frame
from lpctl.modes import macro_pad, registry
from lpctl.modes.base import ModeContext
from lpctl.modes.clock import POMODORO, Clock
from lpctl.modes.now_playing import NowPlayingMode
from lpctl.services.media import NowPlaying
from lpctl.winutil import parse_combo


class FakeMedia:
    def __init__(self, info):
        self.info = info

    def latest(self):
        return self.info


class FakeServices:
    def __init__(self, **svcs):
        self.svcs = svcs

    def get(self, name):
        return self.svcs[name]


def ctx(tmp_path, **svcs):
    return ModeContext(Config(tmp_path / "c.toml", copy.deepcopy(DEFAULTS)), FakeServices(**svcs))


def lit(frame):
    return sum(c != (0, 0) for c in frame.leds[:64])


def test_font_and_fold():
    assert ascii_fold("Beyoncé – Halo") == "Beyonce - Halo"
    assert ascii_fold("Sigur Rós ♫") == "Sigur Ros ?"
    cols = render_columns([("Hi", (3, 0))])
    assert len(cols) == 12 and cols[0][0] == 0x7F  # H's first column is solid


def test_scroller_short_text_is_centred_and_static():
    s = Scroller()
    s.set([("1", (0, 3))])
    a, b = Frame(), Frame()
    s.draw(a, 0.5)
    s.draw(b, 0.5)
    assert a.leds == b.leds and lit(a) > 0


def test_now_playing_renders_title_and_idle(tmp_path):
    mode = NowPlayingMode(ctx(tmp_path, media=FakeMedia(NowPlaying("Song", "Artist", "x", True))))
    seen = 0
    for _ in range(30):
        f = Frame()
        mode.render(f, 0.1)
        seen = max(seen, lit(f))
    assert seen > 0
    mode.ctx.services.svcs["media"].info = NowPlaying()
    f = Frame()
    mode.render(f, 2.0)
    assert lit(f) > 0  # "Nothing playing" scrolls


def test_clock_views_render(tmp_path):
    mode = Clock(ctx(tmp_path))
    for view in range(3):
        mode.view = view
        f = Frame()
        mode.render(f, 0.05)
        assert lit(f) > 0


def test_pomodoro_phases(tmp_path):
    Clock(ctx(tmp_path))
    POMODORO.cfg = {"work_minutes": 1 / 60, "break_minutes": 1 / 60, "long_break_minutes": 1 / 60}
    POMODORO.reset()
    POMODORO.toggle()
    POMODORO._last -= 2  # pretend 2 s passed
    POMODORO.tick()
    assert POMODORO.phase == "break" and POMODORO.completed == 1
    POMODORO.reset()
    assert POMODORO.phase == "work" and not POMODORO.running


def test_macro_pad_pages_and_actions(tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(macro_pad, "run_action", lambda b: fired.append(b["label"]))
    monkeypatch.setattr(macro_pad, "mic_muted", lambda: True)
    mode = macro_pad.MacroPad(ctx(tmp_path))
    f = Frame()
    mode.render(f, 0.05)
    assert f.get(0, 0) == (0, 3)  # Prev, green
    assert f.get(0, 2) == (3, 0)  # mic muted -> red
    mode.on_event(ButtonEvent("pad", 1, True, 1, 0))
    time.sleep(0.05)
    assert fired == ["Play"]
    mode.on_event(ButtonEvent("side", 1, True))
    f = Frame()
    mode.render(f, 0.05)
    assert lit(f) == 0 and mode.page == 2


def test_parse_combo():
    assert parse_combo("ctrl+shift+m") == [0x11, 0x10, ord("M")]
    assert parse_combo("win+f13") == [0x5B, 0x7C]


def test_registry_lists_modes():
    names = registry.available()
    for n in ("visualiser", "now_playing", "macro_pad", "clock", "test_pattern"):
        assert n in names
    assert "base" not in names and "registry" not in names
