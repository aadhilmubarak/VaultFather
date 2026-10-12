"""
Detects TV episode files (SxxEyy naming) inside a folder and groups
them by series name, then by season — separate from scan_movies(),
which now excludes anything this recognizes as an episode so a movie
folder that also has a "Game of Thrones" subfolder doesn't show
individual episodes in the Movies list too.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.movie_scanner import VIDEO_EXTENSIONS, human_size

# Matches "Game.of.Thrones.S01E05...", "Game of Thrones - S1E5", etc.
# Group 1 = everything before the season/episode marker (the raw series name).
EPISODE_RE = re.compile(r"^(.*?)[.\s_\-]*[Ss](\d{1,2})[Ee](\d{1,3})", re.IGNORECASE)


@dataclass
class EpisodeFile:
    path: str
    filename: str
    series_name: str
    season: int
    episode: int
    size_bytes: int

    @property
    def size_human(self) -> str:
        return human_size(self.size_bytes)


def is_series_episode(filename: str) -> bool:
    return bool(EPISODE_RE.search(Path(filename).stem))


def _clean_series_name(raw: str) -> str:
    name = re.sub(r"[._]+", " ", raw)
    name = name.strip(" -")
    name = re.sub(r"\s{2,}", " ", name)
    return name or "Unknown Series"


def parse_episode(path: str) -> EpisodeFile | None:
    stem = Path(path).stem
    match = EPISODE_RE.search(stem)
    if not match:
        return None
    raw_name, season_str, episode_str = match.groups()
    try:
        size = os.path.getsize(path)
    except OSError:
        size = 0
    return EpisodeFile(
        path=path,
        filename=os.path.basename(path),
        series_name=_clean_series_name(raw_name),
        season=int(season_str),
        episode=int(episode_str),
        size_bytes=size,
    )


def scan_series(folder_path: str) -> dict[str, dict[int, list[EpisodeFile]]]:
    """
    Returns {series_name: {season_number: [EpisodeFile, ...]}}, episodes
    sorted by episode number within each season. Empty dict if the
    folder doesn't exist or nothing matches an episode pattern.
    """
    groups: dict[str, dict[int, list[EpisodeFile]]] = {}
    if not folder_path or not os.path.isdir(folder_path):
        return groups

    for root, _dirs, files in os.walk(folder_path):
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in VIDEO_EXTENSIONS:
                continue
            full_path = os.path.join(root, fname)
            episode = parse_episode(full_path)
            if episode is None:
                continue
            groups.setdefault(episode.series_name, {}).setdefault(episode.season, []).append(episode)

    for seasons in groups.values():
        for episodes in seasons.values():
            episodes.sort(key=lambda e: e.episode)

    return groups
