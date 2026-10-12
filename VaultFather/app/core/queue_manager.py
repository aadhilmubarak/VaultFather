"""
The Backup Queue's brain: takes movies added from the Movies tab, and
processes them one at a time — archive once, then upload to every
chosen destination, then record — on a background thread so the UI
never blocks on a multi-gigabyte movie.

Multi-destination strategy: the movie is archived exactly once (same
file, same password, regardless of how many destinations it's going
to). The first destination gets a real upload; every destination after
that gets the same messages *forwarded* instead of re-uploaded — same
file, zero extra bytes sent, near-instant. Each destination still gets
its own database record and its own success/failure, so one channel
failing doesn't affect another that already succeeded.

Runs on a plain Python thread (not QThread) since the heavy lifting
(subprocess for 7z, asyncio for Telegram) doesn't need Qt at all; it
only touches Qt via signals, which PySide6 safely marshals back to the
main thread regardless of which thread emitted them.
"""

import asyncio
import os
import threading
import time
import uuid
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from app.core.backup_job import run_archive_job
from app.core.config import load_config
from app.core.database import update_status, get_destination_by_name, record_movie_backup, \
    record_series_backup, has_series_announcement, record_series_announcement, \
    save_persistent_queue_job, remove_persistent_queue_job, load_persistent_queue_jobs
from app.core.telegram_client import get_client, TelegramNotConfiguredError
from app.core.telegram_uploader import upload_movie, forward_movie, UploadCancelled
from app.core.logger import get_logger

logger = get_logger()
CONNECT_TIMEOUT = 45.0    # allow sufficient handshake window for obfuscated MTProto
RESOLVE_TIMEOUT = 30.0    # same for resolving a destination channel


