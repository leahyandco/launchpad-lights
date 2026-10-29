"""Audio capture, analysed on a background thread. Either the whole system (WASAPI loopback of
the default output) or a single application (WASAPI process loopback).

The renderer reads latest() each frame; it never blocks on audio. Loopback delivers no buffers
while nothing is playing, so a supervisor loop feeds silence to keep bars falling, and reopens the
capture after a few seconds of silence. That reopen is how we follow a change of default output
device (apps move playback and the old device goes quiet) and an app being restarted.
"""
import logging
import threading
import time

import numpy as np

from .analysis import GAIN_DEFAULTS, Analyzer, Snapshot

log = logging.getLogger(__name__)

BLOCK = 1024
APP_RATE = 48000
REOPEN_AFTER_SILENCE_S = 3.0
RETRY_S = 2.0


def default_loopback(pa, pyaudio) -> dict:
    wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    out = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if out.get("isLoopbackDevice"):
        return out
    for lb in pa.get_loopback_device_info_generator():
        if out["name"] in lb["name"]:
            return lb
    raise RuntimeError(f"No loopback device for default output {out['name']!r}")


class AudioService:
    def __init__(self, cfg: dict):
        self.fmin = float(cfg.get("fmin", 40.0))
        self.fmax = float(cfg.get("fmax", 16000.0))
        self.device_name: str | None = None
        self.source = ""  # "" = whole system, else an executable name like "Spotify.exe"
        self._snapshot = Snapshot()
        self._lock = threading.Lock()  # guards the analyzer; capture and supervisor both feed it
        self._analyzer: Analyzer | None = None
        self._settings: dict = {}
        self._restart = threading.Event()
        self.configure(cfg)
        self._last_feed = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="audio", daemon=True)
        self._thread.start()
        log.info("Audio service started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None
        self._snapshot = Snapshot()
        log.info("Audio service stopped")

    def latest(self) -> Snapshot:
        return self._snapshot  # reference swap is atomic, no lock needed

    def configure(self, cfg: dict) -> None:
        """Apply source, sensitivity and gain settings from a visualiser config section."""
        source = str(cfg.get("source", "") or "")
        if source != self.source:
            self.source = source
            self._restart.set()
        keys = ("sensitivity", *GAIN_DEFAULTS)
        self._settings = {k: cfg[k] for k in keys if k in cfg}
        with self._lock:
            if self._analyzer:
                self._analyzer.configure(**self._settings)

    def _feed(self, samples: np.ndarray, dt: float | None = None) -> None:
        with self._lock:
            snap = self._analyzer.process(samples, dt)
            self._last_feed = time.monotonic()
        self._snapshot = snap

    def _use_rate(self, rate: int) -> None:
        with self._lock:
            if self._analyzer is None or self._analyzer.rate != rate:
                self._analyzer = Analyzer(rate, BLOCK, fmin=self.fmin, fmax=self.fmax)
                self._analyzer.configure(**self._settings)

    def _opened(self, name: str, rate: int, channels: int) -> None:
        if name != self.device_name:
            log.info("Capturing %s (%d Hz, %d ch)", name, rate, channels)
            self.device_name = name

    def _run(self) -> None:
        import pyaudiowpatch as pyaudio

        last_error = None
        while not self._stop.is_set():
            self._restart.clear()
            try:
                if self.source:
                    self._app_session(self.source)
                else:
                    self._system_session(pyaudio)
                last_error = None
            except Exception as e:
                if str(e) != last_error:  # log each distinct error once, not every retry
                    log.warning("Audio capture error (retrying every %.0fs): %s", RETRY_S, e)
                    last_error = str(e)
                self.device_name = None  # so the next successful open is logged
                self._stop.wait(RETRY_S)

    def _supervise(self, rate: int, opened: float, poll=None, alive=lambda: True) -> None:
        """Loop until stop/restart/silence. poll() pulls captured audio for pull-style sources."""
        while not self._stop.wait(0.01 if poll else 0.05) and not self._restart.is_set():
            if poll:
                data = poll()
                if data is not None and len(data):
                    self._feed(data)
            now = time.monotonic()
            gap = now - self._last_feed
            if gap > 0.1:
                self._feed(np.zeros(min(BLOCK, int(gap * rate)), np.float32), dt=gap)
            if not alive():
                log.info("Audio stream stopped (device removed?), reopening")
                return
            if self._snapshot.silent_seconds > REOPEN_AFTER_SILENCE_S and now - opened > REOPEN_AFTER_SILENCE_S:
                return

    def _system_session(self, pyaudio) -> None:
        # A fresh PyAudio each session so PortAudio re-enumerates devices and sees the new default.
        pa = pyaudio.PyAudio()
        try:
            dev = default_loopback(pa, pyaudio)
            rate = int(dev["defaultSampleRate"])
            channels = max(1, int(dev["maxInputChannels"]))
            self._use_rate(rate)

            def callback(data, frame_count, time_info, status):
                self._feed(np.frombuffer(data, dtype=np.float32).reshape(-1, channels))
                return None, pyaudio.paContinue

            stream = pa.open(format=pyaudio.paFloat32, channels=channels, rate=rate, input=True,
                             input_device_index=dev["index"], frames_per_buffer=BLOCK, stream_callback=callback)
            self._opened(dev["name"], rate, channels)
            self._last_feed = opened = time.monotonic()
            try:
                self._supervise(rate, opened, alive=stream.is_active)
            finally:
                stream.stop_stream()
                stream.close()
        finally:
            pa.terminate()

    def _app_session(self, exe: str) -> None:
        from .process_loopback import ProcessLoopback, find_root_pid

        cap = ProcessLoopback(find_root_pid(exe), APP_RATE, 2)
        cap.start()
        try:
            self._use_rate(APP_RATE)
            self._opened(f"{exe} (this app only)", APP_RATE, 2)
            self._last_feed = opened = time.monotonic()
            self._supervise(APP_RATE, opened, poll=cap.read)
        finally:
            cap.close()
