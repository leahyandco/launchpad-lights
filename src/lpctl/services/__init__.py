"""Shared services modes can request. Started lazily, stopped when no active mode needs them."""
import logging
from typing import Callable, Protocol

log = logging.getLogger(__name__)


class Service(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...


class ServiceManager:
    def __init__(self, factories: dict[str, Callable[[], Service]]):
        self._factories = factories
        self._instances: dict[str, Service] = {}
        self._refs: dict[str, int] = {}

    def acquire(self, name: str) -> Service:
        svc = self._instances.get(name)
        if svc is None:
            svc = self._instances[name] = self._factories[name]()
        if self._refs.get(name, 0) == 0:
            svc.start()
        self._refs[name] = self._refs.get(name, 0) + 1
        return svc

    def release(self, name: str) -> None:
        n = self._refs.get(name, 0) - 1
        self._refs[name] = max(n, 0)
        if n == 0:
            self._instances[name].stop()

    def get(self, name: str) -> Service:
        return self._instances[name]

    def stop_all(self) -> None:
        for name, n in self._refs.items():
            if n > 0:
                self._instances[name].stop()
        self._refs.clear()
