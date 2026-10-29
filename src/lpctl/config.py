"""TOML config in %APPDATA%\\lpctl, merged over defaults."""
import copy
import logging
import os
import tomllib
from pathlib import Path

import tomli_w

log = logging.getLogger(__name__)

OLD_DEFAULT_MODES = ["visualiser", "", "", "", "", "", "", "test_pattern"]

DEFAULT_MACROS = [
    {"page": 1, "x": 0, "y": 0, "action": "media", "value": "prev", "colour": "green", "label": "Prev"},
    {"page": 1, "x": 1, "y": 0, "action": "media", "value": "play_pause", "colour": "green", "label": "Play"},
    {"page": 1, "x": 2, "y": 0, "action": "media", "value": "next", "colour": "green", "label": "Next"},
    {"page": 1, "x": 3, "y": 0, "action": "media", "value": "stop", "colour": "red", "label": "Stop"},
    {"page": 1, "x": 5, "y": 0, "action": "media", "value": "vol_down", "colour": "amber", "label": "Vol -"},
    {"page": 1, "x": 6, "y": 0, "action": "media", "value": "vol_up", "colour": "amber", "label": "Vol +"},
    {"page": 1, "x": 7, "y": 0, "action": "media", "value": "mute", "colour": "red", "label": "Mute"},
    {"page": 1, "x": 0, "y": 2, "action": "mic_mute", "value": "", "colour": "green", "label": "Mic"},
    {"page": 1, "x": 0, "y": 4, "action": "key", "value": "win+d", "colour": "lime", "label": "Desktop"},
    {"page": 1, "x": 1, "y": 4, "action": "key", "value": "win+shift+s", "colour": "yellow", "label": "Snip"},
    {"page": 1, "x": 2, "y": 4, "action": "key", "value": "ctrl+shift+esc", "colour": "orange", "label": "TaskMgr"},
    {"page": 1, "x": 0, "y": 6, "action": "run", "value": "calc.exe", "colour": "amber_dim", "label": "Calc"},
    {"page": 1, "x": 1, "y": 6, "action": "run", "value": "notepad.exe", "colour": "amber_dim", "label": "Notes"},
    {"page": 1, "x": 2, "y": 6, "action": "url", "value": "https://www.youtube.com", "colour": "red_dim",
     "label": "YouTube"},
]

DEFAULTS = {
    "device": {"port_name": "Launchpad Mini", "rapid_update": True, "retry_seconds": 2.0},
    "app": {
        "startup_mode": "visualiser",
        "modes": ["visualiser", "now_playing", "macro_pad", "clock", "", "", "", "test_pattern"],
        "standby_hold_seconds": 1.0,
        "text_size": "small",
    },
    "now_playing": {"scroll_speed": 10.0},
    "macro_pad": {"page": 1, "buttons": DEFAULT_MACROS},
    "clock": {"view": 1, "24h": True, "work_minutes": 25.0, "break_minutes": 5.0, "long_break_minutes": 15.0},
    "visualiser": {
        "sub_mode": 1,
        "fps": 40,
        "fmin": 40.0,
        "fmax": 16000.0,
        "sensitivity": "medium",
        "auto_gain": True,
        "gain_db": 0.0,
        "range_db": 32.0,
        "noise_floor_db": -75.0,
        "source": "",
        "auto_cycle": False,
        "cycle_beats": 32,
        "cycle_seconds": 20.0,
        "idle_timeout": 30.0,
        "idle_style": "animation",
    },
}


def app_dir() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "lpctl"


class Config:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        path = Path(path) if path else app_dir() / "config.toml"
        data = copy.deepcopy(DEFAULTS)
        exists = path.exists()
        if exists:
            with open(path, "rb") as f:
                for name, values in tomllib.load(f).items():
                    if isinstance(values, dict):
                        data.setdefault(name, {}).update(values)
        if data["app"].get("modes") == OLD_DEFAULT_MODES:  # untouched first-release layout: pick up new modes
            data["app"]["modes"] = list(DEFAULTS["app"]["modes"])
        cfg = cls(path, data)
        if not exists:
            cfg.save()
        return cfg

    def section(self, name: str) -> dict:
        return self.data.setdefault(name, {})

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                tomli_w.dump(self.data, f)
            tmp.replace(self.path)
        except OSError as e:
            log.warning("Could not save config to %s: %s", self.path, e)
