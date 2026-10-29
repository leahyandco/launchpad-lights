"""Scrolls the current track (title in amber, artist in green) from any app with media controls.

Side buttons: 1 previous, 2 play/pause, 3 next.
"""
import math

from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.font import Scroller
from launchpad_lights.launchpad.frame import Frame
from launchpad_lights.winutil import send_media

from .base import Mode
from .registry import register

AMBER, GREEN, RED_DIM, GREEN_DIM, AMBER_DIM = (3, 3), (0, 3), (1, 0), (0, 1), (1, 1)
SIDE_ACTIONS = {0: "prev", 1: "play_pause", 2: "next"}


@register
class NowPlayingMode(Mode):
    name = "now_playing"
    fps = 30
    side_labels = ("Previous track", "Play / pause", "Next track")
    services = ("media",)

    def __init__(self, ctx):
        super().__init__(ctx)
        self.scroller = Scroller(speed=float(ctx.config.section("now_playing").get("scroll_speed", 10)),
                                 font=ctx.config.section("app").get("text_size", "small"))
        self.t = 0.0

    def on_config_changed(self) -> None:
        self.scroller.speed = float(self.ctx.config.section("now_playing").get("scroll_speed", 10))
        self.scroller.set_font(self.ctx.config.section("app").get("text_size", "small"))

    def on_event(self, event: ButtonEvent) -> None:
        if event.kind == "side" and event.pressed and event.index in SIDE_ACTIONS:
            send_media(SIDE_ACTIONS[event.index])

    def render(self, frame: Frame, dt: float) -> None:
        self.t += dt
        info = self.ctx.services.get("media").latest()
        if info.title:
            segments = [(info.title, AMBER)]
            if info.artist:
                segments += [("  ", AMBER), (info.artist, GREEN)]
            self.scroller.set(segments)
        else:
            self.scroller.set([("Nothing playing", RED_DIM)])
        self.scroller.draw(frame, dt if info.playing or not info.title else dt * 0.4)
        # Bottom row: a slow green pulse while playing, dim amber while paused.
        for x in range(8):
            if info.playing:
                if (math.sin(self.t * 4 - x * 0.8) + 1) / 2 > 0.6:
                    frame.set(x, 7, GREEN_DIM)
            elif info.title:
                frame.set(x, 7, AMBER_DIM)
        frame.set_side(0, GREEN)
        frame.set_side(1, GREEN if info.playing else AMBER)
        frame.set_side(2, GREEN)
