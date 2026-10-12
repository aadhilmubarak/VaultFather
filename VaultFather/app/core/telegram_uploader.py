"""
Resumable, chunked upload of a single archive volume to Telegram.

How resume actually works: Telegram's upload.saveBigFilePart keeps
uploaded parts server-side, associated with a file_id you generate
yourself, for a while after you stop sending — not forever, but long
enough to survive a dropped connection or an app restart a bit later.
So the trick is entirely local bookkeeping: remember the file_id and
how many parts already landed, and on resume, just keep sending from
the next part instead of starting over. This module owns that
bookkeeping (via database.upload_progress); it doesn't try to ask
Telegram what it already has, since that guarantee doesn't exist.

If the file_id has genuinely expired server-side (interrupted for too
long), the resumed upload will simply fail on the first send — the
caller should treat any failure here as "start this volume over" by
clearing the saved state and re-uploading from scratch.
"""

import math
import os
import threading
import asyncio
import mmap

from telethon import utils as telethon_utils
from telethon.helpers import generate_random_long
from telethon.tl.functions.upload import SaveBigFilePartRequest
from telethon.tl.types import InputFileBig

from app.core.database import get_upload_state, save_upload_state, clear_upload_state
from app.core.title_cleaner import clean_movie_title
from app.core.config import load_config


class UploadCancelled(Exception):
    pass


async def upload_volume(
    client,
    volume_path: str,
    progress_callback=None,
    cancel_event: threading.Event | None = None,
    part_timeout: float = 60.0,
) -> InputFileBig:
    """
    High-speed parallel chunked upload of an archive volume to Telegram.
    Uses 512KB chunks and concurrent MTProto pipelines to achieve maximum
    throughput on any network.
    """
    file_size = os.path.getsize(volume_path)
    filename = os.path.basename(volume_path)

    # 512KB is Telegram's optimal max part size
    part_size = 512 * 1024
    total_parts = math.ceil(file_size / part_size)

    # 20 parallel streams — safe ceiling before Telegram starts issuing FloodWaits.
    # cryptg (C-extension AES) makes this safe: without it, pure-Python encryption
    # at 16+ workers would saturate the CPU and stall the event loop.
    concurrency = 20

    state = get_upload_state(volume_path)
    if state and state["status"] == "in_progress" and state["total_parts"] == total_parts:
        file_id = int(state["telegram_file_id"])
        start_part = state["uploaded_parts"]
    else:
        file_id = generate_random_long()
        start_part = 0
        save_upload_state(volume_path, file_id, part_size, total_parts, 0, file_size)

    parts_to_upload = list(range(start_part, total_parts))
    if not parts_to_upload:
        clear_upload_state(volume_path)
        return InputFileBig(id=file_id, parts=total_parts, name=filename)

    semaphore = asyncio.Semaphore(concurrency)
    completed_parts_count = start_part
    lock = asyncio.Lock()

    with open(volume_path, "rb") as f:
        # Use memory-mapping for zero-overhead concurrent reads
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            async def upload_part(part_index: int):
                nonlocal completed_parts_count

                if cancel_event is not None and cancel_event.is_set():
                    raise UploadCancelled(f"Cancelled at part {part_index}/{total_parts}")

                offset = part_index * part_size
                chunk_len = min(part_size, file_size - offset)
                chunk = mm[offset : offset + chunk_len]

                async with semaphore:
                    if cancel_event is not None and cancel_event.is_set():
                        raise UploadCancelled(f"Cancelled at part {part_index}/{total_parts}")

                    # Retry each part up to 5 times.
                    # Never wrap in asyncio.wait_for — Telethon needs time to
                    # internally reconnect when the server drops the connection;
                    # cancelling it prematurely was causing the "stalled" errors.
                    max_retries = 5
                    for attempt in range(max_retries):
                        try:
                            await client(SaveBigFilePartRequest(
                                file_id=file_id,
                                file_part=part_index,
                                file_total_parts=total_parts,
                                bytes=chunk,
                            ))
                            break  # sent successfully
                        except UploadCancelled:
                            raise
                        except Exception as exc:
                            if attempt == max_retries - 1:
                                raise RuntimeError(
                                    f"Part {part_index}/{total_parts} failed after "
                                    f"{max_retries} attempts: {exc}"
                                ) from exc
                            await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s

                async with lock:
                    completed_parts_count += 1
                    save_upload_state(volume_path, file_id, part_size, total_parts, completed_parts_count, file_size)

                    if progress_callback:
                        bytes_done = min(completed_parts_count * part_size, file_size)
                        progress_callback(int(completed_parts_count / total_parts * 100), bytes_done, file_size)

            BATCH = 64
            for i in range(0, len(parts_to_upload), BATCH):
                batch = parts_to_upload[i : i + BATCH]
                await asyncio.gather(*[upload_part(idx) for idx in batch])

        finally:
            mm.close()

    clear_upload_state(volume_path)
    return InputFileBig(id=file_id, parts=total_parts, name=filename)


async def upload_movie(
    client,
    channel_entity,
    volume_paths: list[str],
    caption_prefix: str,
    progress_callback=None,
    cancel_event: threading.Event | None = None,
) -> list[int]:
    """
    Uploads every volume of a (possibly split) movie archive in order,
    each as its own captionless file message, then sends one separate
    follow-up text message with just the clean movie title and year
    (release tags, resolution, extension all stripped) — two distinct
    messages rather than the name baked into the file's caption.

    Returns every message ID in order (all volumes, then the name
    message) — this is what gets stored as telegram_message_ids.

    progress_callback receives (overall_percent, bytes_done, bytes_total)
    across all volumes combined, not just the current one — bytes_total
    is the sum of every volume's size, known up front, so a real
    transfer speed can be computed from consecutive callbacks.
    """
    message_ids: list[int] = []
    volume_count = len(volume_paths)
    bytes_total_all = sum(os.path.getsize(v) for v in volume_paths)
    bytes_done_before_volume = 0

    for i, volume_path in enumerate(volume_paths):
        def per_volume_progress(pct, bytes_done, bytes_total, i=i, base=bytes_done_before_volume):
            if progress_callback:
                overall_pct = int(((i + pct / 100) / volume_count) * 100)
                progress_callback(overall_pct, base + bytes_done, bytes_total_all)

        input_file = await upload_volume(
            client, volume_path,
            progress_callback=per_volume_progress,
            cancel_event=cancel_event,
        )
        bytes_done_before_volume += os.path.getsize(volume_path)

        message = await client.send_file(channel_entity, file=input_file, force_document=True)
        message_ids.append(message.id)

    clean_title = clean_movie_title(caption_prefix)
    name_message = await client.send_message(channel_entity, clean_title)
    message_ids.append(name_message.id)

    if progress_callback:
        progress_callback(100, bytes_total_all, bytes_total_all)

    return message_ids


async def forward_movie(client, source_entity, target_entity, message_ids: list[int]) -> list[int]:
    """
    Duplicates an already-uploaded movie's messages into another channel
    via Telegram's native forward — Telegram copies the existing file
    reference server-side rather than re-sending the bytes, so this is
    fast regardless of the movie's size. Used for every destination
    after the first when a movie is backed up to more than one channel.
    """
    messages = await client.forward_messages(target_entity, message_ids, from_peer=source_entity)
    if not isinstance(messages, list):
        messages = [messages]
    return [m.id for m in messages]
