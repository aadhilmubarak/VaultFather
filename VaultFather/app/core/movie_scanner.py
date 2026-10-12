"""
Real filesystem scanning for the Movies tab — no placeholder data.

Duration is intentionally left out here: reading it properly needs a
media-probing dependency (ffprobe / pymediainfo), which is a call worth
making deliberately rather than bolting on quietly. It'll be wired in
once we decide which one to bundle. Until then, MovieFile.duration is
None and the UI shows "—".
"""

import os
from dataclasses import dataclass

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv",
    ".flv", ".m4v", ".mpg", ".mpeg", ".ts", ".webm",
}


@dataclass
class MovieFile:
    path: str
    name: str
    size_bytes: int
    duration_seconds: float | None = None  # filled in a later phase

    @property
    def size_human(self) -> str:
        return human_size(self.size_bytes)

    @property
    def duration_human(self) -> str:
        if self.duration_seconds is None:
            return "—"
        total = int(self.duration_seconds)
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)
        return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def scan_movies(folder_path: str) -> list[MovieFile]:
    """
    Recursively walks folder_path and returns every video file found,
    largest first (biggest files are usually the ones worth backing up).
    Returns an empty list if the folder doesn't exist or isn't readable.
    """
    if not folder_path or not os.path.isdir(folder_path):
        return []

    movies: list[MovieFile] = []
    for root, _dirs, files in os.walk(folder_path):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in VIDEO_EXTENSIONS:
                continue
            if _is_series_episode(filename):
                continue  # shows up in the Series tab instead
            full_path = os.path.join(root, filename)
            try:
                size_bytes = os.path.getsize(full_path)
            except OSError:
                continue
            movies.append(MovieFile(path=full_path, name=filename, size_bytes=size_bytes))

    movies.sort(key=lambda m: m.name.casefold())
    return movies


def _is_series_episode(filename: str) -> bool:
    # Local import to avoid a circular import (series_scanner imports
    # VIDEO_EXTENSIONS/human_size from this module).
    from app.core.series_scanner import is_series_episode
    return is_series_episode(filename)
