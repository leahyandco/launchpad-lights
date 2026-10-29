"""Audio analysis: FFT into 8 log-spaced bands with auto-gain, smoothing, beat and level tracking.

Pure numpy so it can be tested with synthetic signals.
"""
import math
from collections import deque
from dataclasses import dataclass

import numpy as np

# Auto-gain speed: how fast the rolling peak decays, in dB/s.
SENSITIVITY = {"low": 1.5, "medium": 4.0, "high": 10.0}
# User-facing gain settings and their defaults.
GAIN_DEFAULTS = {"auto_gain": True, "gain_db": 0.0, "range_db": 32.0, "noise_floor_db": -75.0}
REFERENCE_DB = -12.0  # with auto-gain off, a band/level this loud fills the display at 0 dB gain
MIN_PEAK_DB = -55.0  # auto-gain never boosts beyond this
SILENCE_RMS = 1e-5
RELEASE_S = 0.25  # bars fall full scale in this long
BEAT_RATIO = 1.5
BEAT_COOLDOWN_S = 0.25
BASS_AVG_S = 1.0
BPM_MIN, BPM_MAX = 70.0, 180.0
BPM_WINDOW_S = 8.0  # beats older than this are ignored
BPM_TIMEOUT_S = 4.0  # no beat for this long: tempo unknown


@dataclass(frozen=True)
class Snapshot:
    bands: tuple[float, ...] = (0.0,) * 8  # 0-1 per band, low to high
    level: float = 0.0  # mono RMS, 0-1 after gain
    level_l: float = 0.0
    level_r: float = 0.0
    stereo: bool = False
    beat_count: int = 0  # increments on each beat; compare to detect new beats
    bpm: float = 0.0  # 0 when the tempo is unknown
    silent_seconds: float = 0.0


def estimate_bpm(beat_times: list[float]) -> float:
    """Median inter-beat interval, folded into BPM_MIN..BPM_MAX. 0 if too few beats."""
    if len(beat_times) < 4:
        return 0.0
    lo, hi = 60.0 / BPM_MAX, 60.0 / BPM_MIN
    intervals = []
    for a, b in zip(beat_times, beat_times[1:]):
        d = b - a
        if d <= 0:
            continue
        while d < lo:
            d *= 2
        while d > hi:
            d /= 2
        intervals.append(d)
    if len(intervals) < 3:
        return 0.0
    return 60.0 / float(np.median(intervals))


