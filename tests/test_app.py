import queue

from lpctl.app import App
from lpctl.config import DEFAULTS, Config
from lpctl.launchpad.events import ButtonEvent
from lpctl.launchpad.frame import TOP
from lpctl.modes import registry
from lpctl.modes.base import Mode


@registry.register
class Dummy(Mode):
    name = "dummy"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.events = []

    def on_event(self, event):
        self.events.append(event)

    def render(self, frame, dt):
        frame.set(0, 0, (3, 0))


class FakeDevice:
    def __init__(self):
        self.events = queue.Queue()


def make_app(tmp_path):
    import copy
    data = copy.deepcopy(DEFAULTS)
    data["app"]["modes"] = ["dummy", "test_pattern", "", "", "", "", "", "dummy"]
    data["app"]["startup_mode"] = "dummy"
    app = App(Config(tmp_path / "c.toml", data), FakeDevice())
    app._start_mode()
    return app


def test_top_button_switches_mode_and_persists(tmp_path):
    app = make_app(tmp_path)
    app._handle(ButtonEvent("top", 1, True), 0.0)
    assert app.mode_name == "test_pattern"
    assert app.config.data["app"]["startup_mode"] == "test_pattern"
    frame = app.render_frame(0.01)
    assert frame.leds[TOP + 1] == (0, 3) and frame.leds[TOP] == (0, 0)


def test_unassigned_slot_ignored(tmp_path):
    app = make_app(tmp_path)
    app._handle(ButtonEvent("top", 3, True), 0.0)
    assert app.mode_name == "dummy"


def test_side_and_pad_events_go_to_mode(tmp_path):
    app = make_app(tmp_path)
    ev = ButtonEvent("side", 2, True)
    app._handle(ev, 0.0)
    assert app.mode.events == [ev]


def test_hold_top_right_toggles_standby(tmp_path):
    app = make_app(tmp_path)
    app.device.events.put(ButtonEvent("top", 7, True))
    app._poll(10.0)
    app._poll(11.1)
    assert app.standby
    assert app.render_frame(0.01).leds == [(0, 0)] * 80
    app.device.events.put(ButtonEvent("top", 7, False))
    app._poll(11.2)
    assert app.standby  # release after a long hold must not also select mode 8
    app.device.events.put(ButtonEvent("top", 7, True))
    app._poll(20.0)
    app._poll(21.1)
    assert not app.standby
    assert app.mode_name == "dummy"


def test_short_press_top_right_selects_slot_8(tmp_path):
    app = make_app(tmp_path)
    app._handle(ButtonEvent("top", 1, True), 0.0)
    app.device.events.put(ButtonEvent("top", 7, True))
    app.device.events.put(ButtonEvent("top", 7, False))
    app._poll(5.0)
    assert app.mode_name == "dummy" and not app.standby
