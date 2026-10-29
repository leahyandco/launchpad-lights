"""Mode base class. Modes draw into a Frame and never touch MIDI."""
from dataclasses import dataclass
from typing import ClassVar

from lpctl.config import Config
from lpctl.launchpad.events import ButtonEvent
from lpctl.launchpad.frame import Frame
from lpctl.services import ServiceManager


@dataclass
class ModeContext:
    config: Config
    services: ServiceManager

    def save(self) -> None:
        self.config.save()


class Mode:
    name: ClassVar[str] = ""
    fps: float = 30.0  # target render rate; may be changed at runtime (e.g. when idle)
    services: ClassVar[tuple[str, ...]] = ()  # acquired by the app before on_enter, released after on_exit

    def __init__(self, ctx: ModeContext):
        self.ctx = ctx

    def on_enter(self) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def on_config_changed(self) -> None:
        """Settings were changed from the GUI or tray; re-read anything cached from config."""

    def on_event(self, event: ButtonEvent) -> None:
        """Pad and side-button events. Top buttons belong to the app unless the mode is locked."""

    def render(self, frame: Frame, dt: float) -> None:
        raise NotImplementedError
