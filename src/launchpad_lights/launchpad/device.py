"""Port discovery, reconnect, frame flushing and input decoding."""
import logging
import queue
import time

import mido

from . import protocol
from .frame import N_LEDS, Frame

log = logging.getLogger(__name__)

RAPID_THRESHOLD = N_LEDS // 2  # above this many changed LEDs, a rapid update is fewer messages
FULL_REFRESH_S = 5.0  # resend everything this often, so LEDs another app overwrote heal themselves


def find_port(names: list[str], substring: str) -> str | None:
    s = substring.lower()
    return next((n for n in names if s in n.lower()), None)


class LaunchpadDevice:
    def __init__(self, port_name: str = "Launchpad Mini", rapid_update: bool = True, retry_seconds: float = 2.0):
        self.port_name = port_name
        self.rapid_update = rapid_update
        self.retry_seconds = retry_seconds
        self.events: queue.Queue = queue.Queue()
        self._out = None
        self._in = None
        self._out_name: str | None = None
        self._last: Frame | None = None
        self._next_check = 0.0
        self._next_full = 0.0
        self._problem: str | None = None

    @property
    def connected(self) -> bool:
        return self._out is not None

    @property
    def status(self) -> str:
        if self.connected:
            return f"Connected: {self._out_name}"
        return self._problem or "Connecting..."

    def maintain(self, now: float) -> None:
        """Called every loop iteration; checks the port every retry_seconds."""
        if now < self._next_check:
            return
        self._next_check = now + self.retry_seconds
        try:
            if self.connected:
                if self._out_name not in mido.get_output_names():
                    log.warning("Launchpad disconnected (%s)", self._out_name)
                    self._close_ports()
            else:
                self._try_open()
        except Exception as e:  # a MIDI backend failure must not take the render loop down
            self._report(f"MIDI error: {e}.")

    def _report(self, problem: str) -> None:
        # Log each distinct problem once rather than every retry.
        if problem != self._problem:
            log.warning("%s Retrying every %.0fs.", problem, self.retry_seconds)
            self._problem = problem

    def _try_open(self) -> None:
        out_name = find_port(mido.get_output_names(), self.port_name)
        if not out_name:
            self._report(f"No MIDI output matching {self.port_name!r}. Is the Launchpad plugged in?")
            return
        in_name = find_port(mido.get_input_names(), self.port_name)
        try:
            out = mido.open_output(out_name)
        except Exception as e:
            self._report(
                f"Found {out_name!r} but could not open it ({e}). It is probably held by another MIDI app "
                "(Ableton Live, Novation Components, a DAW). Close it."
            )
            return
        inp = None
        if in_name:
            try:
                inp = mido.open_input(in_name, callback=self._on_message)
            except Exception as e:
                log.warning("Opened output but not input %r (%s); buttons will not work", in_name, e)
        self._out, self._in, self._out_name = out, inp, out_name
        self._problem = None
        self._last = None
        self._out.send(protocol.RESET)
        log.info("Launchpad connected: out=%r in=%r", out_name, in_name)

    def _on_message(self, msg: mido.Message) -> None:
        ev = protocol.decode(msg)
        if ev is not None:
            self.events.put(ev)

    def show(self, frame: Frame) -> None:
        if not self.connected:
            return
        now = time.monotonic()
        if now >= self._next_full:
            self._next_full = now + FULL_REFRESH_S
            self._last = None
        changed = frame.diff(self._last)
        if not changed:
            return
        try:
            if self.rapid_update and len(changed) > RAPID_THRESHOLD:
                # Any non-rapid message resets the rapid-update pointer to LED 0.
                self._out.send(protocol.led_message(0, frame.leds[0]))
                for msg in protocol.rapid_messages(frame):
                    self._out.send(msg)
            else:
                for i in changed:
                    self._out.send(protocol.led_message(i, frame.leds[i]))
            self._last = frame.copy()
        except Exception as e:
            log.warning("Send failed (%s); treating Launchpad as disconnected", e)
            self._close_ports()

    def _close_ports(self) -> None:
        for port in (self._in, self._out):
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
        self._in = self._out = self._out_name = None
        self._last = None

    def close(self) -> None:
        if self._out is not None:
            try:
                self._out.send(protocol.RESET)
            except Exception:
                pass
        self._close_ports()
