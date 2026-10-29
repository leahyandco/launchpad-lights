"""TOML config in %APPDATA%\\Launchpad Lights, merged over defaults."""
import copy
import logging
import os
import shutil
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


APP_NAME = "Launchpad Lights"
OLD_DIR_NAME = "lpctl"  # the app's name before 0.2


def app_dir() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME


def migrate_old_dir() -> None:
    """Copy the config across from the pre-rename folder the first time the new name runs."""
    new = app_dir()
    old = new.parent / OLD_DIR_NAME / "config.toml"
    if not (new / "config.toml").exists() and old.exists():
        new.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, new / "config.toml")
        log.info("Copied settings from %s", old)


def _coerce(data: dict) -> None:
    """Fix values of the wrong type (e.g. idle_timeout = "30s") by converting or falling back to the default."""
    for section, defaults in DEFAULTS.items():
        values = data.get(section)
        if not isinstance(values, dict):
            data[section] = copy.deepcopy(defaults)
            continue
        for key, default in defaults.items():
            if key not in values:
                continue
            value = values[key]
            try:
                if isinstance(default, bool):
                    ok = isinstance(value, bool)
                elif isinstance(default, (int, float)):
                    if isinstance(value, bool):
                        raise ValueError
                    value = type(default)(value)
                    ok = True
                elif isinstance(default, str):
                    ok = isinstance(value, str)
                elif isinstance(default, list):
                    ok = isinstance(value, list)
                else:
                    ok = True
            except (TypeError, ValueError):
                ok = False
            if ok:
                values[key] = value
            else:
                log.warning("Config [%s] %s = %r is the wrong type; using %r", section, key, values[key], default)
                values[key] = copy.deepcopy(default)


class Config:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        if not path:
            migrate_old_dir()
        path = Path(path) if path else app_dir() / "config.toml"
        data = copy.deepcopy(DEFAULTS)
        exists = path.exists()
        if exists:
            try:
                with open(path, "rb") as f:
                    loaded = tomllib.load(f)
            except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as e:
                # A hand-edit typo shouldn't stop the app starting. Keep the broken file for reference.
                bad = path.with_suffix(".bad.toml")
                log.error("Config %s is invalid (%s). Using defaults; the broken file is saved as %s", path, e, bad)
                try:
                    path.replace(bad)
                except OSError:
                    pass
                loaded, exists = {}, False
            for name, values in loaded.items():
                if isinstance(values, dict):
                    data.setdefault(name, {}).update(values)
            _coerce(data)
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