@dataclass
class BackupJob:
    id: str
    movie_path: str
    movie_name: str
    destinations: list[str]
    status: str = "queued"   # queued | archiving | uploading | done | failed
    percent: int = 0         # blended 0-50 archiving / 50-100 uploading — drives the queue-row bar
    phase_percent: int = 0   # 0-100 within whatever's happening right now — drives the small ring
    bytes_done: int = 0
    bytes_total: int = 0
    upload_speed_bps: float = 0.0   # bytes/sec, only meaningful during "uploading"
    error: str | None = None
    backup_ids: dict = field(default_factory=dict)   # destination name -> DB record id
    series_name: str | None = None    # set only for TV episodes
    season_number: int | None = None
    episode_number: int | None = None
    send_season_intro: bool = False   # True only for the first episode queued in a season batch
    subtitle_paths: list[str] = field(default_factory=list)
    upload_start_time: float | None = None
    upload_end_time: float | None = None

    @property
    def season_label(self) -> str | None:
        return f"S{self.season_number:02d}" if self.season_number is not None else None

    @property
    def upload_elapsed_seconds(self) -> float | None:
        if self.upload_start_time is None:
            return None
        if self.upload_end_time is not None:
            return max(0.0, self.upload_end_time - self.upload_start_time)
        return max(0.0, time.time() - self.upload_start_time)

    @property
    def upload_time_str(self) -> str | None:
        secs = self.upload_elapsed_seconds
        if secs is None:
            return None
        secs_int = int(secs)
        m, s = divmod(secs_int, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        elif m > 0:
            return f"{m}m {s}s"
        else:
            return f"{s}s"


class QueueManager(QObject):
    """
    Own one instance of this for the whole app (created in main.py,
    passed down to whichever pages need it). Pages should never touch
    _jobs directly — read via jobs_in_order()/get_job(), act via
    add_job()/cancel_job(), and react via the signals below.
    """

    job_added = Signal(str)     # job_id
    job_updated = Signal(str)   # job_id — status and/or percent changed
    job_removed = Signal(str)   # job_id

    def __init__(self):
        super().__init__()
        self._jobs: dict[str, BackupJob] = {}
        self._order: list[str] = []
        self._cancel_events: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._worker_running = False

        # Restore persistent jobs from database across app restarts/shutdowns
        self._restore_persistent_jobs()

    def _restore_persistent_jobs(self) -> None:
        try:
            persisted = load_persistent_queue_jobs()
            for p in persisted:
                # Never restore completed uploads — they're done, not pending
                if p["status"] == "done":
                    remove_persistent_queue_job(p["id"])
                    continue
                # If was running or paused, resume as paused so user has full control
                st = "paused" if p["status"] in ("paused", "archiving", "uploading") else p["status"]
                job = BackupJob(
                    id=p["id"],
                    movie_path=p["movie_path"],
                    movie_name=p["movie_name"],
                    destinations=p["destinations"],
                    status=st,
                    percent=p["percent"],
                    phase_percent=p["phase_percent"],
                    bytes_done=p["bytes_done"],
                    bytes_total=p["bytes_total"],
                    series_name=p["series_name"],
                    season_number=p["season_number"],
                    episode_number=p["episode_number"],
                    send_season_intro=p["send_season_intro"],
                    subtitle_paths=p.get("subtitle_paths", []),
                )
                self._jobs[job.id] = job
                self._order.append(job.id)
        except Exception as exc:
            logger.warning(f"Failed to restore persistent queue: {exc}")

    def _persist(self, job: BackupJob) -> None:
        try:
            save_persistent_queue_job(
                job_id=job.id,
                movie_path=job.movie_path,
                movie_name=job.movie_name,
                destinations=job.destinations,
                status=job.status,
                percent=job.percent,
                phase_percent=job.phase_percent,
                bytes_done=job.bytes_done,
                bytes_total=job.bytes_total,
                series_name=job.series_name,
                season_number=job.season_number,
                episode_number=job.episode_number,
                send_season_intro=job.send_season_intro,
                subtitle_paths=job.subtitle_paths,
            )
        except Exception as exc:
            logger.warning(f"Failed to persist queue job {job.id}: {exc}")

    # ---------- Public API ----------

    def jobs_in_order(self) -> list[BackupJob]:
        with self._lock:
            return [self._jobs[jid] for jid in self._order if jid in self._jobs]

    def get_job(self, job_id: str) -> BackupJob | None:
        return self._jobs.get(job_id)

    def get_active_job(self) -> BackupJob | None:
        """The single job currently archiving or uploading, if any —
        the queue processes strictly one at a time, so there's never
        more than one of these."""
        for job in self.jobs_in_order():
            if job.status in ("archiving", "uploading"):
                return job
        return None

    def add_job(self, movie_path: str, movie_name: str, destinations: list[str], subtitle_paths: list[str] | None = None) -> str:
        job_id = str(uuid.uuid4())
        job = BackupJob(
            id=job_id, movie_path=movie_path, movie_name=movie_name,
            destinations=list(destinations), subtitle_paths=list(subtitle_paths or [])
        )
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
        self._persist(job)
        self.job_added.emit(job_id)
        self._ensure_worker()
        return job_id

    def add_series_season(
        self, series_name: str, season_number: int,
        episodes: list, destinations: list[str],
    ) -> list[str]:
        job_ids = []
        for index, episode in enumerate(episodes):
            job_id = str(uuid.uuid4())
            job = BackupJob(
                id=job_id, movie_path=episode.path, movie_name=episode.filename,
                destinations=list(destinations),
                series_name=series_name, season_number=season_number,
                episode_number=episode.episode,
                send_season_intro=(index == 0),
            )
            with self._lock:
                self._jobs[job_id] = job
                self._order.append(job_id)
            self._persist(job)
            self.job_added.emit(job_id)
            job_ids.append(job_id)
        self._ensure_worker()
        return job_ids

    def pause_job(self, job_id: str) -> None:
        """Pauses a running or queued job. Upload parts already landed on Telegram remain saved."""
        event = self._cancel_events.get(job_id)
        if event:
            event.set()

        job = self._jobs.get(job_id)
        if job and job.status in ("queued", "archiving", "uploading"):
            job.status = "paused"
            job.upload_speed_bps = 0.0
            self._persist(job)
            self.job_updated.emit(job_id)

    def resume_job(self, job_id: str) -> None:
        """Resumes a paused or failed job."""
        job = self._jobs.get(job_id)
        if not job:
            return
        if job.status == "failed":
            self.retry_job(job_id)
            return
        if job.status != "paused":
            return
        job.status = "queued"
        job.upload_speed_bps = 0.0
        job.error = None
        self._persist(job)
        self.job_updated.emit(job_id)
        self._ensure_worker()

    def cancel_job(self, job_id: str) -> None:
        """Stops a running job mid-flight, or removes one that hasn't started yet."""
        event = self._cancel_events.get(job_id)
        if event:
            event.set()

        job = self._jobs.get(job_id)
        if job:
            with self._lock:
                if job_id in self._order:
                    self._order.remove(job_id)
                self._jobs.pop(job_id, None)
            remove_persistent_queue_job(job_id)
            self.job_removed.emit(job_id)

    def retry_job(self, job_id: str) -> None:
        """Re-queues a failed job from the top."""
        job = self._jobs.get(job_id)
        if not job or job.status != "failed":
            return
        job.status = "queued"
        job.percent = 0
        job.phase_percent = 0
        job.bytes_done = 0
        job.bytes_total = 0
        job.upload_speed_bps = 0.0
        job.error = None
        job.backup_ids = {}
        job.upload_start_time = None
        job.upload_end_time = None
        self._persist(job)
        self.job_updated.emit(job_id)
        self._ensure_worker()

    def clear_failed_jobs(self) -> None:
        """Removes all failed and done (uploaded) jobs from the queue, keeping only active, queued, and paused jobs."""
        with self._lock:
            clearable_ids = [
                jid for jid in self._order
                if self._jobs.get(jid) and self._jobs[jid].status in ("failed", "done")
            ]
            for jid in clearable_ids:
                self._order.remove(jid)
                self._jobs.pop(jid, None)
                remove_persistent_queue_job(jid)
        for jid in clearable_ids:
            self.job_removed.emit(jid)

    # ---------- Worker thread ----------

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker_running:
                return
            self._worker_running = True
        threading.Thread(target=self._process_loop, daemon=True).start()

    def _next_queued_job(self) -> BackupJob | None:
        with self._lock:
            for job_id in self._order:
                job = self._jobs.get(job_id)
                if job and job.status == "queued":
                    return job
        return None

    def _process_loop(self) -> None:
        while True:
            job = self._next_queued_job()
            if job is None:
                with self._lock:
                    self._worker_running = False
                return
            self._run_job(job)

    def _run_job(self, job: BackupJob) -> None:
        cancel_event = threading.Event()
        self._cancel_events[job.id] = cancel_event

        job.status = "archiving"
        job.percent = 0
        job.phase_percent = 0
        job.bytes_done = 0
        job.bytes_total = os.path.getsize(job.movie_path) if os.path.isfile(job.movie_path) else 0
        job.upload_speed_bps = 0.0
        self.job_updated.emit(job.id)

        def on_archive_progress(pct):
            job.percent = int(pct * 0.5)  # archiving is the first half of the bar
            job.phase_percent = pct       # raw phase progress, resets to 0 when upload starts
            self.job_updated.emit(job.id)

        try:
            outcome = run_archive_job(
                job.movie_path,
                progress_callback=on_archive_progress,
                cancel_event=cancel_event,
                subtitle_paths=job.subtitle_paths,
            )
        except Exception as exc:
            logger.exception(f"Archiving crashed for {job.movie_path}")
            self._fail(job, str(exc))
            return

        if not outcome.result.success:
            self._fail(job, outcome.result.error_message or "Archiving failed.")
            return

        volumes = outcome.result.archive_volumes
        total_size = sum(os.path.getsize(v) for v in volumes if os.path.isfile(v))

        # One DB record per destination — same archive, tracked independently.
        # Series episodes go to series_backups (with season/episode numbers
        # for grouping), everything else goes to movies_backups.
        is_series = job.series_name is not None
        for dest_name in job.destinations:
            if is_series:
                bid = record_series_backup(
                    series_name=job.series_name, season_number=job.season_number,
                    episode_number=job.episode_number, episode_name=job.movie_name,
                    episode_path=job.movie_path,
                    archive_volumes=volumes, password=outcome.password,
                    compression_level=outcome.compression_level,
                    split_volume_size_mb=outcome.split_volume_size_mb,
                    total_archive_size_bytes=total_size, destination=dest_name,
                    status="archived",
                )
            else:
                bid = record_movie_backup(
                    movie_path=job.movie_path, movie_name=job.movie_name,
                    archive_volumes=volumes, password=outcome.password,
                    compression_level=outcome.compression_level,
                    split_volume_size_mb=outcome.split_volume_size_mb,
                    total_archive_size_bytes=total_size, destination=dest_name,
                    status="archived",
                )
            job.backup_ids[dest_name] = bid

        record_table = "series_backups" if is_series else "movies_backups"

        job.status = "uploading"
        job.upload_start_time = time.time()
        job.upload_end_time = None
        job.percent = 50
        job.phase_percent = 0   # reset — this is a new phase, ring starts fresh
        job.bytes_done = 0
        job.bytes_total = sum(os.path.getsize(v) for v in volumes if os.path.isfile(v))
        self._speed_tracker = {"t": time.time(), "bytes": 0}
        self.job_updated.emit(job.id)

        def on_upload_progress(pct, bytes_done, bytes_total):
            job.percent = 50 + int(pct * 0.5)  # upload is the second half
            job.phase_percent = pct
            job.bytes_done = bytes_done
            job.bytes_total = bytes_total

            now = time.time()
            dt = now - self._speed_tracker["t"]
            if dt >= 0.25:  # max 4Hz UI update rate to prevent main thread freeze
                delta_bytes = bytes_done - self._speed_tracker["bytes"]
                job.upload_speed_bps = max(0.0, delta_bytes / dt)
                self._speed_tracker = {"t": now, "bytes": bytes_done}
                self.job_updated.emit(job.id)

        try:
            results = asyncio.run(
                self._upload_all(job, volumes, on_upload_progress, cancel_event)
            )
        except UploadCancelled:
            job.upload_end_time = time.time()
            self._fail(job, "Cancelled.", table=record_table)
            return
        except TelegramNotConfiguredError as exc:
            job.upload_end_time = time.time()
            self._fail(job, str(exc), table=record_table)
            return
        except Exception as exc:
            logger.exception(f"Upload failed for {job.movie_path}")
            job.upload_end_time = time.time()
            self._fail(job, f"Upload failed: {exc}", table=record_table)
            return

        all_success = True
        error_parts = []
        for dest_name, (success, payload) in results.items():
            bid = job.backup_ids.get(dest_name)
            if success:
                if bid:
                    update_status(bid, "backed_up", telegram_message_ids=[str(m) for m in payload], table=record_table)
            else:
                all_success = False
                error_parts.append(f"{dest_name}: {payload}")
                if bid:
                    update_status(bid, "failed", table=record_table)

        job.upload_end_time = time.time()
        if all_success:
            job.status = "done"
            job.percent = 100
            job.phase_percent = 100
            job.upload_speed_bps = 0.0
            job.error = None
            remove_persistent_queue_job(job.id)
            config = load_config()
            if config.get("delete_archive_after_upload", True):
                self._delete_archive_files(volumes)
        else:
            job.status = "failed"
            job.upload_speed_bps = 0.0
            job.error = "; ".join(error_parts)
            self._persist(job)

        self.job_updated.emit(job.id)

    def _fail(self, job: BackupJob, message: str, table: str = "movies_backups") -> None:
        if job.status != "paused":
            job.status = "failed"
            if job.upload_start_time and not job.upload_end_time:
                job.upload_end_time = time.time()
            job.error = message
            for bid in job.backup_ids.values():
                update_status(bid, "failed", table=table)
        job.upload_speed_bps = 0.0
        self._persist(job)
        self.job_updated.emit(job.id)

    def _delete_archive_files(self, volume_paths: list[str]) -> None:
        """Called only once every destination has confirmed a successful
        upload — Telegram is the real backup at that point, so there's
        no reason to keep the local .7z taking up disk space."""
        for path in volume_paths:
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError as exc:
                logger.warning(f"Couldn't delete archive file after upload: {path} ({exc})")

    async def _upload_all(self, job: BackupJob, volumes: list[str], progress_callback, cancel_event) -> dict:
        """
        Uploads to every destination, returning {destination_name: (success, message_ids_or_error)}.
        First destination is a real upload; the rest are forwarded from
        it (same file, no re-upload) unless that fails, in which case
        each destination attempts its own real upload as a fallback.
        """
        client = get_client()
        try:
            await asyncio.wait_for(client.connect(), timeout=CONNECT_TIMEOUT)
        except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
            raise RuntimeError(
                f"Couldn't connect to Telegram servers (Connection Reset / Timeout). "
                f"Your ISP, router, or local Windows firewall is blocking or resetting Telegram's IP address. "
                f"Try enabling a VPN (e.g., Cloudflare WARP) or SOCKS5 proxy in Settings."
            ) from exc

        try:
            if not await client.is_user_authorized():
                raise RuntimeError(
                    "Telegram session isn't authorized — add it again from the Backups tab."
                )

            results = {}
            destinations = job.destinations
            count = len(destinations)
            source_entity = None
            source_message_ids = None
            total_bytes = sum(os.path.getsize(v) for v in volumes if os.path.isfile(v))

            for i, dest_name in enumerate(destinations):
                def scoped_progress(pct, bytes_done, bytes_total, i=i):
                    if progress_callback:
                        overall_pct = int(((i + pct / 100) / count) * 100)
                        progress_callback(overall_pct, bytes_done, bytes_total)

                try:
                    destination = get_destination_by_name(dest_name)
                    channel_id = destination.telegram_channel_id if destination else None
                    if not channel_id:
                        raise RuntimeError(f"No configured channel for '{dest_name}' — check the Backups tab.")

                    try:
                        entity = await asyncio.wait_for(client.get_entity(channel_id), timeout=RESOLVE_TIMEOUT)
                    except asyncio.TimeoutError:
                        raise RuntimeError(f"Couldn't resolve '{dest_name}' after {RESOLVE_TIMEOUT:.0f}s.")

                    if job.send_season_intro and job.series_name and job.season_label:
                        await self._send_season_intro(client, entity, dest_name, job.series_name, job.season_label)

                    if source_entity is None:
                        message_ids = await upload_movie(
                            client, entity, volumes, caption_prefix=job.movie_name,
                            progress_callback=scoped_progress, cancel_event=cancel_event,
                        )
                        source_entity = entity
                        source_message_ids = message_ids
                        results[dest_name] = (True, message_ids)
                    else:
                        forwarded_ids = await forward_movie(client, source_entity, entity, source_message_ids)
                        results[dest_name] = (True, forwarded_ids)
                        scoped_progress(100, total_bytes, total_bytes)

                except UploadCancelled:
                    raise
                except Exception as exc:
                    results[dest_name] = (False, str(exc))

            if progress_callback:
                progress_callback(100, total_bytes, total_bytes)

            return results
        finally:
            await client.disconnect()

    async def _send_season_intro(self, client, entity, dest_name: str, series_name: str, season_label: str) -> None:
        """Sends the series name (only the first time ever, per
        destination) followed by the season label (every time)."""
        if not has_series_announcement(series_name, dest_name):
            name_msg = await client.send_message(entity, series_name)
            record_series_announcement(series_name, dest_name, str(name_msg.id))
        await client.send_message(entity, season_label)