class Analyzer:
    def __init__(self, rate: int, block: int = 1024, bands: int = 8, fmin: float = 40.0, fmax: float = 16000.0,
                 sensitivity: str = "medium", tilt_db: float = 3.0):
        self.rate = rate
        self.block = block
        self.window = np.hanning(block).astype(np.float32)
        self._norm = 2.0 / float(self.window.sum())
        freqs = np.fft.rfftfreq(block, 1.0 / rate)
        edges = np.searchsorted(freqs, np.geomspace(fmin, min(fmax, rate / 2), bands + 1))
        for i in range(1, len(edges)):  # every band gets its own bins, even when the low bands are narrower than one
            edges[i] = max(edges[i], edges[i - 1] + 1)
        self.band_slices = [slice(lo, hi) for lo, hi in zip(edges[:-1], edges[1:])]
        # Music has less energy up high; tilt so the top bands are not permanently dim.
        self.tilt = tilt_db * np.arange(bands)
        self.buf = np.zeros(block, np.float32)
        self.configure(sensitivity=sensitivity, **GAIN_DEFAULTS)
        self.peak_db = MIN_PEAK_DB
        self.vu_peak_db = MIN_PEAK_DB
        self.bands = np.zeros(bands)
        self.vu = np.zeros(3)  # mono, left, right
        self.stereo = False
        self.bass_avg = 0.0
        self.clock = 0.0
        self.last_beat = -math.inf
        self.beat_count = 0
        self.beat_times: deque[float] = deque(maxlen=24)
        self.bpm = 0.0
        self.silent_seconds = 0.0

    def configure(self, *, sensitivity: str | None = None, auto_gain: bool | None = None, gain_db: float | None = None,
                  range_db: float | None = None, noise_floor_db: float | None = None) -> None:
        if sensitivity is not None:
            self.sensitivity = sensitivity if sensitivity in SENSITIVITY else "medium"
            self.decay = SENSITIVITY[self.sensitivity]
        if auto_gain is not None:
            self.auto_gain = bool(auto_gain)
        if gain_db is not None:
            self.gain_db = float(gain_db)
        if range_db is not None:
            self.range_db = max(6.0, float(range_db))
        if noise_floor_db is not None:
            self.noise_floor_db = float(noise_floor_db)

    def set_sensitivity(self, name: str) -> None:
        self.configure(sensitivity=name)

    def _normalise(self, db: np.ndarray, peak: float) -> np.ndarray:
        ceiling = peak if self.auto_gain else REFERENCE_DB
        return np.clip((db + self.gain_db - (ceiling - self.range_db)) / self.range_db, 0.0, 1.0)

    def process(self, samples: np.ndarray, dt: float | None = None) -> Snapshot:
        """Feed a block of samples, shape (n,) or (n, channels). dt defaults to n / rate."""
        samples = np.asarray(samples, np.float32)
        if samples.ndim == 2:
            self.stereo = samples.shape[1] >= 2
            mono = samples.mean(axis=1)
            left, right = samples[:, 0], samples[:, 1 if self.stereo else 0]
        else:
            self.stereo = False
            mono = left = right = samples
        n = len(mono)
        if dt is None:
            dt = n / self.rate
        self.clock += dt
        if n >= self.block:
            self.buf = mono[-self.block:].copy()
        elif n:
            self.buf = np.concatenate((self.buf[n:], mono))

        rms = np.array([np.sqrt(np.mean(x * x)) if n else 0.0 for x in (mono, left, right)])
        silent = rms[0] < SILENCE_RMS
        self.silent_seconds = self.silent_seconds + dt if silent else 0.0

        power = (np.abs(np.fft.rfft(self.buf * self.window)) * self._norm) ** 2
        band_power = np.array([power[s].sum() for s in self.band_slices])
        raw_db = 10 * np.log10(band_power + 1e-20)
        band_db = raw_db + self.tilt
        rms_db = 20 * np.log10(rms + 1e-20)

        if not silent:
            self.peak_db = max(float(band_db.max()), self.peak_db - self.decay * dt, MIN_PEAK_DB)
            self.vu_peak_db = max(float(rms_db.max()), self.vu_peak_db - self.decay * dt, MIN_PEAK_DB)

        levels = self._normalise(band_db, self.peak_db)
        levels[raw_db < self.noise_floor_db] = 0.0
        vu = self._normalise(rms_db, self.vu_peak_db)
        vu[rms_db < self.noise_floor_db] = 0.0
        # Instant attack, linear release.
        fall = dt / RELEASE_S
        self.bands = np.maximum(levels, self.bands - fall)
        self.vu = np.maximum(vu, self.vu - fall)

        self._detect_beat(float(band_power[:2].sum()))
        self.bass_avg += (1 - math.exp(-dt / BASS_AVG_S)) * (band_power[:2].sum() - self.bass_avg)
        return self.snapshot()

    def _detect_beat(self, bass: float) -> None:
        ceiling = self.peak_db if self.auto_gain else REFERENCE_DB - self.gain_db
        loud_enough = 10 * math.log10(bass + 1e-20) > max(self.noise_floor_db, ceiling - self.range_db)
        if (loud_enough and bass > BEAT_RATIO * self.bass_avg
                and self.clock - self.last_beat >= BEAT_COOLDOWN_S):
            self.beat_count += 1
            self.last_beat = self.clock
            self.beat_times.append(self.clock)
            recent = [t for t in self.beat_times if self.clock - t <= BPM_WINDOW_S]
            estimate = estimate_bpm(recent)
            if estimate:
                # Light smoothing so the readout doesn't jitter beat to beat.
                self.bpm = estimate if not self.bpm or abs(estimate - self.bpm) > 8 else 0.7 * self.bpm + 0.3 * estimate
        if self.clock - self.last_beat > BPM_TIMEOUT_S:
            self.bpm = 0.0

    def snapshot(self) -> Snapshot:
        return Snapshot(
            bands=tuple(float(b) for b in self.bands),
            level=float(self.vu[0]),
            level_l=float(self.vu[1]),
            level_r=float(self.vu[2]),
            stereo=self.stereo,
            beat_count=self.beat_count,
            bpm=self.bpm,
            silent_seconds=self.silent_seconds,
        )
