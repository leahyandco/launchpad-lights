import copy
import time

from launchpad_lights.config import DEFAULTS, Config
from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.font import Scroller, ascii_fold, render_columns
from launchpad_lights.launchpad.frame import Frame
from launchpad_lights.modes import macro_pad, registry
from launchpad_lights.modes.base import ModeContext
from launchpad_lights.modes.clock import POMODORO, Clock
from launchpad_lights.modes.now_playing import NowPlayingMode
from launchpad_lights.services.media import NowPlaying
from launchpad_lights.winutil import parse_combo


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
    assert ascii_fold("Beyonc\u00e9 \u2013 Halo") == "Beyonce - Halo"
    assert ascii_fold("Sigur R\u00f3s \u266b") == "Sigur Ros ?"
    cols = render_columns([("Hi", (3, 0))])
    assert len(cols) == 12 and cols[0][0] == 0x7F  # H's first column is solid


def test_small_font_fits_more():
    from launchpad_lights.launchpad.font import _SMALL_ROWS
    for ch, rows in _SMALL_ROWS.items():
        parts = rows.split("/")
        assert len(parts) == 5 and len({len(p) for p in parts}) == 1, ch
    text = [("Hello world", (3, 3))]
    assert len(render_columns(text, "small")) < len(render_columns(text, "large")) * 0.75
    assert render_columns([("a", (3, 3))], "small") == render_columns([("A", (3, 3))], "small")


def test_flip_clock_is_static_two_digits(tmp_path):
    mode = Clock(ctx(tmp_path))
    mode.view = 3
    a, b = Frame(), Frame()
    mode.render(a, 0.01)
    mode.render(b, 0.01)
    assert a.leds[:56] == b.leds[:56] and lit(a) > 6


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
    for view in range(4):
        mode.view = view
        f = Frame()
        mode.render(f, 0.05)
        assert lit(f) > 0


def test_pomodoro_phases(tmp_path):
    Clock(ctx(tmp_path))
    POMODORO.cfg = {"work_minutes": 1 / 60, "break_minutes": 1, "long_break_minutes": 1}
    POMODORO.reset()
    POMODORO.toggle()
    POMODORO._last -= 2  # pretend 2 s passed: the 1 s work phase is over, 1 s into the break
    POMODORO.tick()
    assert POMODORO.phase == "break" and POMODORO.completed == 1
    POMODORO.reset()
    assert POMODORO.phase == "work" and not POMODORO.running


def test_macro_pad_pages_and_actions(tmp_path, monkeypatch):
    fired = []
    monkeypatch.setattr(macro_pad, "run_action", lambda b: fired.append(b["label"]))
    monkeypatch.setattr(macro_pad, "mic_muted", lambda: True)
    mode = macro_pad.MacroPad(ctx(tmp_path))
    mode.on_enter()  # starts the mic poller
    time.sleep(0.1)
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
    mode.on_exit()


def test_macro_pad_ignores_buttons_off_the_grid(tmp_path):
    c = ctx(tmp_path)
    c.config.section("macro_pad")["buttons"] = [
        {"page": 1, "x": 0, "y": 10, "action": "media", "value": "next"},
        {"page": 1, "x": 8, "y": 0, "action": "media", "value": "next"},
        {"page": 9, "x": 0, "y": 0, "action": "media", "value": "next"},
        {"page": 1, "x": "a", "y": 0, "action": "media", "value": "next"},
        {"page": 1, "x": 2, "y": 3, "action": "media", "value": "next", "colour": "red"},
    ]
    mode = macro_pad.MacroPad(c)
    f = Frame()
    mode.render(f, 0.05)  # must not raise
    assert lit(f) == 1 and f.get(2, 3) == (3, 0)
    # Side button 1 shows the current page; nothing from the bad buttons leaked into side or top LEDs.
    assert f.leds[64] == (0, 3) and f.leds[65:] == [(0, 0)] * 15


def test_pomodoro_catches_up_and_banks_time(tmp_path):
    Clock(ctx(tmp_path))
    POMODORO.cfg = {"work_minutes": 1, "break_minutes": 1, "long_break_minutes": 1}
    POMODORO.reset()
    POMODORO.toggle()
    POMODORO._last -= 150  # 2.5 minutes with nothing ticking: work, break, then 30 s into work
    POMODORO.tick()
    assert POMODORO.phase == "work" and POMODORO.completed == 1
    assert 25 <= POMODORO.remaining <= 31
    POMODORO._last -= 10
    POMODORO.toggle()  # pausing banks the 10 s instead of losing it
    assert not POMODORO.running and 15 <= POMODORO.remaining <= 21


def test_pomodoro_picks_up_new_length_before_starting(tmp_path):
    Clock(ctx(tmp_path))
    POMODORO.cfg = {"work_minutes": 25}
    POMODORO.reset()
    POMODORO.cfg["work_minutes"] = 50
    POMODORO.refresh_lengths()
    assert POMODORO.total == 50 * 60


def test_pomodoro_notifies_on_phase_change(tmp_path):
    Clock(ctx(tmp_path))
    seen = []
    POMODORO.on_phase = seen.append
    try:
        POMODORO.cfg = {"work_minutes": 1, "break_minutes": 5}
        POMODORO.reset()
        POMODORO.toggle()
        POMODORO._last -= 61
        POMODORO.tick()
    finally:
        POMODORO.on_phase = None
    assert seen == ["Pomodoro: Break, 5 minutes."]


def test_scroller_enters_without_stalling():
    s = Scroller(speed=1.0)
    s.set([("Hello there", (3, 3))])
    starts = []
    for _ in range(3):
        f = Frame()
        s.draw(f, 0.5)
        starts.append(s.pos)
    assert starts == [-7.5, -7.0, -6.5]


def test_scroller_keep_position():
    s = Scroller(speed=10.0)
    s.set([("12:34", (3, 3))])
    s.draw(Frame(), 1.0)
    pos = s.pos
    s.set([("12:35", (3, 3))], keep_position=True)
    assert s.pos == pos
    s.set([("Something longer", (3, 3))], keep_position=True)
    assert s.pos == -8.0


def test_parse_combo():
    assert parse_combo("ctrl+shift+m") == [0x11, 0x10, ord("M")]
    assert parse_combo("win+f13") == [0x5B, 0x7C]


def test_registry_lists_modes():
    names = registry.available()
    for n in ("visualiser", "now_playing", "macro_pad", "clock", "test_pattern"):
        assert n in names
    assert "base" not in names and "registry" not in names
