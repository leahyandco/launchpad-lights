"""Macro pad: each pad runs a configurable action. Side buttons 1-8 switch between 8 pages.

Actions:
    media     value: play_pause / next / prev / stop / mute / vol_up / vol_down
    key       value: a key combo such as "ctrl+shift+m" or "win+d"
    run       value: a command line, e.g. "notepad.exe" or "C:\\Tools\\vpn.bat connect"
    url       value: a URL or file path to open with its default app
    mic_mute  toggles the default microphone; lit red when muted, green when live

Buttons live in config [[macro_pad.buttons]] with page (1-8), x, y, action, value, colour, label.
"""
import logging
import os
import subprocess
import threading
import time

from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.frame import Frame
from launchpad_lights.winutil import mic_muted, send_combo, send_media, toggle_mic

from .base import Mode
from .registry import register

log = logging.getLogger(__name__)

COLOURS = {
    "red": (3, 0), "orange": (3, 1), "light_orange": (3, 2), "amber": (3, 3), "yellow": (2, 3),
    "lime": (1, 3), "green": (0, 3), "red_dim": (1, 0), "amber_dim": (1, 1), "green_dim": (0, 1), "off": (0, 0),
}
ACTIONS = ["media", "key", "run", "url", "mic_mute"]
FLASH_S = 0.15
MIC_POLL_S = 0.5
PAGES = 8


def run_action(button: dict) -> None:
    """Perform a button's action. Called on a worker thread so the render loop never waits."""
    action, value = button.get("action", ""), str(button.get("value", ""))
    try:
        if action == "media":
            send_media(value)
        elif action == "key":
            send_combo(value)
        elif action == "run":
            subprocess.Popen(value)  # Windows takes the command line as-is, quotes and all
        elif action == "url":
            os.startfile(value)
        elif action == "mic_mute":
            toggle_mic()
        log.info("Macro %r: %s %s", button.get("label", ""), action, value)
    except Exception as e:
        log.warning("Macro %r failed: %s", button.get("label", ""), e)


@register
class MacroPad(Mode):
    name = "macro_pad"
    fps = 20

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cfg = ctx.config.section("macro_pad")
        self.page = min(max(int(self.cfg.get("page", 1)), 1), PAGES)
        self.flash: dict[int, float] = {}  # pad index -> time the flash ends
        self.mic: bool | None = None
        self._next_mic_poll = 0.0
        self._build()

    def _build(self) -> None:
        self.buttons: dict[tuple[int, int], dict] = {}
        for b in self.cfg.get("buttons", []):
            try:
                self.buttons[(int(b.get("page", 1)), int(b["y"]) * 8 + int(b["x"]))] = b
            except (KeyError, ValueError, TypeError):
                log.warning("Ignoring bad macro button %r", b)
        self.has_mic = any(b.get("action") == "mic_mute" for b in self.buttons.values())

    def on_config_changed(self) -> None:
        self._build()

    def on_event(self, event: ButtonEvent) -> None:
        if not event.pressed:
            return
        if event.kind == "side":
            self.page = event.index + 1
            self.cfg["page"] = self.page
            self.ctx.save()
        elif event.kind == "pad":
            button = self.buttons.get((self.page, event.index))
            if button:
                self.flash[event.index] = time.monotonic() + FLASH_S
                threading.Thread(target=run_action, args=(button,), daemon=True).start()
                if button.get("action") == "mic_mute":
                    self._next_mic_poll = 0.0

    def render(self, frame: Frame, dt: float) -> None:
        now = time.monotonic()
        if self.has_mic and now >= self._next_mic_poll:
            self.mic = mic_muted()
            self._next_mic_poll = now + MIC_POLL_S
        for (page, index), b in self.buttons.items():
            if page != self.page:
                continue
            colour = COLOURS.get(b.get("colour", "amber"), (3, 3))
            if b.get("action") == "mic_mute":
                colour = (1, 1) if self.mic is None else (3, 0) if self.mic else (0, 3)
            if self.flash.get(index, 0) > now:
                colour = (0, 3) if colour[0] >= colour[1] else (3, 0)
            frame.leds[index] = colour
        used = {page for page, _ in self.buttons}
        for i in range(PAGES):
            frame.set_side(i, (0, 3) if i + 1 == self.page else (0, 1) if i + 1 in used else (0, 0))
