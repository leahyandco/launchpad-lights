"""System tray icon: shows the active mode, quick switching, quit."""
import logging
import queue

import pystray
from PIL import Image, ImageDraw

from launchpad_lights import autostart
from launchpad_lights.modes.visualiser import SUB_MODE_LABELS
from launchpad_lights.services.analysis import SENSITIVITY

log = logging.getLogger(__name__)

TITLE = "Launchpad Lights"


def mode_label(name: str) -> str:
    return name.replace("_", " ").capitalize()


def make_icon(size: int = 64) -> Image.Image:
    """A little 4x4 spectrum on a dark rounded square."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=size // 6, fill=(28, 28, 28, 255))
    n, gap = 4, max(2, size // 16)
    cell = (size - gap * (n + 1)) / n
    heights = [2, 4, 3, 1]
    colours = [(60, 200, 60), (60, 200, 60), (240, 200, 0), (240, 60, 40)]  # bottom row first
    for col, h in enumerate(heights):
        for row in range(n):
            x0 = gap + col * (cell + gap)
            y0 = size - gap - (row + 1) * cell - row * gap
            d.rounded_rectangle((x0, y0, x0 + cell, y0 + cell), radius=max(1, size // 32),
                                fill=colours[row] if row < h else (62, 62, 62))
    return img


class Tray:
    def __init__(self, app, ui: queue.Queue):
        """ui receives "show" and "quit" for the Tk thread to act on."""
        self.app = app
        self.ui = ui
        self.viz = app.config.section("visualiser")
        self._state = None
        self._slots = list(app.slots)
        self.icon = pystray.Icon("launchpad-lights", make_icon(), TITLE, menu=self._menu())

    def start(self) -> None:
        self.icon.run_detached()

    def stop(self) -> None:
        self.icon.stop()

    def notify(self, message: str) -> None:
        try:
            self.icon.notify(message, TITLE)
        except Exception:
            pass

    def refresh(self) -> None:
        """Called periodically from the Tk thread; rebuilds the menu when state changed."""
        app = self.app
        if app.slots != self._slots:
            self._slots = list(app.slots)
            self.icon.menu = self._menu()
            self._state = None
        state = (app.mode_name, app.standby, self.viz.get("sub_mode"), self.viz.get("sensitivity"),
                 self.viz.get("auto_gain"), self.viz.get("auto_cycle"))
        if state == self._state:
            return
        self._state = state
        what = "standby" if app.standby else mode_label(app.mode_name or "")
        self.icon.title = f"{TITLE}: {what}"
        self.icon.update_menu()

    def _toggle_autostart(self) -> None:
        try:
            autostart.set_enabled(not autostart.is_enabled())
        except OSError as e:
            log.warning("Could not change start with Windows: %s", e)
        self.icon.update_menu()

    def _menu(self) -> pystray.Menu:
        app, viz, Item = self.app, self.viz, pystray.MenuItem

        def switch(name):
            return lambda: app.post(lambda: app.switch(name))

        def is_mode(name):
            return lambda item: app.mode_name == name and not app.standby

        def view(i):
            return lambda: app.set_config("visualiser", sub_mode=i)

        def is_view(i):
            return lambda item: viz.get("sub_mode") == i

        def speed(name):
            return lambda: app.set_config("visualiser", sensitivity=name)

        def is_speed(name):
            return lambda item: viz.get("sensitivity") == name

        modes = [Item(f"{i + 1}. {mode_label(n)}", switch(n), checked=is_mode(n), radio=True)
                 for i, n in enumerate(app.slots) if n]
        views = [Item(label, view(i + 1), checked=is_view(i + 1), radio=True) for i, label in enumerate(SUB_MODE_LABELS)]
        speeds = [Item(s.capitalize(), speed(s), checked=is_speed(s), radio=True) for s in SENSITIVITY]
        return pystray.Menu(
            Item("Open settings", lambda: self.ui.put("show"), default=True),
            pystray.Menu.SEPARATOR,
            *modes,
            pystray.Menu.SEPARATOR,
            Item("Visualiser view", pystray.Menu(*views)),
            Item("Auto-cycle views", lambda: app.set_config("visualiser", auto_cycle=not viz.get("auto_cycle", False)),
                 checked=lambda item: bool(viz.get("auto_cycle", False))),
            Item("Auto gain", lambda: app.set_config("visualiser", auto_gain=not viz.get("auto_gain", True)),
                 checked=lambda item: bool(viz.get("auto_gain", True))),
            Item("Auto-gain speed", pystray.Menu(*speeds)),
            Item("Standby", lambda: app.set_standby(not app.standby), checked=lambda item: app.standby),
            pystray.Menu.SEPARATOR,
            Item("Start with Windows", self._toggle_autostart, checked=lambda item: autostart.is_enabled()),
            Item("Quit", lambda: self.ui.put("quit")),
        )
