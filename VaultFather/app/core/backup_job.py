"""
Handles the archiving decisions in one place: what password to use and
how to split into volumes, per current Settings. Deliberately does NOT
write to the database anymore — now that one archive can be uploaded to
several destinations, the caller (QueueManager) creates one database
record per destination after archiving succeeds, since each destination
gets tracked independently (one channel's upload can fail while another
succeeds, and each keeps its own message IDs).
"""

import threading
from dataclasses import dataclass

from app.core.archiver import archive_movie, ArchiveResult
from app.core.config import load_config
from app.core.password import resolve_password


@dataclass
class ArchiveOutcome:
    result: ArchiveResult
    password: str
    compression_level: str
    split_volume_size_mb: int | None


def run_archive_job(
    movie_path: str,
    progress_callback=None,
    cancel_event: threading.Event | None = None,
    subtitle_paths: list[str] | None = None,
) -> ArchiveOutcome:
    """
    Resolves the password per current Settings (fixed or random) and
    archives with the configured compression level and split volume
    size. Returns the outcome (including the password used and the
    settings applied) so the caller can record it — once per destination.
    """
    config = load_config()
    password = resolve_password(config)
    compression_level = config.get("compression_level", "store")
    split_volume_size_mb = config.get("split_volume_size_mb")

    result = archive_movie(
        source_path=movie_path,
        password=password,
        output_dir=config.get("archive_output_dir"),
        compression_level=compression_level,
        split_volume_size_mb=split_volume_size_mb,
        progress_callback=progress_callback,
        cancel_event=cancel_event,
        subtitle_paths=subtitle_paths,
    )

    return ArchiveOutcome(
        result=result,
        password=password,
        compression_level=compression_level,
        split_volume_size_mb=split_volume_size_mb,
    )
