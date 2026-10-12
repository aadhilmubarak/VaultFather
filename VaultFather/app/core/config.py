"""
Lightweight persistent config — a JSON file in the user's home directory.
Nothing fancy: the real Settings screen (Phase 6) will read/write through
this same module, so whatever gets set programmatically now will show up
there later instead of needing a migration.
"""

import json
import os
import shutil
import platform
from pathlib import Path

CONFIG_DIR = Path.home() / ".vaultfather"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS = {
    "seven_zip_path": None,       # None = auto-detect
    "archive_output_dir": None,   # None = alongside the source movie
    "password_mode": "random",    # "random" or "fixed"
    "fixed_password": "",
    "compression_level": "store", # "store" | "fast" | "normal" | "max"
    "split_volume_size_mb": 1800, # None/0 disables splitting
    "delete_archive_after_upload": True,  # free up local disk once every destination confirms success
    "last_movie_folder": None,    # remembered so you don't have to reselect it every launch
    "tmdb_api_key": None,          # free key from themoviedb.org, powers poster artwork
    "google_client_id": None,      # from Google Cloud Console, powers Drive backup
    "google_client_secret": None,
    "google_drive_connected_email": None,
    "google_drive_daily_backup": True,
    "last_drive_backup_date": None,   # "YYYY-MM-DD", so daily backup only runs once per day
    "telegram_api_id": None,
    "telegram_api_hash": None,
    "telegram_channel_id": None,      # numeric entity id — resolved once at login, reliable even if renamed
    "telegram_channel_title": None,   # display name only, for the UI
    "unwatched_channel_id": None,     # numeric entity id for Unwatched Wishlist channel
    "unwatched_channel_title": None,  # display title for Unwatched Wishlist channel
    "upload_concurrency": 8,          # number of parallel MTProto upload chunk streams (4 to 16)
    "telegram_movie_download_dir": None,  # destination folder for movies downloaded from Telegram cloud
}

# Maps the friendly Settings-screen labels to 7z's -mx switch.
COMPRESSION_LEVELS = {
    "store": "0",
    "fast": "1",
    "normal": "5",
    "max": "9",
}

# Common 7-Zip install locations on Windows, checked in order if the
# config doesn't specify a path and it's not on PATH.
WINDOWS_7Z_CANDIDATES = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
]


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def set_telegram_credentials(api_id: int, api_hash: str) -> None:
    """Saves your Telegram API credentials to the local config file.
    Called from the Settings screen once authenticated — never hardcoded into source."""
    config = load_config()
    config["telegram_api_id"] = api_id
    config["telegram_api_hash"] = api_hash
    save_config(config)


def get_configured_destinations() -> list[str]:
    """
    Real, currently-usable backup destinations — right now just the one
    Telegram channel set up, if any. Returns an
    empty list (not a placeholder) when nothing's configured yet, so
    the UI can show an honest "not set up" state instead of a fake option.
    """
    config = load_config()
    title = config.get("telegram_channel_title")
    return [title] if title else []


def get_seven_zip_path() -> str | None:
    """
    Resolves the 7z executable to use, in order:
    1. Explicit path saved in config
    2. 7z / 7z.exe on PATH
    3. Common Windows install locations
    Returns None if nothing is found.
    """
    config = load_config()
    configured = config.get("seven_zip_path")
    if configured and os.path.isfile(configured):
        return configured

    exe_name = "7z.exe" if platform.system() == "Windows" else "7z"
    on_path = shutil.which(exe_name) or shutil.which("7za")
    if on_path:
        return on_path

    if platform.system() == "Windows":
        for candidate in WINDOWS_7Z_CANDIDATES:
            if os.path.isfile(candidate):
                return candidate

    return None
