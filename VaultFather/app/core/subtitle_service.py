"""
Subtitle Management & Lossless Remuxing Service for VaultFather.

Features:
  1. OpenSubtitles 64-bit Movie Hash calculation (exact match as used by VLC / VLSub).
  2. Online subtitle search via OpenSubtitles REST API (Hash match first, query fallback).
  3. Automatic download and gzip decompression.
  4. 100% Lossless Remuxing via FFmpeg (Stream Copy - 0.00% video/audio quality loss).
  5. Soft-subtitles flagged as disabled/optional by default (matching VLC player behavior).
"""

import os
import sys
import gzip
import json
import struct
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable

from app.core.logger import get_logger
from app.core.title_cleaner import clean_movie_title, parse_movie_title_and_year

logger = get_logger()

USER_AGENT = "VLSub 0.10.2"
SEARCH_TIMEOUT = 10  # seconds


def get_ffmpeg_executable() -> str | None:
    """Finds a usable ffmpeg executable, checking bundled imageio-ffmpeg first."""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.isfile(exe):
            return exe
    except Exception:
        pass

    on_path = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if on_path and os.path.isfile(on_path):
        return on_path

    # Common Windows paths
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    return None


def compute_movie_hash(file_path: str) -> tuple[str, int]:
    """
    Computes OpenSubtitles 64-bit checksum hash over the first 64KB
    and last 64KB of the movie file plus its file size.
    Returns (hex_hash, file_size).
    """
    longlongformat = '<q'
    bytesize = struct.calcsize(longlongformat)

    if not os.path.isfile(file_path):
        return "", 0

    filesize = os.path.getsize(file_path)
    if filesize < 65536 * 2:
        return "", filesize

    hash_val = filesize
    with open(file_path, "rb") as f:
        # First 64 KB
        for _ in range(65536 // bytesize):
            buffer = f.read(bytesize)
            (l_val,) = struct.unpack(longlongformat, buffer)
            hash_val = (hash_val + l_val) & 0xFFFFFFFFFFFFFFFF

        # Last 64 KB
        f.seek(max(0, filesize - 65536), 0)
        for _ in range(65536 // bytesize):
            buffer = f.read(bytesize)
            (l_val,) = struct.unpack(longlongformat, buffer)
            hash_val = (hash_val + l_val) & 0xFFFFFFFFFFFFFFFF

    return "%016x" % hash_val, filesize


def search_subtitles_online(movie_path: str, query: str | None = None, language: str = "eng") -> list[dict]:
    """
    Searches online for subtitles for the specified movie.
    Prioritizes exact hash match (100% audio sync), then title query match.
    """
    results: list[dict] = []
    seen_ids = set()

    movie_hash, file_size = compute_movie_hash(movie_path)

    # 1. Exact Hash Search
    if movie_hash and file_size > 0:
        hash_url = (
            f"https://rest.opensubtitles.org/search/moviebytesize-{file_size}/"
            f"moviehash-{movie_hash}/sublanguageid-{language}"
        )
        try:
            req = urllib.request.Request(hash_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if isinstance(data, list):
                    for item in data:
                        sub_id = item.get("IDSubtitleFile") or item.get("SubFileName")
                        if sub_id not in seen_ids:
                            seen_ids.add(sub_id)
                            results.append({
                                "id": str(sub_id),
                                "name": item.get("SubFileName") or f"{Path(movie_path).stem}.srt",
                                "release": item.get("MovieReleaseName") or "",
                                "format": (item.get("SubFormat") or "srt").lower(),
                                "downloads": item.get("SubDownloadsCnt") or "0",
                                "rating": item.get("SubRating") or "0.0",
                                "is_hash_match": True,
                                "download_url": item.get("SubDownloadLink") or "",
                                "language": item.get("LanguageName") or language,
                            })
        except Exception as exc:
            logger.warning(f"Subtitle hash search failed: {exc}")

    # 2. Title Query Fallback (multi-candidate search for editions, cuts, etc.)
    from app.core.title_cleaner import get_search_candidate_titles, parse_movie_title_and_year

    queries_to_try: list[str] = []
    if query:
        queries_to_try.append(query)
    else:
        title, year = parse_movie_title_and_year(Path(movie_path).name)
        for q_t, q_y in get_search_candidate_titles(title, year):
            term = f"{q_t} {q_y}".strip() if q_y else q_t
            if term not in queries_to_try:
                queries_to_try.append(term)

    for search_term in queries_to_try[:4]:
        encoded_query = urllib.parse.quote(search_term.strip().lower())
        query_url = f"https://rest.opensubtitles.org/search/query-{encoded_query}/sublanguageid-{language}"
        try:
            req = urllib.request.Request(query_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=SEARCH_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if isinstance(data, list):
                    for item in data:
                        sub_id = item.get("IDSubtitleFile") or item.get("SubFileName")
                        if sub_id not in seen_ids:
                            seen_ids.add(sub_id)
                            results.append({
                                "id": str(sub_id),
                                "name": item.get("SubFileName") or "Subtitle.srt",
                                "release": item.get("MovieReleaseName") or "",
                                "format": (item.get("SubFormat") or "srt").lower(),
                                "downloads": item.get("SubDownloadsCnt") or "0",
                                "rating": item.get("SubRating") or "0.0",
                                "is_hash_match": False,
                                "download_url": item.get("SubDownloadLink") or "",
                                "language": item.get("LanguageName") or language,
                            })
        except Exception as exc:
            logger.warning(f"Subtitle title search failed for '{search_term}': {exc}")

    # Sort results: Hash matches first, then by downloads/rating
    def _sort_key(item):
        is_hash = 1 if item.get("is_hash_match") else 0
        try:
            dl = int(item.get("downloads", 0))
        except (ValueError, TypeError):
            dl = 0
        return (is_hash, dl)

    results.sort(key=_sort_key, reverse=True)
    return results


def download_subtitle_file(download_url: str, output_path: str) -> bool:
    """
    Downloads a subtitle file (typically gzipped from OpenSubtitles),
    decompresses it if needed, and writes clean subtitle text to output_path.
    """
    if not download_url:
        return False

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        req = urllib.request.Request(download_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_bytes = resp.read()

        # Check if gzip compressed (magic bytes \x1f\x8b)
        if raw_bytes.startswith(b"\x1f\x8b"):
            content = gzip.decompress(raw_bytes)
        else:
            content = raw_bytes

        # Write clean subtitle text
        with open(out_file, "wb") as f:
            f.write(content)

        return True
    except Exception as exc:
        logger.error(f"Failed to download subtitle from {download_url}: {exc}")
        return False


def remux_subtitle_lossless(
    movie_path: str,
    subtitle_path: str,
    language_code: str = "eng",
    progress_callback: Callable[[str], None] | None = None
) -> tuple[bool, str]:
    """
    Soft-muxes the subtitle into the movie container with 0.00% quality loss.
    - Video and audio streams are copied byte-for-byte (-c copy).
    - Subtitle stream is set as optional (disposition=0, disabled by default in VLC).
    - Preserves file format container (.mkv, .mp4, etc.).
    """
    ffmpeg_exe = get_ffmpeg_executable()
    if not ffmpeg_exe:
        return False, "FFmpeg binary could not be found for lossless remuxing."

    movie = Path(movie_path)
    sub = Path(subtitle_path)

    if not movie.is_file():
        return False, f"Movie file not found: {movie_path}"
    if not sub.is_file():
        return False, f"Subtitle file not found: {subtitle_path}"

    ext = movie.suffix.lower()
    temp_output = movie.parent / f".vf_remux_temp_{movie.stem}{ext}"

    if progress_callback:
        progress_callback("Remuxing streams (0% quality loss)...")

    # Determine subtitle codec based on container format
    if ext == ".mp4" or ext == ".m4v" or ext == ".mov":
        sub_codec = "mov_text"
    else:  # .mkv, .webm, etc.
        sub_codec = "srt"

    cmd = [
        ffmpeg_exe,
        "-i", str(movie),
        "-i", str(sub),
        "-map", "0",
        "-map", "1",
        "-c", "copy",
        "-c:s", sub_codec,
        "-metadata:s:s:0", f"language={language_code}",
        "-metadata:s:s:0", "title=VaultFather",
        "-disposition:s:0", "0",    # Disabled / optional by default
        str(temp_output),
        "-y"
    ]

    popen_kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        process = subprocess.Popen(cmd, **popen_kwargs)
        stdout, stderr = process.communicate()

        if process.returncode != 0 or not temp_output.is_file() or temp_output.stat().st_size == 0:
            if temp_output.is_file():
                temp_output.unlink(missing_ok=True)
            err_line = stderr.strip().splitlines()[-1] if stderr else "Unknown remux error"
            return False, f"Remux failed: {err_line}"

        # Safely swap the remuxed movie in place of the original
        backup_path = movie.parent / f".vf_orig_backup_{movie.name}"
        try:
            if backup_path.is_file():
                backup_path.unlink()
            os.replace(movie, backup_path)
            os.replace(temp_output, movie)
            if backup_path.is_file():
                backup_path.unlink()
        except Exception as swap_err:
            # If swap fails (e.g. file lock), restore original
            if backup_path.is_file() and not movie.is_file():
                os.replace(backup_path, movie)
            if temp_output.is_file():
                temp_output.unlink(missing_ok=True)
            return False, f"Could not replace video file (is it open in VLC?): {swap_err}"

        return True, "Subtitles embedded losslessly."
    except Exception as exc:
        if temp_output.is_file():
            temp_output.unlink(missing_ok=True)
        return False, str(exc)


def get_cached_subtitle_path(movie_path: str) -> str | None:
    """Finds existing companion subtitle for movie_path if present."""
    from app.core.subtitle_detector import detect_subtitles
    subs = detect_subtitles(movie_path)
    return subs[0] if subs else None


def fetch_and_save_subtitles(movie_path: str) -> str | None:
    """Auto-searches and downloads best-matching subtitle for movie_path."""
    movie = Path(movie_path)
    if not movie.is_file():
        return None

    results = search_subtitles_online(movie_path)
    if not results:
        return None

    top_sub = results[0]
    dl_url = top_sub.get("download_url")
    if not dl_url:
        return None

    fmt = top_sub.get("format", "srt")
    target_path = movie.parent / f"{movie.stem}.{fmt}"
    if download_subtitle_file(dl_url, str(target_path)):
        return str(target_path)
    return None