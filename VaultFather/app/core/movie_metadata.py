"""
Extended TMDb metadata fetcher:
Enriches movies with Plot / Overview, Genres, Director, Language, IMDb ID,
Letterboxd links, Vote Rating, Cast, Backdrop, and Poster images.
"""

import json
import os
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import load_config
from app.core.title_cleaner import parse_movie_title_and_year

METADATA_CACHE_DIR = Path.home() / ".vaultfather" / "metadata_cache"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w780"
TMDB_BACKDROP_BASE = "https://image.tmdb.org/t/p/w1280"
REQUEST_TIMEOUT = 10


@dataclass
class MovieMetadata:
    title: str
    year: str | None = None
    plot: str = "No overview available."
    genres: list[str] = field(default_factory=list)
    director: str = "Unknown"
    language: str = "English"
    rating: float = 0.0
    runtime_minutes: int | None = None
    imdb_id: str | None = None
    tmdb_id: int | None = None
    poster_path: str | None = None
    backdrop_path: str | None = None
    cast: list[str] = field(default_factory=list)

    @property
    def imdb_url(self) -> str | None:
        return f"https://www.imdb.com/title/{self.imdb_id}/" if self.imdb_id else None

    @property
    def letterboxd_url(self) -> str:
        if self.tmdb_id:
            return f"https://letterboxd.com/tmdb/{self.tmdb_id}/"
        query = urllib.parse.quote(f"{self.title} {self.year or ''}".strip())
        return f"https://letterboxd.com/search/{query}/"

    @property
    def rating_formatted(self) -> str:
        return f"{self.rating:.1f}" if self.rating > 0 else "—"

    @property
    def genres_formatted(self) -> str:
        return ", ".join(self.genres) if self.genres else "General"


def fetch_movie_metadata(filename_or_title: str) -> MovieMetadata:
    """
    Fetches full movie metadata from TMDb (with disk cache) or returns fallback data.
    """
    clean_title, year = parse_movie_title_and_year(filename_or_title)
    METADATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = f"{clean_title.strip().lower()}_{year or ''}"
    cache_file = METADATA_CACHE_DIR / f"{cache_key}.json"

    if cache_file.is_file():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            meta = MovieMetadata(**data)
            # Migrate old cache entries that stored a remote URL instead of a local path
            pp = meta.poster_path
            if pp and (pp.startswith("http") or not os.path.isfile(pp)):
                from app.core.poster_service import cached_poster_path as _cached
                local = _cached(clean_title, year, "movie")
                meta.poster_path = local  # None if not yet cached — popup will fall back
            return meta
        except Exception:
            pass


    config = load_config()
    api_key = config.get("tmdb_api_key")
    if not api_key:
        return MovieMetadata(title=clean_title, year=year)

    try:
        # 1. Search movie
        query_params = {"api_key": api_key, "query": clean_title, "include_adult": "false"}
        if year:
            query_params["year"] = str(year)
        url = f"https://api.themoviedb.org/3/search/movie?{urllib.parse.urlencode(query_params)}"

        req = urllib.request.Request(url, headers={"User-Agent": "VaultFather/2.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = data.get("results", [])
        if not results and year:
            # Fallback search without year
            query_params.pop("year", None)
            url = f"https://api.themoviedb.org/3/search/movie?{urllib.parse.urlencode(query_params)}"
            req = urllib.request.Request(url, headers={"User-Agent": "VaultFather/2.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])

        if not results:
            fallback = MovieMetadata(title=clean_title, year=year)
            return fallback

        tmdb_movie = results[0]
        tmdb_id = tmdb_movie["id"]

        # 2. Fetch full details with credits & external_ids
        detail_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={api_key}&append_to_response=credits,external_ids"
        req = urllib.request.Request(detail_url, headers={"User-Agent": "VaultFather/2.0"})
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            details = json.loads(resp.read().decode("utf-8"))

        plot = details.get("overview") or "No overview available."
        genres = [g["name"] for g in details.get("genres", [])]
        rating = float(details.get("vote_average") or 0.0)
        runtime = details.get("runtime")
        lang = (details.get("original_language") or "en").upper()
        ext_ids = details.get("external_ids", {})
        imdb_id = ext_ids.get("imdb_id")

        # Director & Cast
        credits = details.get("credits", {})
        director = "Unknown"
        for crew in credits.get("crew", []):
            if crew.get("job") == "Director":
                director = crew.get("name")
                break

        cast = [c.get("name") for c in credits.get("cast", [])[:5] if c.get("name")]

        # Download poster to poster_service cache and store local path
        local_poster_path = None
        if details.get("poster_path"):
            from app.core.poster_service import fetch_poster as _fetch_poster_file, cached_poster_path as _cached
            # Use the parsed clean_title + year as the cache key (matches what cards use)
            local_poster_path = _cached(clean_title, year, "movie")
            if not local_poster_path:
                local_poster_path = _fetch_poster_file(clean_title, year, "movie")

        # Backdrop URL (stored as remote URL — only used for display, not downloaded)
        backdrop_raw = details.get("backdrop_path")
        backdrop_url = f"{TMDB_BACKDROP_BASE}{backdrop_raw}" if backdrop_raw else None

        meta = MovieMetadata(
            title=details.get("title") or clean_title,
            year=year or (details.get("release_date", "")[:4] or None),
            plot=plot,
            genres=genres,
            director=director,
            language=lang,
            rating=rating,
            runtime_minutes=runtime,
            imdb_id=imdb_id,
            tmdb_id=tmdb_id,
            poster_path=local_poster_path,
            backdrop_path=backdrop_url,
            cast=cast,
        )

        # Cache metadata to disk (poster_path is now a local path or None)
        try:
            cache_file.write_text(json.dumps(meta.__dict__, indent=2), encoding="utf-8")
        except Exception:
            pass

        return meta


    except Exception:
        return MovieMetadata(title=clean_title, year=year)