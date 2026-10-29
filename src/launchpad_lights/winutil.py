"""Small Windows helpers: COM init per thread, media/hotkey key presses, mic mute, audio apps."""
import ctypes
import logging
import sys
import threading

if not hasattr(sys, "coinit_flags"):
    sys.coinit_flags = 0  # multithreaded apartment; must be set before comtypes is first imported

log = logging.getLogger(__name__)
_com = threading.local()

KEYEVENTF_EXTENDEDKEY = 0x1
KEYEVENTF_KEYUP = 0x2

MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "prev": 0xB1,
    "stop": 0xB2,
    "mute": 0xAD,
    "vol_down": 0xAE,
    "vol_up": 0xAF,
}
MEDIA_LABELS = {
    "play_pause": "Play / pause",
    "next": "Next track",
    "prev": "Previous track",
    "stop": "Stop",
    "mute": "Mute",
    "vol_down": "Volume down",
    "vol_up": "Volume up",
}
NAMED_KEYS = {
    "ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B,
    "esc": 0x1B, "escape": 0x1B, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "ins": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pgup": 0x21, "pagedown": 0x22, "pgdn": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "printscreen": 0x2C, "prtsc": 0x2C, "pause": 0x13, "capslock": 0x14,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
    **MEDIA_KEYS,
}
EXTENDED = {0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x5B, *MEDIA_KEYS.values()}


_instance_mutex = None
ERROR_ALREADY_EXISTS = 183


def claim_single_instance(name: str = "Local\\LaunchpadLights") -> bool:
    """False if another copy already holds the named mutex. The handle lives until exit."""
    global _instance_mutex
    kernel32 = ctypes.windll.kernel32
    _instance_mutex = kernel32.CreateMutexW(None, False, name)
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS


def message_box(title: str, text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)  # MB_ICONINFORMATION


def ensure_com() -> None:
    """Initialise COM (MTA) on the calling thread once."""
    if getattr(_com, "ready", False):
        return
    import comtypes
    try:
        comtypes.CoInitializeEx(0)
    except OSError:
        pass  # already initialised in another mode on this thread; still usable
    _com.ready = True


def parse_combo(combo: str) -> list[int]:
    """'ctrl+shift+m' -> virtual key codes. Raises ValueError on unknown keys."""
    codes = []
    for part in combo.lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in NAMED_KEYS:
            codes.append(NAMED_KEYS[part])
        elif len(part) == 1 and part.isalnum():
            codes.append(ord(part.upper()))
        else:
            raise ValueError(f"Unknown key {part!r} in {combo!r}")
    if not codes:
        raise ValueError("Empty key combo")
    return codes


def send_keys(codes: list[int]) -> None:
    user32 = ctypes.windll.user32
    for vk in codes:
        user32.keybd_event(vk, 0, KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0, 0)
    for vk in reversed(codes):
        user32.keybd_event(vk, 0, (KEYEVENTF_EXTENDEDKEY if vk in EXTENDED else 0) | KEYEVENTF_KEYUP, 0)


def send_combo(combo: str) -> None:
    send_keys(parse_combo(combo))


def send_media(name: str) -> None:
    send_keys([MEDIA_KEYS[name]])


def _mic_endpoint():
    ensure_com()
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    dev = AudioUtilities.GetMicrophone()
    return dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)


def mic_muted() -> bool | None:
    """True/False for the default microphone, None if there is no microphone."""
    try:
        return bool(_mic_endpoint().GetMute())
    except Exception:
        return None


def toggle_mic() -> bool | None:
    try:
        ep = _mic_endpoint()
        muted = not ep.GetMute()
        ep.SetMute(muted, None)
        log.info("Microphone %s", "muted" if muted else "unmuted")
        return muted
    except Exception as e:
        log.warning("Mic mute unavailable: %s", e)
        return None


def audio_apps() -> list[str]:
    """Executable names of processes that currently have an audio session."""
    try:
        ensure_com()
        from pycaw.pycaw import AudioUtilities
        names = {s.Process.name() for s in AudioUtilities.GetAllSessions() if s.Process}
        return sorted(names, key=str.lower)
    except Exception as e:
        log.warning("Could not list audio apps: %s", e)
        return []
