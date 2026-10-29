"""Now-playing info from Windows media sessions (Spotify, browsers, anything with media controls)."""
import asyncio
import logging
import threading
from dataclasses import dataclass

log = logging.getLogger(__name__)

POLL_S = 1.0
PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING


@dataclass(frozen=True)
class NowPlaying:
    title: str = ""
    artist: str = ""
    app: str = ""
    playing: bool = False


class MediaService:
    def __init__(self):
        self._info = NowPlaying()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="media", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None

    def latest(self) -> NowPlaying:
        return self._info

    def _run(self) -> None:
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
        except ImportError as e:
            log.warning("Now playing unavailable (winrt not installed): %s", e)
            return
        asyncio.run(self._loop(Manager))

    async def _loop(self, Manager) -> None:
        manager = await Manager.request_async()
        last_error = None
        while not self._stop.is_set():
            try:
                session = manager.get_current_session()
                if session is None:
                    info = NowPlaying()
                else:
                    props = await session.try_get_media_properties_async()
                    status = session.get_playback_info().playback_status
                    info = NowPlaying(props.title or "", props.artist or "", session.source_app_user_model_id or "",
                                      int(status) == PLAYING)
                if info != self._info:
                    if info.title != self._info.title and info.title:
                        log.info("Now playing: %s - %s", info.artist, info.title)
                    self._info = info
                last_error = None
            except Exception as e:
                if str(e) != last_error:
                    log.warning("Media session error: %s", e)
                    last_error = str(e)
            await asyncio.sleep(POLL_S)
