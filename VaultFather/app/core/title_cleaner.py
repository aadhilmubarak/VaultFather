"""
Turns a raw torrent-style or organized filename into a clean "Title (Year)"
or parsed (title, year) tuple for metadata lookup and display.

Handles edge cases such as:
  - Numbers in titles: "2012 (2009).mkv" -> "2012 (2009)"
  - Sequels with years: "Blade Runner 2049 (2017).mkv" -> "Blade Runner 2049 (2017)"
  - Year-named titles: "1917.2019.1080p.mkv" -> "1917 (2019)"
  - Standard titles: "Interstellar.2014.Remux.2160p.mkv" -> "Interstellar (2014)"
  - Channel / group tags: "@CC_Links.12.Angry.Men.1957.mkv" -> "12 Angry Men (1957)"
  - Director's cut / Snyder cut editions: "Justice League Snyder Cut 2021" -> "Justice League (2021)"
"""

import re
from pathlib import Path

# Channel / uploader prefixes e.g. @CC_Links., @MovieWorld, [TG]
CHANNEL_PREFIX_RE = re.compile(r"^(@[\w-]+|\[[\w.-]+\])[.\s_]+", re.IGNORECASE)

# Known release tags that indicate the end of title / year section
QUALITY_TAGS = re.compile(
    r"\b(2160p|1080p|720p|480p|4k|uhd|bluray|blu-ray|bdrip|brrip|web-dl|webrip|web|hdtv|"
    r"remux|repack|proper|unrated|extended|directors\.cut|imax|hdr10\+?|hdr|dv|dovi|"
    r"x264|x265|h264|h265|hevc|avc|10bit|8bit|dts-hd|dts|truehd|atmos|ddp?5\.1|ac3|aac|"
    r"yts(\.mx|\.lt)?|yify|rarbg|psa|qxr|galaxyrg|flux|sparks|amiable)\b",
    re.IGNORECASE,
)

# Common edition / director's cut markers
EDITION_RE = re.compile(
    r"\b((zack\s*)?sn[yi]der(\x27?s)?\s*cut|director(\x27?s)?\s*cut|the\s*final\s*cut|final\s*cut|"
    r"extended(\s*(cut|edition|version))?|unrated(\s*(cut|edition))?|ultimate\s*(cut|edition)?|"
    r"special\s*edition|imax(\s*edition)?|theatrical(\s*(cut|edition))?|assembly\s*cut|"
    r"remastered|criterion(\s*collection)?|richard\s*donner\s*cut)\b",
    re.IGNORECASE,
)

# Explicit year in parentheses or brackets: (2009) or [2017]
EXPLICIT_YEAR_RE = re.compile(r"[\(\[\{](19\d{2}|20\d{2})[\)\]\}]")

# Standalone 4-digit year pattern
YEAR_TOKEN_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

TRAILING_JUNK_RE = re.compile(r"[\s.\-_(\[\{]+$")
LEADING_JUNK_RE = re.compile(r"^[\s.\-_)\]\}]+")


def parse_movie_title_and_year(filename: str) -> tuple[str, str | None]:
    """
    Parses raw filename into (clean_title, year_str).
    Returns year_str as 'YYYY' or None if not found.
    """
    stem = Path(filename).stem

    # 0. Strip leading channel / group prefixes (e.g. @CC_Links. or [YTS])
    stem = CHANNEL_PREFIX_RE.sub("", stem)

    # 1. Check for explicit year in brackets/parentheses e.g. (2009) or [2017]
    bracket_matches = list(EXPLICIT_YEAR_RE.finditer(stem))
    if bracket_matches:
        last_match = bracket_matches[-1]
        year = last_match.group(1)
        raw_title = stem[:last_match.start()]
        clean_title = _clean_title_string(raw_title)
        if clean_title:
            return clean_title, year

    # 2. Strip quality tags and everything after them
    tag_match = QUALITY_TAGS.search(stem)
    working_text = stem[:tag_match.start()] if tag_match else stem

    # Normalize dot/underscore separators to spaces
    normalized = re.sub(r"[._]+", " ", working_text)

    # 3. Find all 4-digit years in the sanitized string
    year_matches = list(YEAR_TOKEN_RE.finditer(normalized))
    if not year_matches:
        clean = _clean_title_string(normalized)
        return clean or stem, None

    # If there are multiple year-like tokens (e.g. "2012 2009" or "Blade Runner 2049 2017"),
    # the actual release year is the LAST one in the normalized string before quality tags.
    target_match = year_matches[-1]
    year = target_match.group(1)
    raw_title = normalized[:target_match.start()]
    clean_title = _clean_title_string(raw_title)

    if not clean_title:
        # The entire text was just the year itself (e.g. "2012.mkv")
        # In this case, treat the year as the title!
        return year, None

    return clean_title, year


def strip_edition_tags(title: str) -> str:
    """Removes edition / cut strings (e.g. 'Directors Cut', 'Snyder Cut') from a title."""
    cleaned = EDITION_RE.sub("", title)
    return re.sub(r"\s{2,}", " ", cleaned).strip(" .-_")


def get_search_candidate_titles(title: str, year: str | None = None) -> list[tuple[str, str | None]]:
    """
    Generates an ordered list of (query_title, query_year) search candidates
    for resilient TMDb poster and OpenSubtitles lookup.
    """
    candidates: list[tuple[str, str | None]] = []
    seen = set()

    def _add(q_t: str, q_y: str | None):
        t_norm = q_t.strip().lower()
        key = (t_norm, q_y)
        if t_norm and key not in seen:
            seen.add(key)
            candidates.append((q_t.strip(), q_y))

    # 1. As-is query
    _add(title, year)

    # 2. Query with edition tags removed (e.g. 'Nymphomaniac Directors Cut Vol 2' -> 'Nymphomaniac Vol 2')
    stripped = strip_edition_tags(title)
    if stripped and stripped.lower() != title.lower():
        _add(stripped, year)

    # 3. Specific known aliases / cuts
    t_lower = title.lower()
    if "snyder" in t_lower or "snider" in t_lower:
        _add("Zack Snyder's Justice League", year)
        _add("Justice League", year)
    elif "blade runner" in t_lower:
        _add("Blade Runner", year)

    # 4. Fallbacks without year (handles incorrect/re-release years in filenames)
    if year:
        _add(title, None)
        if stripped and stripped.lower() != title.lower():
            _add(stripped, None)
        if "snyder" in t_lower or "snider" in t_lower:
            _add("Zack Snyder's Justice League", None)
            _add("Justice League", None)

    return candidates


def _clean_title_string(raw: str) -> str:
    cleaned = re.sub(r"[._]+", " ", raw)
    cleaned = TRAILING_JUNK_RE.sub("", cleaned)
    cleaned = LEADING_JUNK_RE.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def clean_movie_title(filename: str) -> str:
    """
    Returns 'Title (Year)' or just 'Title' if no year was found.
    """
    title, year = parse_movie_title_and_year(filename)
    if year:
        return f"{title} ({year})"
    return title
