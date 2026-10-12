"""
Subtitle file detector for VaultFather.

Scans the same directory as a movie file and returns any subtitle files
whose base stem closely matches the movie's own stem. Matching is
intentionally liberal — any subtitle file whose stem *starts with* the
movie stem (case-insensitive) is included, so language-tagged variants
like "Interstellar.en.srt", "Interstellar.ara.srt" all match.
"""

import os
from pathlib import Path

SUBTITLE_EXTENSIONS = {
    ".srt", ".sub", ".ass", ".ssa", ".vtt",
    ".sbv", ".smi", ".sup", ".idx",
}


def detect_subtitles(movie_path: str) -> list[str]:
    """
    Returns a sorted list of absolute paths to subtitle files found
    in the same directory as *movie_path* that match its filename stem.
    Returns an empty list if none are found or if the directory is
    unreadable.
    """
    movie = Path(movie_path)
    if not movie.is_file():
        return []

    folder = movie.parent
    movie_stem = movie.stem.lower()

    results: list[str] = []
    try:
        for entry in folder.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in SUBTITLE_EXTENSIONS:
                continue
            # Match: subtitle stem starts with the movie stem (handles
            # language suffixes like ".en", ".ara", ".forced" etc.)
            if entry.stem.lower().startswith(movie_stem):
                results.append(str(entry))
    except OSError:
        return []

    return sorted(results)
