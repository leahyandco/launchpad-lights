"""Mode base class. Modes draw into a Frame and never touch MIDI."""
from dataclasses import dataclass
from typing import ClassVar

from launchpad_lights.config import Config
from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.frame import Frame
from launchpad_lights.services import ServiceManager


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
    side_labels: ClassVar[tuple[str, ...]] = ()  # what side buttons 1-8 do, shown next to the GUI preview

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
