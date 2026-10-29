"""Capture a single application's audio with WASAPI process loopback (Windows 10 2004+/11).

PortAudio has no process loopback, so this talks to the Windows audio APIs directly via comtypes.
"""
import ctypes
import threading
from ctypes import POINTER, byref, c_int, c_int64, c_uint32, c_uint64, c_void_p, wintypes

import numpy as np
import psutil

from lpctl.winutil import ensure_com

from comtypes import COMObject, GUID, HRESULT, IUnknown, STDMETHOD  # noqa: E402  (after coinit flags)

AUDCLNT_SHAREMODE_SHARED = 0
AUDCLNT_STREAMFLAGS_LOOPBACK = 0x00020000
AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM = 0x80000000
AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY = 0x08000000
AUDCLNT_BUFFERFLAGS_SILENT = 0x2
ACTIVATION_TYPE_PROCESS_LOOPBACK = 1
LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE = 0
VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK = "VAD\\Process_Loopback"
VT_BLOB = 65
WAVE_FORMAT_IEEE_FLOAT = 3
BUFFER_HNS = 2_000_000  # 200 ms


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [("wFormatTag", wintypes.WORD), ("nChannels", wintypes.WORD), ("nSamplesPerSec", wintypes.DWORD),
                ("nAvgBytesPerSec", wintypes.DWORD), ("nBlockAlign", wintypes.WORD),
                ("wBitsPerSample", wintypes.WORD), ("cbSize", wintypes.WORD)]


class ACTIVATION_PARAMS(ctypes.Structure):
    _fields_ = [("ActivationType", c_int), ("TargetProcessId", wintypes.DWORD), ("ProcessLoopbackMode", c_int)]


class BLOB(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.ULONG), ("pBlobData", c_void_p)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", wintypes.USHORT), ("r1", wintypes.WORD), ("r2", wintypes.WORD), ("r3", wintypes.WORD),
                ("blob", BLOB)]


class IAudioCaptureClient(IUnknown):
    _iid_ = GUID("{C8ADBD64-E71E-48a0-A4DE-185C395CD317}")
    _methods_ = [
        STDMETHOD(HRESULT, "GetBuffer", [POINTER(c_void_p), POINTER(c_uint32), POINTER(wintypes.DWORD),
                                         POINTER(c_uint64), POINTER(c_uint64)]),
        STDMETHOD(HRESULT, "ReleaseBuffer", [c_uint32]),
        STDMETHOD(HRESULT, "GetNextPacketSize", [POINTER(c_uint32)]),
    ]


class IAudioClient(IUnknown):
    _iid_ = GUID("{1CB9AD4C-DBFA-4c32-B178-C2F568A703B2}")
    _methods_ = [
        STDMETHOD(HRESULT, "Initialize", [c_int, wintypes.DWORD, c_int64, c_int64, POINTER(WAVEFORMATEX),
                                          POINTER(GUID)]),
        STDMETHOD(HRESULT, "GetBufferSize", [POINTER(c_uint32)]),
        STDMETHOD(HRESULT, "GetStreamLatency", [POINTER(c_int64)]),
        STDMETHOD(HRESULT, "GetCurrentPadding", [POINTER(c_uint32)]),
        STDMETHOD(HRESULT, "IsFormatSupported", [c_int, POINTER(WAVEFORMATEX), POINTER(POINTER(WAVEFORMATEX))]),
        STDMETHOD(HRESULT, "GetMixFormat", [POINTER(POINTER(WAVEFORMATEX))]),
        STDMETHOD(HRESULT, "GetDevicePeriod", [POINTER(c_int64), POINTER(c_int64)]),
        STDMETHOD(HRESULT, "Start", []),
        STDMETHOD(HRESULT, "Stop", []),
        STDMETHOD(HRESULT, "Reset", []),
        STDMETHOD(HRESULT, "SetEventHandle", [wintypes.HANDLE]),
        STDMETHOD(HRESULT, "GetService", [POINTER(GUID), POINTER(POINTER(IUnknown))]),
    ]


class IActivateAudioInterfaceAsyncOperation(IUnknown):
    _iid_ = GUID("{72A22D78-CDE4-431D-B8CC-843A71199B6D}")
    _methods_ = [STDMETHOD(HRESULT, "GetActivateResult", [POINTER(HRESULT), POINTER(POINTER(IUnknown))])]


class IActivateAudioInterfaceCompletionHandler(IUnknown):
    _iid_ = GUID("{41D949AB-9862-444A-80F6-C261334DA5EB}")
    _methods_ = [STDMETHOD(HRESULT, "ActivateCompleted", [POINTER(IActivateAudioInterfaceAsyncOperation)])]


