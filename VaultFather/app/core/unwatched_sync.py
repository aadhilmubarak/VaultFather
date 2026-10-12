"""
unwatched_sync.py
─────────────────
Fetches the message history from the user's connected Telegram "Unwatched"
wishlist channel, parses movie title + year from each text message, and
syncs the results into the local `unwatched_movies` SQLite table.

Called from the dashboard's UnwatchedMoviesCard in a background thread so
the UI never blocks.  The function is fully synchronous from the caller's
perspective (it runs its own asyncio event loop internally).

Title/year parsing strategy
────────────────────────────
Each Telegram message is expected to contain a line like:
    Movie Name (2024)
or just:
    Movie Name

We pull the LAST bracketed 4-digit number as the year, and everything
before it (stripped) as the title.  Lines that are too short, are purely
numeric, or contain only URLs are skipped.
"""

from __future__ import annotations

import asyncio
import re
import threading
from typing import Callable

from app.core.config import load_config
from app.core.database import add_unwatched_movie, clear_unwatched_movies
from app.core.telegram_client import get_client, TelegramNotConfiguredError

# Maximum messages to fetch from the channel (newest first).
_FETCH_LIMIT = 200

_YEAR_RE = re.compile(r"\((\d{4})\)")
_URL_RE = re.compile(r"https?://\S+")


def _parse_title_year(text: str) -> tuple[str, str | None] | None:
    """
    Extract (title, year) from a message string.

    Returns None if the line doesn't look like a movie entry.
    """
    # Strip URLs
    clean = _URL_RE.sub("", text).strip()
    if len(clean) < 3:
        return None

    # Find all year patterns like (2024)
    years = _YEAR_RE.findall(clean)
    if years:
        year = years[-1]
        # Title = everything before the last "(YYYY)" occurrence
        title = _YEAR_RE.sub("", clean).strip().strip("–-—:").strip()
    else:
        year = None
        title = clean.strip().strip("–-—:").strip()

    # Filter out garbage: purely numeric, too long, empty
    if not title or len(title) > 120 or title.isdigit():
        return None

    return title, year


async def _fetch_messages(channel_id: int) -> list[tuple[str, str | None]]:
    """Connect to Telegram and pull text messages from the given channel."""
    client = get_client()
    results: list[tuple[str, str | None]] = []
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return results

        async for msg in client.iter_messages(channel_id, limit=_FETCH_LIMIT):
            raw: str = msg.text or ""
            # Each message may contain multiple lines — parse each line
            for line in raw.splitlines():
                line = line.strip()
                parsed = _parse_title_year(line)
                if parsed:
                    results.append(parsed)
                    break  # take the first valid line per message
    finally:
        await client.disconnect()
    return results


def sync_unwatched_channel(
    on_done: Callable[[int], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> None:
    """
    Synchronously (blocking) sync the Telegram Unwatched channel into the DB.

    Designed to be called from a background QThread / threading.Thread so the
    PySide6 main thread is never blocked.

    Parameters
    ----------
    on_done  : called with the count of movies synced when finished
    on_error : called with an error message string if something goes wrong
    """
    config = load_config()
    channel_id = config.get("unwatched_channel_id")

    if not channel_id:
        if on_error:
            on_error("No Unwatched channel connected. Go to Settings → Telegram Unwatched Wishlist Channel.")
        return

    try:
        channel_id = int(channel_id)
    except (ValueError, TypeError):
        if on_error:
            on_error(f"Invalid channel ID stored: {channel_id!r}")
        return

    try:
        loop = asyncio.new_event_loop()
        movies = loop.run_until_complete(_fetch_messages(channel_id))
        loop.close()
    except TelegramNotConfiguredError as exc:
        if on_error:
            on_error(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        if on_error:
            on_error(f"Telegram error: {exc}")
        return

    # Deduplicate by (title_lower, year) keeping insertion order
    seen: set[tuple[str, str | None]] = set()
    unique: list[tuple[str, str | None]] = []
    for title, year in movies:
        key = (title.lower(), year)
        if key not in seen:
            seen.add(key)
            unique.append((title, year))

    # Wipe and repopulate
    clear_unwatched_movies()
    for title, year in unique:
        add_unwatched_movie(title, year)

    if on_done:
        on_done(len(unique))


def sync_unwatched_channel_async(
    on_done: Callable[[int], None] | None = None,
    on_error: Callable[[str], None] | None = None,
) -> threading.Thread:
    """
    Fire-and-forget version: runs sync_unwatched_channel in a daemon thread.

    Returns the Thread so the caller can join() if needed.
    """
    t = threading.Thread(
        target=sync_unwatched_channel,
        args=(on_done, on_error),
        daemon=True,
        name="unwatched-tg-sync",
    )
    t.start()
    return t
