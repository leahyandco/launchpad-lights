"""Mode manager and render loop."""
import logging
import queue
import time

from lpctl.config import Config
from lpctl.launchpad.events import ButtonEvent
from lpctl.launchpad.frame import Frame
from lpctl.modes import registry
from lpctl.modes.base import Mode, ModeContext
from lpctl.services import ServiceManager
from lpctl.services.audio import AudioService
from lpctl.services.media import MediaService

log = logging.getLogger(__name__)

STANDBY_BUTTON = 7
ACTIVE_TOP = (0, 3)
STANDBY_FPS = 10


class App:
    def __init__(self, config: Config, device, *, locked_mode: str | None = None, start_mode: str | None = None):
        """device: LaunchpadDevice or TerminalDevice (anything with events, maintain, show, close).
        locked_mode: run only this mode and hand it the top buttons too (used by --test)."""
        self.config = config
        self.device = device
        app_cfg = config.section("app")
        self.slots = (list(app_cfg.get("modes", [])) + [""] * 8)[:8]
        self.hold_seconds = float(app_cfg.get("standby_hold_seconds", 1.0))
        self.locked = locked_mode is not None
        self.services = ServiceManager({
            "audio": lambda: AudioService(config.section("visualiser")),
            "media": MediaService,
        })
        self.ctx = ModeContext(config, self.services)
        self.mode: Mode | None = None
        self.mode_name: str | None = None
        self.standby = False
        self._initial = locked_mode or start_mode or app_cfg.get("startup_mode", "visualiser")
        self._hold_start: float | None = None
        self._hold_fired = False
        self._running = False
        self.crashed = False
        self._commands: queue.Queue = queue.Queue()
        self._save_at: float | None = None
        self.last_frame = Frame()  # most recent rendered frame, for the GUI preview

    def stop(self) -> None:
        self._running = False

    # Thread-safe entry points for the GUI and tray. Everything runs on the render thread.

    def post(self, fn) -> None:
        self._commands.put(fn)

    def press(self, kind: str, index: int, x: int = -1, y: int = -1) -> None:
        """Simulate a short button press as if it came from the device."""
        self.device.events.put(ButtonEvent(kind, index, True, x, y))
        self.device.events.put(ButtonEvent(kind, index, False, x, y))

    def set_config(self, section: str, **values) -> None:
        def apply():
            self.config.section(section).update(values)
            self._save_at = time.perf_counter() + 1.0  # coalesce slider drags into one write
            if self.mode is not None:
                self.mode.on_config_changed()
        self.post(apply)

    def set_standby(self, on: bool) -> None:
        self.post(lambda: self.standby != on and self.toggle_standby())

    def set_slots(self, slots: list[str]) -> None:
        """Assign modes to the 8 top buttons ("" = unassigned)."""
        slots = (list(slots) + [""] * 8)[:8]

        def apply():
            self.slots = slots
            self.config.section("app")["modes"] = slots
            self.config.save()
            log.info("Top buttons: %s", ", ".join(s or "-" for s in slots))
        self.post(apply)

    @property
    def status(self) -> str:
        return getattr(self.device, "status", "")

    def audio_device(self) -> str | None:
        try:
            return self.services.get("audio").device_name
        except KeyError:
            return None

    def audio_bpm(self) -> float:
        try:
            return self.services.get("audio").latest().bpm
        except KeyError:
            return 0.0

    # Mode lifecycle

    def _enter(self, name: str) -> None:
        cls = registry.get(name)
        for s in cls.services:
            self.services.acquire(s)
        self.mode, self.mode_name = cls(self.ctx), name
        self.mode.on_enter()

    def _exit(self) -> None:
        if self.mode is None:
            return
        try:
            self.mode.on_exit()
        finally:
            for s in type(self.mode).services:
                self.services.release(s)
            self.mode = None

    def switch(self, name: str) -> None:
        if name == self.mode_name and self.mode is not None:
            return
        try:
            registry.get(name)
        except KeyError as e:
            log.error("%s", e)
            return
        self._exit()
        self.standby = False
        self._enter(name)
        log.info("Mode: %s", name)
        if not self.locked:
            self.config.section("app")["startup_mode"] = name
            self.config.save()

    def toggle_standby(self) -> None:
        self.standby = not self.standby
        log.info("Standby %s", "on" if self.standby else "off")
        if self.standby:
            self._exit()  # releases services, e.g. the audio stream
        elif self.mode_name:
            self._enter(self.mode_name)

    # Input

    def _handle(self, ev: ButtonEvent, now: float) -> None:
        if ev.kind == "standby":
            self.toggle_standby()
        elif self.locked:
            self.mode.on_event(ev)
        elif ev.kind == "top":
            if ev.index == STANDBY_BUTTON:
                # Short press selects mode 8, a long hold toggles standby.
                if ev.pressed:
                    self._hold_start, self._hold_fired = now, False
                elif self._hold_start is not None:
                    if not self._hold_fired:
                        self._select_slot(ev.index)
                    self._hold_start = None
            elif ev.pressed:
                self._select_slot(ev.index)
        elif self.mode is not None and not self.standby:
            self.mode.on_event(ev)

    def _select_slot(self, i: int) -> None:
        if self.slots[i]:
            self.switch(self.slots[i])
        elif self.standby:
            self.toggle_standby()

    def _poll(self, now: float) -> None:
        while True:
            try:
                fn = self._commands.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception:
                log.exception("Command from GUI failed")
        while True:
            try:
                ev = self.device.events.get_nowait()
            except queue.Empty:
                break
            self._handle(ev, now)
        if self._save_at is not None and now >= self._save_at:
            self._save_at = None
            self.config.save()
        if self._hold_start is not None and not self._hold_fired and now - self._hold_start >= self.hold_seconds:
            self._hold_fired = True
            self.toggle_standby()

    # Render loop

    def _start_mode(self) -> None:
        candidates = [self._initial] + [s for s in self.slots if s]
        for name in candidates:
            try:
                self._enter(name)
                log.info("Mode: %s", name)
                return
            except KeyError as e:
                log.error("%s", e)
        raise SystemExit("No usable mode configured")

    def render_frame(self, dt: float) -> Frame:
        frame = Frame()
        if self.standby or self.mode is None:
            return frame
        self.mode.render(frame, dt)
        if not self.locked:
            for i in range(8):
                frame.set_top(i, ACTIVE_TOP if self.slots[i] == self.mode_name else (0, 0))
        return frame

    def run(self) -> None:
        self._running = True
        self._start_mode()
        last = time.perf_counter()
        try:
            while self._running:
                now = time.perf_counter()
                self.device.maintain(now)
                self._poll(now)
                dt, last = now - last, now
                self.last_frame = self.render_frame(dt)
                self.device.show(self.last_frame)
                fps = self.mode.fps if (self.mode and not self.standby) else STANDBY_FPS
                delay = 1 / fps - (time.perf_counter() - now)
                if delay > 0:
                    time.sleep(delay)
        except KeyboardInterrupt:
            pass
        except Exception:
            self.crashed = True
            log.exception("Render loop crashed")  # under pythonw / the exe there is no stderr to see it
            raise
        finally:
            log.info("Shutting down")
            if self._save_at is not None:
                self.config.save()
            self._exit()
            self.services.stop_all()
            self.device.close()