class IAgileObject(IUnknown):
    _iid_ = GUID("{94ea2b94-e9cc-49e0-c0ff-ee64ca8f5b90}")
    _methods_ = []


class _CompletionHandler(COMObject):
    _com_interfaces_ = [IActivateAudioInterfaceCompletionHandler, IAgileObject]

    def __init__(self):
        super().__init__()
        self.done = threading.Event()
        self.hr = 0
        self.unknown = None

    def ActivateCompleted(self, this, operation):
        hr = HRESULT()
        unk = POINTER(IUnknown)()
        try:
            operation.GetActivateResult(byref(hr), byref(unk))
            self.hr, self.unknown = hr.value, unk
        except Exception as e:  # COMError carries the HRESULT
            self.hr = getattr(e, "hresult", -1)
        finally:
            self.done.set()
        return 0


_activate = ctypes.WinDLL("Mmdevapi.dll").ActivateAudioInterfaceAsync
_activate.argtypes = [wintypes.LPCWSTR, POINTER(GUID), POINTER(PROPVARIANT),
                      POINTER(IActivateAudioInterfaceCompletionHandler),
                      POINTER(POINTER(IActivateAudioInterfaceAsyncOperation))]
_activate.restype = HRESULT


def find_root_pid(exe: str) -> int:
    """PID of the top-most process with this executable name (e.g. the main chrome.exe).
    Capture includes the whole process tree, so this catches audio from child processes too."""
    exe = exe.lower()
    procs = [p for p in psutil.process_iter(["name", "ppid", "create_time"]) if (p.info["name"] or "").lower() == exe]
    if not procs:
        raise RuntimeError(f"{exe} is not running")
    pids = {p.pid for p in procs}
    roots = [p for p in procs if p.info["ppid"] not in pids] or procs
    return min(roots, key=lambda p: p.info["create_time"] or 0).pid


class ProcessLoopback:
    def __init__(self, pid: int, rate: int = 48000, channels: int = 2):
        self.pid, self.rate, self.channels = pid, rate, channels
        self._client = None
        self._capture = None
        self._handler = None

    def start(self) -> None:
        ensure_com()
        params = ACTIVATION_PARAMS(ACTIVATION_TYPE_PROCESS_LOOPBACK, self.pid, LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE)
        pv = PROPVARIANT(vt=VT_BLOB)
        pv.blob.cbSize = ctypes.sizeof(params)
        pv.blob.pBlobData = ctypes.cast(byref(params), c_void_p)
        self._handler = _CompletionHandler()
        handler_ptr = self._handler.QueryInterface(IActivateAudioInterfaceCompletionHandler)
        op = POINTER(IActivateAudioInterfaceAsyncOperation)()
        _activate(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, byref(IAudioClient._iid_), byref(pv), handler_ptr, byref(op))
        if not self._handler.done.wait(5):
            raise RuntimeError("Timed out activating process loopback")
        if self._handler.hr < 0 or not self._handler.unknown:
            raise RuntimeError(f"Process loopback activation failed (0x{self._handler.hr & 0xFFFFFFFF:08X})")
        client = self._handler.unknown.QueryInterface(IAudioClient)
        block = 4 * self.channels
        fmt = WAVEFORMATEX(WAVE_FORMAT_IEEE_FLOAT, self.channels, self.rate, self.rate * block, block, 32, 0)
        client.Initialize(AUDCLNT_SHAREMODE_SHARED,
                          AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM
                          | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                          BUFFER_HNS, 0, byref(fmt), None)
        unk = POINTER(IUnknown)()
        client.GetService(byref(IAudioCaptureClient._iid_), byref(unk))
        self._capture = unk.QueryInterface(IAudioCaptureClient)
        client.Start()
        self._client = client

    def read(self) -> np.ndarray | None:
        """All audio captured since the last call, shape (frames, channels), or None if nothing."""
        chunks = []
        packet = c_uint32()
        data, frames, flags = c_void_p(), c_uint32(), wintypes.DWORD()
        self._capture.GetNextPacketSize(byref(packet))
        while packet.value:
            self._capture.GetBuffer(byref(data), byref(frames), byref(flags), None, None)
            n = frames.value
            if flags.value & AUDCLNT_BUFFERFLAGS_SILENT or not data.value:
                chunks.append(np.zeros((n, self.channels), np.float32))
            else:
                raw = ctypes.string_at(data.value, n * 4 * self.channels)
                chunks.append(np.frombuffer(raw, np.float32).reshape(n, self.channels))
            self._capture.ReleaseBuffer(n)
            self._capture.GetNextPacketSize(byref(packet))
        return np.concatenate(chunks) if chunks else None

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.Stop()
            except Exception:
                pass
        self._capture = self._client = self._handler = None
