"""
Upload History Tracker:
Records timestamped upload speeds and volume progress in-memory and in SQLite
so the user can slide/scrub through historical upload speeds just like Google
currency exchange rate or stock market charts.
"""

import time
import math
from collections import deque
from dataclasses import dataclass
from PySide6.QtCore import QObject, Signal


@dataclass
class UploadPoint:
    timestamp: float      # Unix timestamp
    speed_bps: float      # Upload speed in bytes/second
    job_name: str         # Name of the movie/file
    bytes_done: int       # Total bytes transferred at this instant
    percent: float        # Phase percent 0-100


class UploadHistoryTracker(QObject):
    data_updated = Signal()

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = UploadHistoryTracker()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        # Keep up to 3600 points (e.g. 1 hour of continuous 1-second sample points)
        self.history: deque[UploadPoint] = deque(maxlen=3600)
        self._last_sample_time = 0.0

    def record_sample(self, speed_bps: float, job_name: str, bytes_done: int, percent: float):
        now = time.time()
        # Record at most once every 500ms
        if now - self._last_sample_time < 0.5:
            return
        self._last_sample_time = now
        pt = UploadPoint(
            timestamp=now,
            speed_bps=max(0.0, speed_bps),
            job_name=job_name,
            bytes_done=bytes_done,
            percent=percent
        )
        self.history.append(pt)
        self.data_updated.emit()

    def get_points(self) -> list[UploadPoint]:
        return list(self.history)
