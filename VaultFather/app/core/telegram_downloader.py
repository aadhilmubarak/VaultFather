"""
Telegram Cloud Downloader & Streamer:
Downloads split 7z volume parts from Telegram channel messages,
assembles and extracts the movie with the stored password for seamless playback.
"""

import os
import shutil
import asyncio
import threading
from pathlib import Path

from telethon.tl.types import MessageMediaDocument
from app.core.telegram_client import get_client
from app.core.archiver import get_seven_zip_path
from app.core.logger import get_logger

logger = get_logger()
RESTORE_TEMP_DIR = Path.home() / ".vaultfather" / "cloud_stream_cache"


async def download_message_media(client, channel_id: int, message_id: int, target_path: str, progress_callback=None) -> str:
    """Downloads media document from a specific Telegram message."""
    entity = await client.get_entity(channel_id)
    message = await client.get_messages(entity, ids=message_id)
    if not message or not message.media:
        raise RuntimeError(f"Message {message_id} does not contain media on Telegram.")

    Path(target_path).parent.mkdir(parents=True, exist_ok=True)

    def scoped_progress(current, total):
        if progress_callback and total:
            progress_callback(int(current / total * 100), current, total)

    await client.download_media(message, file=target_path, progress_callback=scoped_progress)
    return target_path


def restore_and_extract_movie(
    channel_id: int,
    message_ids: list[str],
    password: str,
    output_dir: str | None = None,
    progress_callback=None,
    cancel_event: threading.Event | None = None,
) -> str:
    """
    Synchronous entrypoint: Downloads all volume parts from Telegram, extracts with 7-Zip,
    and returns the local file path of the extracted video file.
    """
    RESTORE_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    temp_job_dir = RESTORE_TEMP_DIR / f"job_{message_ids[0]}"
    temp_job_dir.mkdir(parents=True, exist_ok=True)

    async def _async_download_all():
        client = get_client()
        await client.connect()
        try:
            downloaded_files = []
            msg_count = len(message_ids)
            vol_idx = 0  # counts only volume files (skips caption-only messages)
            for list_idx, msg_id_str in enumerate(message_ids):
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("Download cancelled.")
                msg_id = int(msg_id_str)

                entity = await client.get_entity(channel_id)
                message = await client.get_messages(entity, ids=msg_id)

                # Skip messages that have no media (e.g. caption-only text messages)
                if not message or not message.media:
                    logger.info(f"Skipping message {msg_id} — no media attachment (caption/text only).")
                    continue

                # 7-Zip requires all volumes to share the same base name: archive.7z.001, archive.7z.002 …
                vol_idx += 1
                target_file = str(temp_job_dir / f"archive.7z.{vol_idx:03d}")

                def per_part_progress(pct, cur, total, i=list_idx):
                    if progress_callback:
                        overall = int(((i + pct / 100) / msg_count) * 70)  # first 70% = download phase
                        progress_callback(overall, f"Downloading volume {vol_idx}/{msg_count} ({pct}%)")

                Path(target_file).parent.mkdir(parents=True, exist_ok=True)

                def scoped_progress(current, total, _pct_fn=per_part_progress):
                    if total:
                        _pct_fn(int(current / total * 100), current, total)

                await client.download_media(message, file=target_file, progress_callback=scoped_progress)
                downloaded_files.append(target_file)

            return downloaded_files
        finally:
            await client.disconnect()

    # 1. Download volumes
    downloaded = asyncio.run(_async_download_all())
    if not downloaded:
        raise RuntimeError("No files downloaded.")

    if progress_callback:
        progress_callback(75, "Extracting video from encrypted archive...")

    # 2. Extract with 7-Zip
    seven_zip = get_seven_zip_path()
    if not seven_zip:
        raise RuntimeError("7-Zip executable not found.")

    first_volume = downloaded[0]
    extract_target = Path(output_dir) if output_dir else temp_job_dir / "extracted"
    extract_target.mkdir(parents=True, exist_ok=True)

    import subprocess
    import sys
    _run_kwargs: dict = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE, "text": True}
    if sys.platform.startswith("win"):
        _run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    cmd = [
        seven_zip, "x",
        f"-p{password}",
        f"-o{extract_target}",
        "-y",
        first_volume,
    ]
    res = subprocess.run(cmd, **_run_kwargs)
    if res.returncode != 0:
        raise RuntimeError(f"7-Zip extraction failed: {res.stderr or res.stdout}")

    # Find the extracted video file
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4v", ".ts", ".webm"}
    for root, _, files in os.walk(extract_target):
        for f in files:
            if Path(f).suffix.lower() in video_exts:
                if progress_callback:
                    progress_callback(100, "Ready to play")
                return str(Path(root) / f)

    raise RuntimeError("Extracted archive did not contain a recognized video file.")