"""
Local backup database — SQLite, one file at ~/.vaultfather/vaultfather.db.

This is the foundation for Backup History, Dashboard stats, Movie Backup
Details, and Excel export in later phases, so it's built as a real,
durable store now rather than a throwaway JSON file — the one thing on
this list that genuinely needs to survive and be queryable (especially
the password, which is the only way back into an archive).
"""

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path.home() / ".vaultfather" / "vaultfather.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_path TEXT NOT NULL,
    movie_name TEXT NOT NULL,
    archive_volumes TEXT NOT NULL,   -- JSON list of file paths
    password TEXT NOT NULL,
    compression_level TEXT NOT NULL,
    split_volume_size_mb INTEGER,
    total_archive_size_bytes INTEGER,
    destination TEXT,                -- e.g. "My Movie Archive" (Telegram channel)
    telegram_message_ids TEXT,       -- JSON list, filled in once uploaded
    status TEXT NOT NULL,            -- 'archived' | 'uploading' | 'backed_up' | 'failed'
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS series_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_name TEXT NOT NULL,
    season_number INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,
    episode_name TEXT NOT NULL,
    episode_path TEXT NOT NULL,
    archive_volumes TEXT NOT NULL,   -- JSON list of file paths
    password TEXT NOT NULL,
    compression_level TEXT NOT NULL,
    split_volume_size_mb INTEGER,
    total_archive_size_bytes INTEGER,
    destination TEXT,
    telegram_message_ids TEXT,       -- JSON list — this episode's own message link(s)
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS upload_progress (
    volume_path TEXT PRIMARY KEY,
    telegram_file_id TEXT NOT NULL,   -- Telegram's per-upload file id (stored as text; can exceed 32-bit)
    part_size_bytes INTEGER NOT NULL,
    total_parts INTEGER NOT NULL,
    uploaded_parts INTEGER NOT NULL,  -- next part index still to send
    file_size_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,             -- 'in_progress' | 'complete'
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS destinations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,               -- 'telegram' for now; 'mega' etc. later
    name TEXT NOT NULL,               -- display name, e.g. the channel title
    telegram_channel_id INTEGER,      -- resolvable Telegram entity id
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS series_announcements (
    series_name TEXT NOT NULL,
    destination TEXT NOT NULL,
    message_id TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (series_name, destination)
);

CREATE TABLE IF NOT EXISTS playback_history (
    movie_key TEXT PRIMARY KEY,
    position_seconds REAL NOT NULL,
    duration_seconds REAL NOT NULL,
    audio_track INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS unwatched_movies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    year TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS persistent_queue (
    id TEXT PRIMARY KEY,
    movie_path TEXT NOT NULL,
    movie_name TEXT NOT NULL,
    destinations TEXT NOT NULL,       -- JSON list
    status TEXT NOT NULL,             -- 'queued' | 'paused' | 'archiving' | 'uploading'
    percent INTEGER NOT NULL,
    phase_percent INTEGER NOT NULL,
    bytes_done INTEGER NOT NULL,
    bytes_total INTEGER NOT NULL,
    series_name TEXT,
    season_number INTEGER,
    episode_number INTEGER,
    send_season_intro INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
"""


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE playback_history ADD COLUMN audio_track INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE persistent_queue ADD COLUMN subtitle_paths TEXT")
        except sqlite3.OperationalError:
            pass
        # Ensure Unwatched wishlist channels are purged from the backup destinations table
        try:
            conn.execute("DELETE FROM destinations WHERE LOWER(name) LIKE '%unwatched%'")
        except Exception:
            pass



@dataclass
class MovieBackupRecord:
    id: int
    movie_path: str
    movie_name: str
    archive_volumes: list[str]
    password: str
    compression_level: str
    split_volume_size_mb: int | None
    total_archive_size_bytes: int
    destination: str | None
    telegram_message_ids: list[str]
    status: str
    created_at: str

    @staticmethod
    def _from_row(row: sqlite3.Row) -> "MovieBackupRecord":
        return MovieBackupRecord(
            id=row["id"],
            movie_path=row["movie_path"],
            movie_name=row["movie_name"],
            archive_volumes=json.loads(row["archive_volumes"]),
            password=row["password"],
            compression_level=row["compression_level"],
            split_volume_size_mb=row["split_volume_size_mb"],
            total_archive_size_bytes=row["total_archive_size_bytes"],
            destination=row["destination"],
            telegram_message_ids=json.loads(row["telegram_message_ids"] or "[]"),
            status=row["status"],
            created_at=row["created_at"],
        )


# Backward-compatible alias — most of the app refers to this as "BackupRecord".
BackupRecord = MovieBackupRecord


@dataclass
class SeriesBackupRecord:
    id: int
    series_name: str
    season_number: int
    episode_number: int
    episode_name: str
    episode_path: str
    archive_volumes: list[str]
    password: str
    compression_level: str
    split_volume_size_mb: int | None
    total_archive_size_bytes: int
    destination: str | None
    telegram_message_ids: list[str]
    status: str
    created_at: str

    @staticmethod
    def _from_row(row: sqlite3.Row) -> "SeriesBackupRecord":
        return SeriesBackupRecord(
            id=row["id"],
            series_name=row["series_name"],
            season_number=row["season_number"],
            episode_number=row["episode_number"],
            episode_name=row["episode_name"],
            episode_path=row["episode_path"],
            archive_volumes=json.loads(row["archive_volumes"]),
            password=row["password"],
            compression_level=row["compression_level"],
            split_volume_size_mb=row["split_volume_size_mb"],
            total_archive_size_bytes=row["total_archive_size_bytes"],
            destination=row["destination"],
            telegram_message_ids=json.loads(row["telegram_message_ids"] or "[]"),
            status=row["status"],
            created_at=row["created_at"],
        )


def record_movie_backup(
    movie_path: str,
    movie_name: str,
    archive_volumes: list[str],
    password: str,
    compression_level: str,
    split_volume_size_mb: int | None,
    total_archive_size_bytes: int,
    destination: str | None = None,
    status: str = "archived",
) -> int:
    """Inserts a new movie backup record and returns its id."""
    init_db()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO movies_backups (
                movie_path, movie_name, archive_volumes, password,
                compression_level, split_volume_size_mb,
                total_archive_size_bytes, destination,
                telegram_message_ids, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                movie_path, movie_name, json.dumps(archive_volumes), password,
                compression_level, split_volume_size_mb,
                total_archive_size_bytes, destination,
                json.dumps([]), status, datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cursor.lastrowid


# Backward-compatible alias.
record_backup = record_movie_backup


def record_series_backup(
    series_name: str,
    season_number: int,
    episode_number: int,
    episode_name: str,
    episode_path: str,
    archive_volumes: list[str],
    password: str,
    compression_level: str,
    split_volume_size_mb: int | None,
    total_archive_size_bytes: int,
    destination: str | None = None,
    status: str = "archived",
) -> int:
    """Inserts a new series episode backup record and returns its id."""
    init_db()
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO series_backups (
                series_name, season_number, episode_number, episode_name, episode_path,
                archive_volumes, password, compression_level, split_volume_size_mb,
                total_archive_size_bytes, destination, telegram_message_ids, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                series_name, season_number, episode_number, episode_name, episode_path,
                json.dumps(archive_volumes), password, compression_level, split_volume_size_mb,
                total_archive_size_bytes, destination, json.dumps([]), status,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cursor.lastrowid


def update_status(backup_id: int, status: str, telegram_message_ids: list[str] | None = None,
                   table: str = "movies_backups") -> None:
    init_db()
    with _connect() as conn:
        if telegram_message_ids is not None:
            conn.execute(
                f"UPDATE {table} SET status = ?, telegram_message_ids = ? WHERE id = ?",
                (status, json.dumps(telegram_message_ids), backup_id),
            )
        else:
            conn.execute(f"UPDATE {table} SET status = ? WHERE id = ?", (status, backup_id))


def get_latest_backup_for_movie(movie_path: str) -> MovieBackupRecord | None:
    """Used for duplicate-backup detection — most recent record for this exact file path."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM movies_backups WHERE movie_path = ? ORDER BY created_at DESC LIMIT 1",
            (movie_path,),
        ).fetchone()
        return MovieBackupRecord._from_row(row) if row else None


def list_movie_backups() -> list[MovieBackupRecord]:
    """Sorted alphabetically by movie name, so a franchise's entries land next to each other."""
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM movies_backups ORDER BY movie_name COLLATE NOCASE ASC").fetchall()
        return [MovieBackupRecord._from_row(row) for row in rows]


# Backward-compatible alias — existing callers (Dashboard stats, etc.) use this name.
def list_backups() -> list[MovieBackupRecord]:
    return list_movie_backups()


def list_series_backups() -> list[SeriesBackupRecord]:
    """Sorted by series, then season, then episode — reproduces the same
    grouping used when queueing and when messaging Telegram."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """SELECT * FROM series_backups
               ORDER BY series_name COLLATE NOCASE ASC, season_number ASC, episode_number ASC"""
        ).fetchall()
        return [SeriesBackupRecord._from_row(row) for row in rows]


# ---------- Upload progress (for resumable uploads) ----------

def get_upload_state(volume_path: str) -> dict | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM upload_progress WHERE volume_path = ?", (volume_path,)
        ).fetchone()
        return dict(row) if row else None


def save_upload_state(
    volume_path: str,
    telegram_file_id: int,
    part_size_bytes: int,
    total_parts: int,
    uploaded_parts: int,
    file_size_bytes: int,
    status: str = "in_progress",
) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO upload_progress (
                volume_path, telegram_file_id, part_size_bytes, total_parts,
                uploaded_parts, file_size_bytes, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(volume_path) DO UPDATE SET
                uploaded_parts = excluded.uploaded_parts,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                volume_path, str(telegram_file_id), part_size_bytes, total_parts,
                uploaded_parts, file_size_bytes, status,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def clear_upload_state(volume_path: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM upload_progress WHERE volume_path = ?", (volume_path,))


# ---------- Destinations (Backups tab) ----------

@dataclass
class Destination:
    id: int
    type: str
    name: str
    telegram_channel_id: int | None
    created_at: str


def add_destination(name: str, telegram_channel_id: int, dest_type: str = "telegram") -> int:
    init_db()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO destinations (type, name, telegram_channel_id, created_at) VALUES (?, ?, ?, ?)",
            (dest_type, name, telegram_channel_id, datetime.now(timezone.utc).isoformat()),
        )
        return cursor.lastrowid


def list_destinations() -> list[Destination]:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM destinations ORDER BY created_at ASC").fetchall()
        return [
            Destination(
                id=r["id"], type=r["type"], name=r["name"],
                telegram_channel_id=r["telegram_channel_id"], created_at=r["created_at"],
            )
            for r in rows
        ]


def get_destination_by_name(name: str) -> Destination | None:
    for dest in list_destinations():
        if dest.name == name:
            return dest
    return None


def remove_destination(destination_id: int) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM destinations WHERE id = ?", (destination_id,))


# ---------- Series announcements ----------
# Tracks whether a series' name has already been sent to a given
# destination, so backing up Season 2 later doesn't repeat "Game of
# Thrones" — only the season label goes out again.

def has_series_announcement(series_name: str, destination: str) -> bool:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM series_announcements WHERE series_name = ? AND destination = ?",
            (series_name, destination),
        ).fetchone()
        return row is not None


def record_series_announcement(series_name: str, destination: str, message_id: str | None = None) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO series_announcements (series_name, destination, message_id, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(series_name, destination) DO NOTHING
            """,
            (series_name, destination, message_id, datetime.now(timezone.utc).isoformat()),
        )


def migrate_legacy_single_channel() -> None:
    """
    Early versions stored one channel directly in config.json
    (telegram_channel_id/telegram_channel_title).
    Now that destinations live in their own table, pull that legacy
    value in as a real destination the first time this runs, so nobody's
    existing setup just silently disappears.
    """
    from app.core.config import load_config

    config = load_config()
    channel_id = config.get("telegram_channel_id")
    title = config.get("telegram_channel_title")
    if not channel_id or not title:
        return

    existing = get_destination_by_name(title)
    if existing:
        return

    add_destination(title, channel_id)


def clear_all_backup_history() -> None:
    """
    Wipes every backup record — movies, series episodes, series-name
    announcement memory, and any in-flight upload resume state. Does
    NOT touch destinations (channels) or config (passwords, api keys,
    etc.) — those are settings, not history.
    """
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM movies_backups")
        conn.execute("DELETE FROM series_backups")
        conn.execute("DELETE FROM series_announcements")
        conn.execute("DELETE FROM upload_progress")


def clear_failed_backups() -> tuple[int, int]:
    """
    Removes only the 'failed' records — the leftover noise from backups
    that never actually completed. Doesn't touch the real movie/episode
    file on disk (nothing here ever does), and doesn't touch successful
    or in-progress records, only failed ones — so Excel exports and the
    History tab aren't cluttered with attempts that never landed.
    Returns (movies_removed, episodes_removed).
    """
    init_db()
    with _connect() as conn:
        movie_count = conn.execute(
            "SELECT COUNT(*) FROM movies_backups WHERE status = 'failed'"
        ).fetchone()[0]
        series_count = conn.execute(
            "SELECT COUNT(*) FROM series_backups WHERE status = 'failed'"
        ).fetchone()[0]
        conn.execute("DELETE FROM movies_backups WHERE status = 'failed'")
        conn.execute("DELETE FROM series_backups WHERE status = 'failed'")
        return movie_count, series_count


def migrate_split_backup_tables() -> None:
    """
    Earlier versions stored every backup (movies and, briefly, episodes)
    in one combined 'backups' table. Now that movies and series live in
    their own tables, copy anything from the old table into
    movies_backups (everything backed up before the Series feature
    existed was a movie) and drop it, so existing history isn't lost.
    """
    init_db()
    with _connect() as conn:
        old_table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='backups'"
        ).fetchone()
        if not old_table_exists:
            return

        rows = conn.execute("SELECT * FROM backups").fetchall()
        for row in rows:
            conn.execute(
                """
                INSERT INTO movies_backups (
                    movie_path, movie_name, archive_volumes, password,
                    compression_level, split_volume_size_mb,
                    total_archive_size_bytes, destination,
                    telegram_message_ids, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["movie_path"], row["movie_name"], row["archive_volumes"], row["password"],
                    row["compression_level"], row["split_volume_size_mb"],
                    row["total_archive_size_bytes"], row["destination"],
                    row["telegram_message_ids"], row["status"], row["created_at"],
                ),
            )
        conn.execute("DROP TABLE backups")


def save_playback_position(movie_key: str, position_seconds: float, duration_seconds: float, audio_track: int = 0) -> None:
    """Saves or updates the user's playback position and active audio track for a movie."""
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO playback_history (movie_key, position_seconds, duration_seconds, audio_track, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(movie_key) DO UPDATE SET
                position_seconds = excluded.position_seconds,
                duration_seconds = excluded.duration_seconds,
                audio_track = excluded.audio_track,
                updated_at = excluded.updated_at
            """,
            (movie_key, position_seconds, duration_seconds, audio_track, datetime.now(timezone.utc).isoformat()),
        )


def get_playback_position(movie_key: str) -> tuple[float, float, int]:
    """Returns (position_seconds, duration_seconds, audio_track) or (0.0, 0.0, 0) if not found."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT position_seconds, duration_seconds, audio_track FROM playback_history WHERE movie_key = ?",
            (movie_key,),
        ).fetchone()
        if row:
            at = row["audio_track"] if "audio_track" in row.keys() and row["audio_track"] is not None else 0
            return float(row["position_seconds"]), float(row["duration_seconds"]), int(at)
        return 0.0, 0.0, 0


def list_playback_history() -> dict[str, tuple[float, float]]:
    """Returns a dict mapping movie_key -> (position_seconds, duration_seconds)."""
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT movie_key, position_seconds, duration_seconds FROM playback_history").fetchall()
        return {r["movie_key"]: (float(r["position_seconds"]), float(r["duration_seconds"])) for r in rows}


def get_last_viewed_movie() -> dict | None:
    """Returns the most recently played movie entry from playback_history."""
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT movie_key, position_seconds, duration_seconds, audio_track, updated_at
            FROM playback_history
            ORDER BY updated_at DESC LIMIT 1
            """
        ).fetchone()
        if row:
            at = row["audio_track"] if "audio_track" in row.keys() and row["audio_track"] is not None else 0
            return {
                "movie_path": row["movie_key"],
                "position_seconds": float(row["position_seconds"]),
                "duration_seconds": float(row["duration_seconds"]),
                "audio_track": int(at),
                "updated_at": row["updated_at"],
            }
        return None


def list_unwatched_movies() -> list[dict]:
    """Returns the list of unwatched movies from the Unwatched channel/vault."""
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, year FROM unwatched_movies ORDER BY id DESC"
        ).fetchall()
        return [{"id": r["id"], "title": r["title"], "year": r["year"]} for r in rows]


def add_unwatched_movie(title: str, year: str | None = None) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO unwatched_movies (title, year, created_at) VALUES (?, ?, ?)",
            (title, year, datetime.now(timezone.utc).isoformat()),
        )


def clear_unwatched_movies() -> None:
    """Wipes the local unwatched_movies table so it can be repopulated from Telegram."""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM unwatched_movies")


def delete_unwatched_movie(movie_id: int) -> None:
    """Remove a single movie from the unwatched wishlist by its DB id."""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM unwatched_movies WHERE id = ?", (movie_id,))


def delete_movie_backup(record_id: int) -> None:
    """Remove a single movie backup record from history by its DB id."""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM movies_backups WHERE id = ?", (record_id,))


def delete_series_backup(record_id: int) -> None:
    """Remove a single series episode backup record from history by its DB id."""
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM series_backups WHERE id = ?", (record_id,))

def save_persistent_queue_job(
    job_id: str, movie_path: str, movie_name: str, destinations: list[str],
    status: str, percent: int, phase_percent: int, bytes_done: int, bytes_total: int,
    series_name: str | None = None, season_number: int | None = None,
    episode_number: int | None = None, send_season_intro: bool = False,
    subtitle_paths: list[str] | None = None
) -> None:
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO persistent_queue (
                id, movie_path, movie_name, destinations, status,
                percent, phase_percent, bytes_done, bytes_total,
                series_name, season_number, episode_number, send_season_intro, created_at, subtitle_paths
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                status = excluded.status,
                percent = excluded.percent,
                phase_percent = excluded.phase_percent,
                bytes_done = excluded.bytes_done,
                bytes_total = excluded.bytes_total
            """,
            (
                job_id, movie_path, movie_name, json.dumps(destinations), status,
                percent, phase_percent, bytes_done, bytes_total,
                series_name, season_number, episode_number, int(send_season_intro),
                datetime.now(timezone.utc).isoformat(), json.dumps(subtitle_paths or [])
            )
        )


def remove_persistent_queue_job(job_id: str) -> None:
    init_db()
    with _connect() as conn:
        conn.execute("DELETE FROM persistent_queue WHERE id = ?", (job_id,))


def load_persistent_queue_jobs() -> list[dict]:
    init_db()
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM persistent_queue ORDER BY created_at ASC").fetchall()
        out = []
        for r in rows:
            # Handle old rows lacking subtitle_paths column
            subs_json = r["subtitle_paths"] if "subtitle_paths" in r.keys() else "[]"
            out.append({
                "id": r["id"],
                "movie_path": r["movie_path"],
                "movie_name": r["movie_name"],
                "destinations": json.loads(r["destinations"]),
                "status": r["status"],
                "percent": r["percent"],
                "phase_percent": r["phase_percent"],
                "bytes_done": r["bytes_done"],
                "bytes_total": r["bytes_total"],
                "series_name": r["series_name"],
                "season_number": r["season_number"],
                "episode_number": r["episode_number"],
                "send_season_intro": bool(r["send_season_intro"]),
                "subtitle_paths": json.loads(subs_json) if subs_json else [],
            })
        return out


