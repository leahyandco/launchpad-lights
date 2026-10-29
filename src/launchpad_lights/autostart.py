"""Start with Windows via the per-user Run registry key (no admin rights needed)."""
import logging
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE = "Launchpad Lights"
OLD_VALUE = "lpctl"  # the app's name before 0.2; its command no longer works after the rename


def command() -> str:
    if getattr(sys, "frozen", False):  # packaged .exe
        return f'"{sys.executable}" --hidden'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{exe}" -m launchpad_lights --hidden'


def _has(value: str) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, value)
            return True
    except OSError:
        return False


def is_enabled() -> bool:
    return _has(VALUE)


def set_enabled(enabled: bool) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE, 0, winreg.REG_SZ, command())
            log.info("Start with Windows enabled: %s", command())
        else:
            try:
                winreg.DeleteValue(key, VALUE)
            except FileNotFoundError:
                pass
            log.info("Start with Windows disabled")


def _stored_program() -> Path | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE)
    except OSError:
        return None
    value = value.strip()
    if value.startswith('"'):
        return Path(value[1:].split('"', 1)[0])
    return Path(value.split(" ", 1)[0])


def repair() -> None:
    """Called at startup. Swaps a pre-rename "lpctl" entry for the new name, and rewrites an entry
    whose program no longer exists (folder moved, venv deleted, exe replaced) to point at this copy."""
    try:
        if _has(OLD_VALUE):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, OLD_VALUE)
            set_enabled(True)
        program = _stored_program()
        if program is not None and not program.exists():
            log.info("Start with Windows pointed at %s, which no longer exists. Fixing it.", program)
            set_enabled(True)
    except OSError as e:
        log.warning("Could not repair the start-with-Windows entry: %s", e)
