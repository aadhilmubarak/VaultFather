import threading
from PySide6.QtCore import QObject, Signal
import time
from app.core.telegram_downloader import restore_and_extract_movie

class DownloadManager(QObject):
    _instance = None
    
    download_started = Signal(str) # job_name
    download_progress = Signal(int, str) # percent, text
    download_finished = Signal(str) # job_name or file_path
    download_failed = Signal(str, str) # job_name, error
    
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self.active_job_name = None
        self.progress_percent = 0
        self.progress_text = ""
        self.speed_bps = 0.0
        self._cancel_event = None
        self._lock = threading.Lock()
        self._speed_tracker = {"t": 0, "bytes": 0}
        self.is_downloading = False

    def start_download(self, job_name, channel_id, message_ids, password, output_dir=None):
        with self._lock:
            if self.is_downloading:
                raise RuntimeError("A download is already in progress.")
            self.is_downloading = True
            self.active_job_name = job_name
            self.progress_percent = 0
            self.progress_text = "Starting..."
            self.speed_bps = 0.0
            self._cancel_event = threading.Event()
            self._speed_tracker = {"t": time.time(), "bytes": 0}

        self.download_started.emit(job_name)

        def _progress(overall_pct, bytes_done_or_text, total_bytes=None):
            with self._lock:
                self.progress_percent = overall_pct
                if isinstance(bytes_done_or_text, str):
                    self.progress_text = bytes_done_or_text
                    self.speed_bps = 0.0
                else:
                    self.progress_text = f"Downloading... {overall_pct}%"
                    # Calculate speed
                    now = time.time()
                    dt = now - self._speed_tracker["t"]
                    if dt >= 0.25:
                        delta_bytes = bytes_done_or_text - self._speed_tracker["bytes"]
                        self.speed_bps = max(0.0, delta_bytes / dt)
                        self._speed_tracker = {"t": now, "bytes": bytes_done_or_text}
                        self.download_progress.emit(self.progress_percent, self.progress_text)
                    return
            self.download_progress.emit(self.progress_percent, self.progress_text)

        def _worker():
            try:
                path = restore_and_extract_movie(
                    channel_id=channel_id,
                    message_ids=message_ids,
                    password=password,
                    output_dir=output_dir,
                    progress_callback=_progress,
                    cancel_event=self._cancel_event
                )
                with self._lock:
                    self.is_downloading = False
                self.download_finished.emit(path)
            except Exception as exc:
                with self._lock:
                    self.is_downloading = False
                self.download_failed.emit(job_name, str(exc))

        threading.Thread(target=_worker, daemon=True).start()

    def cancel_download(self):
        with self._lock:
            if self._cancel_event:
                self._cancel_event.set()
