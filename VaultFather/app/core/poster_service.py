"""
Fetches movie/TV poster artwork from TMDb (themoviedb.org) and caches
it to disk, so it's only ever downloaded once per title. Requires a
free TMDb API key, set in Settings — with no key configured, or if a
lookup fails for any reason, this returns None and the UI shows a
placeholder rather than breaking.

Two on-disk markers per title, both in ~/.vaultfather/poster_cache/:
  {key}.jpg   the actual poster, once found
  {key}.miss  "already looked, nothing found" — so a title with no
              poster doesn't get re-queried against the API every
              single time the Movies tab is opened
"""

import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path

from app.core.config import load_config

CACHE_DIR = Path.home() / ".vaultfather" / "poster_cache"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"
REQUEST_TIMEOUT = 10


def _cache_key(title: str, year: str | None, media_type: str) -> str:
    raw = f"{media_type}:{title.strip().lower()}:{year or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cached_poster_path(title: str, year: str | None, media_type: str) -> str | None:
    """Synchronous, disk-only check — never touches the network. Use
    this from the UI thread to show an already-cached poster instantly."""
    key = _cache_key(title, year, media_type)
    path = CACHE_DIR / f"{key}.jpg"
    return str(path) if path.is_file() else None


def fetch_poster(title: str, year: str | None, media_type: str = "movie") -> str | None:
    """
    Looks up and downloads a poster, blocking — meant to be called from
    a background thread, never the UI thread. Returns the local file
    path on success, or None (no key configured, no match, or a
    network problem). Never raises.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(title, year, media_type)
    cached_path = CACHE_DIR / f"{key}.jpg"
    miss_marker = CACHE_DIR / f"{key}.miss"

    if cached_path.is_file():
        return str(cached_path)

    config = load_config()
    api_key = config.get("tmdb_api_key")
    if not api_key:
        return None

    from app.core.title_cleaner import get_search_candidate_titles
    candidates = get_search_candidate_titles(title, year)

    # If miss marker exists and we have no fallback candidates, skip
    if miss_marker.is_file() and len(candidates) <= 1:
        return None

    endpoint = "movie" if media_type == "movie" else "tv"
    poster_path = None

    for q_title, q_year in candidates:
        try:
            params = {"api_key": api_key, "query": q_title}
            if q_year and media_type == "movie":
                params["year"] = q_year
            search_url = f"https://api.themoviedb.org/3/search/{endpoint}?{urllib.parse.urlencode(params)}"

            with urllib.request.urlopen(search_url, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            for result in data.get("results") or []:
                if result.get("poster_path"):
                    poster_path = result["poster_path"]
                    break
            if poster_path:
                break
        except Exception:
            continue

    if not poster_path:
        miss_marker.touch()
        return None

    try:
        if miss_marker.is_file():
            miss_marker.unlink(missing_ok=True)
        image_url = f"{TMDB_IMAGE_BASE}{poster_path}"
        with urllib.request.urlopen(image_url, timeout=REQUEST_TIMEOUT) as resp:
            image_bytes = resp.read()

        with open(cached_path, "wb") as f:
            f.write(image_bytes)
        return str(cached_path)
    except Exception:
        return None


def fetch_movie_metadata(
    title: str,
    year: str | None,
    media_type: str = "movie",
) -> dict:
    """
    Returns a dict with keys:
        poster_path  : local file path (str) or None
        overview     : plot synopsis (str) or ""
        rating       : TMDb vote_average (float) or None
        imdb_id      : IMDb id string e.g. "tt1234567" or None

    Always returns the dict even on failure (keys present, values None/"").
    Blocking — call from a background thread.
    """
    result = {"poster_path": None, "overview": "", "rating": None, "imdb_id": None}

    config = load_config()
    api_key = config.get("tmdb_api_key")
    if not api_key:
        # Still try to return a cached poster if it exists
        result["poster_path"] = cached_poster_path(title, year, media_type)
        return result

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    endpoint = "movie" if media_type == "movie" else "tv"

    try:
        from app.core.title_cleaner import get_search_candidate_titles
        candidates = get_search_candidate_titles(title, year)
        best = None

        for q_title, q_year in candidates:
            try:
                params: dict = {"api_key": api_key, "query": q_title}
                if q_year and media_type == "movie":
                    params["year"] = q_year
                search_url = (
                    f"https://api.themoviedb.org/3/search/{endpoint}"
                    f"?{urllib.parse.urlencode(params)}"
                )
                with urllib.request.urlopen(search_url, timeout=REQUEST_TIMEOUT) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                for r in data.get("results") or []:
                    if r.get("poster_path"):
                        best = r
                        break
                if best is None and data.get("results"):
                    best = data["results"][0]

                if best is not None:
                    break
            except Exception:
                continue

        if best is None:
            return result

        result["overview"] = best.get("overview") or ""
        result["rating"] = best.get("vote_average")

        # Fetch imdb_id via /movie/{id}/external_ids
        tmdb_id = best.get("id")
        if tmdb_id:
            ext_url = (
                f"https://api.themoviedb.org/3/{endpoint}/{tmdb_id}"
                f"/external_ids?api_key={api_key}"
            )
            try:
                with urllib.request.urlopen(ext_url, timeout=REQUEST_TIMEOUT) as r2:
                    ext = json.loads(r2.read().decode("utf-8"))
                result["imdb_id"] = ext.get("imdb_id")
            except Exception:
                pass

        # Download / return poster
        poster_path_tmdb = best.get("poster_path")
        if poster_path_tmdb:
            key = _cache_key(title, year, media_type)
            cached_path = CACHE_DIR / f"{key}.jpg"
            if not cached_path.is_file():
                image_url = f"{TMDB_IMAGE_BASE}{poster_path_tmdb}"
                with urllib.request.urlopen(image_url, timeout=REQUEST_TIMEOUT) as resp:
                    cached_path.write_bytes(resp.read())
            result["poster_path"] = str(cached_path)
        else:
            result["poster_path"] = cached_poster_path(title, year, media_type)

    except Exception:
        result["poster_path"] = cached_poster_path(title, year, media_type)

    return result
