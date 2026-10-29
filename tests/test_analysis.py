import numpy as np

from launchpad_lights.services.analysis import Analyzer

RATE = 48000
BLOCK = 1024


def sine(freq, seconds, amp=0.5, rate=RATE):
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def feed(an, signal):
    snap = None
    for i in range(0, len(signal) - BLOCK + 1, BLOCK):
        snap = an.process(signal[i:i + BLOCK])
    return snap


def test_band_placement():
    edges = np.geomspace(40, 16000, 9)
    for band in range(8):
        centre = float(np.sqrt(edges[band] * edges[band + 1]))
        if band == 0:
            centre = 50.0  # band 0 is a single FFT bin at 48k/1024
        an = Analyzer(RATE, BLOCK, tilt_db=0.0)
        snap = feed(an, sine(centre, 0.5))
        assert int(np.argmax(snap.bands)) == band, (band, centre, snap.bands)


def test_silence_is_dark_and_counted():
    an = Analyzer(RATE, BLOCK)
    snap = feed(an, np.zeros(RATE, np.float32))
    assert max(snap.bands) == 0.0
    assert snap.level == 0.0
    assert snap.silent_seconds > 0.9


def test_auto_gain_quiet_and_loud_both_fill():
    for amp in (0.005, 0.9):
        an = Analyzer(RATE, BLOCK)
        snap = feed(an, sine(1000, 2.0, amp))
        assert snap.bands[4] > 0.9, (amp, snap.bands)
        assert snap.level > 0.9


def test_manual_gain():
    quiet = sine(1000, 1.0, 0.003)
    an = Analyzer(RATE, BLOCK)
    an.configure(auto_gain=False)
    assert feed(an, quiet).bands[4] < 0.3
    an = Analyzer(RATE, BLOCK)
    an.configure(auto_gain=False, gain_db=24.0)
    assert feed(an, quiet).bands[4] > 0.9


def test_gain_offset_with_auto_gain():
    loud = sine(1000, 1.0, 0.5)
    base = feed(Analyzer(RATE, BLOCK), loud).bands
    an = Analyzer(RATE, BLOCK)
    an.configure(gain_db=-12.0)
    cut = feed(an, loud).bands
    assert cut[4] < base[4] - 0.2


def test_release_falls_over_quarter_second():
    an = Analyzer(RATE, BLOCK)
    feed(an, sine(1000, 1.0))
    after_100ms = feed(an, np.zeros(int(0.1 * RATE), np.float32)).bands[4]
    after_400ms = feed(an, np.zeros(int(0.3 * RATE), np.float32)).bands[4]
    assert 0.3 < after_100ms < 0.9
    assert after_400ms == 0.0


def test_beats_on_bass_bursts():
    seconds = 4.0
    sig = sine(60, seconds, amp=0.03)
    burst = sine(60, 0.1, amp=0.8)
    for start in np.arange(0.25, seconds, 0.5):
        i = int(start * RATE)
        sig[i:i + len(burst)] = burst
    an = Analyzer(RATE, BLOCK)
    snap = feed(an, sig)
    assert 7 <= snap.beat_count <= 9, snap.beat_count


def test_bpm_from_bass_bursts():
    seconds = 8.0
    sig = sine(60, seconds, amp=0.03)
    burst = sine(60, 0.08, amp=0.8)
    for start in np.arange(0.2, seconds, 0.5):  # 120 BPM
        i = int(start * RATE)
        sig[i:i + len(burst)] = burst
    an = Analyzer(RATE, BLOCK)
    snap = feed(an, sig)
    assert 115 <= snap.bpm <= 125, snap.bpm


def test_estimate_bpm_folds_octaves():
    from launchpad_lights.services.analysis import estimate_bpm
    halves = [i * 1.0 for i in range(8)]  # 60 BPM folds up to 120
    assert estimate_bpm(halves) == 120.0
    assert estimate_bpm([0, 0.5]) == 0.0


def test_stereo_levels():
    an = Analyzer(RATE, BLOCK)
    left = sine(1000, 1.0, 0.5)
    stereo = np.stack([left, left * 0.01], axis=1)
    snap = None
    for i in range(0, len(left) - BLOCK + 1, BLOCK):
        snap = an.process(stereo[i:i + BLOCK])
    assert snap.stereo
    assert snap.level_l > 0.9
    assert snap.level_r < snap.level_l - 0.3
