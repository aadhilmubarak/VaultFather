"""
A shared, app-wide poster loader: PosterCard widgets call request() and
get a poster_ready signal back once it's available, without ever
blocking the UI thread. One background thread processes requests
sequentially — posters are small and this only runs once per title
(disk cache handles every repeat visit to the Movies tab instantly).
"""

import queue
import threading

from PySide6.QtCore import QObject, Signal

from app.core.poster_service import fetch_poster, cached_poster_path, _cache_key


class PosterLoader(QObject):
    poster_ready = Signal(str, str)  # cache_key, local_path ("" if none found)

    def __init__(self):
        super().__init__()
        self._queue: queue.Queue = queue.Queue()
        self._requested: set[str] = set()
        self._lock = threading.Lock()
        self._worker_running = False

    def request(self, title: str, year: str | None, media_type: str = "movie") -> str | None:
        """
        Returns a cached path immediately if one's already on disk
        (synchronous, no network). Otherwise queues a background fetch
        and returns None — connect to poster_ready to get the result
        when it lands.
        """
        key = _cache_key(title, year, media_type)
        cached = cached_poster_path(title, year, media_type)
        if cached:
            return cached

        with self._lock:
            if key in self._requested:
                return None
            self._requested.add(key)

        self._queue.put((key, title, year, media_type))
        self._ensure_worker()
        return None

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker_running:
                return
            self._worker_running = True
        threading.Thread(target=self._process_loop, daemon=True).start()

    def _process_loop(self) -> None:
        while True:
            try:
                key, title, year, media_type = self._queue.get(timeout=0.5)
            except queue.Empty:
                with self._lock:
                    self._worker_running = False
                return

            path = fetch_poster(title, year, media_type) or ""
            self.poster_ready.emit(key, path)


# One shared instance for the whole app — posters are a shared cache,
# not per-page state.
poster_loader = PosterLoader()
