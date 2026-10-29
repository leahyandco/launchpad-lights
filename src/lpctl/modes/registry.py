"""Mode registry. A config name like "visualiser" loads lpctl.modes.visualiser on first use,
so adding a mode means adding one module and one config entry."""
import importlib
import pkgutil

from .base import Mode

_MODES: dict[str, type[Mode]] = {}
_NOT_MODES = {"base", "registry"}


def register(cls: type[Mode]) -> type[Mode]:
    _MODES[cls.name] = cls
    return cls


def get(name: str) -> type[Mode]:
    if name not in _MODES:
        try:
            importlib.import_module(f"lpctl.modes.{name}")
        except ModuleNotFoundError:
            pass
    if name not in _MODES:
        raise KeyError(f"Unknown mode {name!r}")
    return _MODES[name]


def available() -> list[str]:
    """Names of all modes that can be assigned to a top button."""
    from lpctl import modes

    names = {m.name for m in pkgutil.iter_modules(modes.__path__) if m.name not in _NOT_MODES}
    return sorted(names | set(_MODES))
