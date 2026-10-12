"""
Top Movies Background Service:
Fetches top 100 movies from TMDb (cached to disk), pre-downloads high quality backdrops,
and cycles the backdrop every 7 seconds. Emits signals for background update:
(backdrop_pixmap, blurred_backdrop_pixmap, movie_title, movie_year, movie_plot, imdb_id, imdb_url)
"""

import os
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, QTimer, Qt
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtWidgets import QGraphicsBlurEffect, QGraphicsScene, QGraphicsPixmapItem

from app.core.config import load_config
from app.core.logger import get_logger

logger = get_logger()
CACHE_DIR = Path.home() / ".vaultfather" / "top100_cache"
BACKDROP_BASE = "https://image.tmdb.org/t/p/w1280"
CYCLE_INTERVAL_MS = 7000  # 7 seconds


@dataclass
class TopMovieItem:
    title: str
    year: str
    plot: str
    tmdb_id: int
    imdb_id: str | None
    backdrop_url: str | None
    local_backdrop_path: str | None = None

    @property
    def imdb_url(self) -> str:
        if self.imdb_id:
            return f"https://www.imdb.com/title/{self.imdb_id}/"
        query = urllib.parse.quote(f"{self.title} {self.year}".strip())
        return f"https://www.imdb.com/find?q={query}"


class TopMoviesBackgroundService(QObject):
    movie_changed = Signal(object, object, str, str, str, str)  # (pixmap, blurred_pixmap, title, year, plot, imdb_url)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._movies: list[TopMovieItem] = []
        self._current_index = 0
        self._timer = QTimer(self)
        self._timer.setInterval(CYCLE_INTERVAL_MS)
        self._timer.timeout.connect(self._on_cycle)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def start(self):
        # Load from disk cache if available
        self._load_cached_list()
        # Launch background fetch if list is empty or older than 24h
        import threading
        threading.Thread(target=self._fetch_top_100_worker, daemon=True).start()
        self._timer.start()

    def _load_cached_list(self):
        cache_file = CACHE_DIR / "top100.json"
        if cache_file.is_file():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                self._movies = [TopMovieItem(**item) for item in data]
                if self._movies:
                    self._on_cycle()
            except Exception as exc:
                logger.warning(f"Failed to load cached top 100: {exc}")

    def _fetch_top_100_worker(self):
        config = load_config()
        api_key = config.get("tmdb_api_key")
        if not api_key:
            return

        cache_file = CACHE_DIR / "top100.json"
        # Fetch actual top 100 movies by requiring 3000+ votes
        fetched: list[TopMovieItem] = []
        try:
            for page in range(1, 6):
                url = f"https://api.themoviedb.org/3/discover/movie?api_key={api_key}&sort_by=vote_average.desc&vote_count.gte=3000&page={page}"
                req = urllib.request.Request(url, headers={"User-Agent": "VaultFather/2.0"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("results", []):
                    bpath = m.get("backdrop_path")
                    if not bpath:
                        continue
                    tmdb_id = m.get("id")
                    title = m.get("title") or "Unknown"
                    year = (m.get("release_date") or "")[:4]
                    plot = m.get("overview") or "No overview available."
                    backdrop_url = f"{BACKDROP_BASE}{bpath}"
                    fetched.append(TopMovieItem(
                        title=title,
                        year=year,
                        plot=plot,
                        tmdb_id=tmdb_id,
                        imdb_id=None,
                        backdrop_url=backdrop_url,
                    ))
                if len(fetched) >= 100:
                    break
            
            self._movies = fetched[:100]

            def _save():
                try:
                    data = [item.__dict__ for item in self._movies]
                    cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                except Exception:
                    pass
            _save()

            if self._movies:
                QTimer.singleShot(0, self._on_cycle)

            # Pre-download all backdrops in the background
            for item in self._movies:
                self._ensure_backdrop_downloaded(item)
            
            # Save again once all paths are known locally
            _save()

        except Exception as exc:
            logger.warning(f"Error fetching top 100 movies: {exc}")

    def _ensure_backdrop_downloaded(self, item: TopMovieItem) -> str | None:
        if not item.backdrop_url:
            return None
        filename = f"{item.tmdb_id}_backdrop.jpg"
        target = CACHE_DIR / filename
        if target.is_file():
            item.local_backdrop_path = str(target)
            return str(target)
        try:
            req = urllib.request.Request(item.backdrop_url, headers={"User-Agent": "VaultFather/2.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            target.write_bytes(data)
            item.local_backdrop_path = str(target)
            return str(target)
        except Exception:
            return None

    def _on_cycle(self):
        self.show_next()

    def show_previous(self):
        """Shows the previously shown movie background and info."""
        if not self._movies:
            return
        # Move back 2 steps because _emit_movie advances or points to current
        self._current_index = (self._current_index - 2) % len(self._movies)
        self._show_movie_at_index(self._current_index)
        # Reset 7-second timer so user has full 7 seconds to look at it
        self._timer.start()

    def show_next(self):
        """Shows the next movie background and info."""
        if not self._movies:
            return
        if self._current_index >= len(self._movies):
            self._current_index = 0
        idx = self._current_index
        self._current_index = (self._current_index + 1) % len(self._movies)
        self._show_movie_at_index(idx)
        self._timer.start()

    def _show_movie_at_index(self, idx: int):
        item = self._movies[idx]
        path = item.local_backdrop_path
        if not path or not os.path.isfile(path):
            import threading
            threading.Thread(target=lambda: self._download_and_emit(item), daemon=True).start()
            return
        self._emit_movie(item, path)

    def _download_and_emit(self, item: TopMovieItem):
        path = self._ensure_backdrop_downloaded(item)
        if path:
            QTimer.singleShot(0, lambda: self._emit_movie(item, path))

    def _emit_movie(self, item: TopMovieItem, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            return

        # Fetch imdb_id lazily if not present
        if not item.imdb_id:
            import threading
            def _fetch_imdb():
                config = load_config()
                key = config.get("tmdb_api_key")
                if key and item.tmdb_id:
                    try:
                        u = f"https://api.themoviedb.org/3/movie/{item.tmdb_id}/external_ids?api_key={key}"
                        req = urllib.request.Request(u, headers={"User-Agent": "VaultFather/2.0"})
                        with urllib.request.urlopen(req, timeout=6) as r:
                            d = json.loads(r.read().decode("utf-8"))
                        item.imdb_id = d.get("imdb_id")
                    except Exception:
                        pass
            threading.Thread(target=_fetch_imdb, daemon=True).start()

        blurred = self._create_blurred_pixmap(pix)
        self.movie_changed.emit(
            pix,
            blurred,
            item.title,
            item.year,
            item.plot,
            item.imdb_url
        )

    def _create_blurred_pixmap(self, src: QPixmap) -> QPixmap:
        # Scale down then scale up for efficient and beautiful filmic blur
        small = src.scaled(320, 180, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        return small.scaled(src.width(), src.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
