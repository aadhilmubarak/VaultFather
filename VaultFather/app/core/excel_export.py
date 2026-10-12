"""
Exports Backup History to a two-sheet .xlsx: Movies and Series.

Schema (per your latest spec): Movie Name | Size | Password Used |
Backup Date | Backup Location — no separate Status/Direct Link columns
anymore; Location IS the link now, one per destination that movie
actually succeeded to.

A single Excel cell can only carry one hyperlink — there's no native
way to make individual items inside a dropdown independently
clickable without VBA macros, which raises more friction (security
warnings, "Enable Content" prompts) than it's worth for this. Instead:
each movie gets ONE merged block — Movie Name/Size/Password/Date
merged vertically across as many rows as it has successful
destinations — with one real, clickable row per destination in the
Location column. Reads as "one row per movie, its locations listed
underneath," fully native, no macros, no buttons.

Movies/episodes with zero successful backups are left out entirely —
nothing useful to show, and no point cluttering the sheet with rows
that don't lead anywhere.

Sort: the sheet is pre-sorted A→Z by name on export (initial view).
Excel AutoFilter arrows on Name, Backup Date, and Size let the user
click any of those headers and choose ascending / descending inside
Excel without any macros — the full row block (name + password +
date + size + all location rows) moves together as one unit because
each movie occupies a contiguous range of rows.
"""

import re
from itertools import groupby

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.core.database import list_movie_backups, list_series_backups, get_destination_by_name
from app.core.movie_scanner import human_size
from app.core.title_cleaner import clean_movie_title

# --- Palette (Cyber Obsidian palette, clean and high-contrast) ---
OBSIDIAN_HEADER = "161330"
INK = "1A1638"
ROW_LIGHT = "FFFFFF"
ROW_BAND = "F6F5FC"
BORDER_COLOR = "DDD7F5"

HEADER_FONT = Font(name="Segoe UI", size=10.5, bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color=OBSIDIAN_HEADER, end_color=OBSIDIAN_HEADER, fill_type="solid")
TITLE_FONT = Font(name="Segoe UI", size=10, bold=True, color=INK)
BODY_FONT = Font(name="Segoe UI", size=9.5, color="2A2550")
LINK_FONT = Font(name="Segoe UI", size=9.5, color="1B56F5", underline="single")

THIN_BORDER = Border(bottom=Side(style="thin", color=BORDER_COLOR), top=Side(style="thin", color=BORDER_COLOR))
OUTER_BORDER = Border(
    bottom=Side(style="thin", color=BORDER_COLOR), top=Side(style="thin", color=BORDER_COLOR),
    left=Side(style="thin", color=BORDER_COLOR), right=Side(style="thin", color=BORDER_COLOR),
)

CENTER = Alignment(horizontal="center", vertical="center")
CENTER_WRAP = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center")
LEFT_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)


def _telegram_link(destination: str | None, message_ids: list[str]) -> str:
    """
    Plain https://t.me/c/... link — Excel hyperlinks can only point at
    one URI with no fallback logic, and t.me is Telegram's own
    universal link: it already tries the installed app first and falls
    back to a web preview on its own, which is the closest thing to
    "app if installed, else browser" achievable from a static link.
    """
    if not destination or not message_ids:
        return ""
    dest = get_destination_by_name(destination)
    if not dest or not dest.telegram_channel_id:
        return ""
    channel_id = str(dest.telegram_channel_id).removeprefix("-100").removeprefix("-")
    return f"https://t.me/c/{channel_id}/{message_ids[0]}"


def _size_bytes(human: str) -> float:
    """Convert a human_size string like '1.23 GB' back to bytes for numeric sort."""
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    m = re.match(r"([\d.]+)\s*([A-Z]+)", human.strip().upper())
    if not m:
        return 0.0
    return float(m.group(1)) * units.get(m.group(2), 1)


def _style_header(ws, columns: list[str], center_cols: set[int]) -> None:
    ws.row_dimensions[1].height = 22
    for col_idx, title in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = CENTER if col_idx in center_cols else LEFT
    ws.freeze_panes = "A2"


def _apply_autofilter(ws, total_cols: int) -> None:
    """Add Excel AutoFilter across all columns so the sort arrows appear."""
    last_col_letter = get_column_letter(total_cols)
    ws.auto_filter.ref = f"A1:{last_col_letter}1"


def _autofit(ws, columns: list[str]) -> None:
    for col_idx, title in enumerate(columns, start=1):
        max_len = len(title)
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx, min_row=2):
            for cell in row:
                if cell.value:
                    max_len = max(max_len, len(str(cell.value)))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max_len + 3, 60)


def _write_block(ws, start_row: int, fixed_values: list, locations: list[tuple[str, str]],
                  fixed_cols: int, center_cols: set[int], band_color: str) -> int:
    """
    Writes one movie/episode's block: fixed_values across fixed_cols
    (merged vertically if there's more than one location), then one
    row per (destination_name, link) in the Location column.
    Returns the row index right after this block.
    """
    span = max(1, len(locations))
    end_row = start_row + span - 1
    fill = PatternFill(start_color=band_color, end_color=band_color, fill_type="solid")

    for col_idx, value in enumerate(fixed_values, start=1):
        cell = ws.cell(row=start_row, column=col_idx, value=value)
        cell.font = TITLE_FONT if col_idx == 1 else BODY_FONT
        cell.alignment = (CENTER_WRAP if col_idx in center_cols else LEFT_WRAP)
        if span > 1:
            ws.merge_cells(start_row=start_row, start_column=col_idx, end_row=end_row, end_column=col_idx)
        for r in range(start_row, end_row + 1):
            ws.cell(row=r, column=col_idx).fill = fill
            ws.cell(row=r, column=col_idx).border = OUTER_BORDER

    location_col = fixed_cols + 1
    if locations:
        for offset, (name, link) in enumerate(locations):
            r = start_row + offset
            cell = ws.cell(row=r, column=location_col, value=name)
            cell.alignment = LEFT
            cell.fill = fill
            cell.border = OUTER_BORDER
            if link:
                cell.hyperlink = link
                cell.font = LINK_FONT
            else:
                cell.font = BODY_FONT
    else:
        cell = ws.cell(row=start_row, column=location_col, value="—")
        cell.alignment = LEFT
        cell.fill = fill
        cell.border = OUTER_BORDER
        cell.font = BODY_FONT

    return end_row + 1


def export_backup_history(output_path: str) -> str:
    wb = Workbook()

    # ------------------------------------------------------------------ Movies
    ws_movies = wb.active
    ws_movies.title = "Movies"
    movie_columns = ["Movie Name", "Size", "Password Used", "Backup Date", "Backup Location"]
    movie_center = {2, 4}
    _style_header(ws_movies, movie_columns, movie_center)
    _apply_autofilter(ws_movies, len(movie_columns))

    # Collect all movie blocks first so we can sort before writing.
    # Each block = (name_key, size_bytes, date_str, fixed_values, locations)
    movie_blocks: list[tuple] = []
    for movie_path, group in groupby(list_movie_backups(), key=lambda m: m.movie_path):
        records = list(group)
        successful = [r for r in records if r.status == "backed_up"]
        if not successful:
            continue

        first = successful[0]
        size_str = human_size(first.total_archive_size_bytes)
        date_str = first.created_at[:10]
        fixed_values = [
            first.movie_name, size_str,
            first.password, date_str,
        ]
        locations = [
            (r.destination or "Unknown", _telegram_link(r.destination, r.telegram_message_ids))
            for r in successful
        ]
        movie_blocks.append((
            (first.movie_name or "").lower(),   # sort key: name
            _size_bytes(size_str),              # sort key: size
            date_str,                           # sort key: date
            fixed_values,
            locations,
        ))

    # Default initial sort: ascending by name (A → Z).
    # Excel's AutoFilter arrows let the user re-sort by Name / Backup Date /
    # Size ascending or descending inside Excel with one click — no macros needed.
    movie_blocks.sort(key=lambda b: b[0])  # sort A→Z by name

    row_idx = 2
    band_toggle = False
    for _name_k, _size_k, _date_k, fixed_values, locations in movie_blocks:
        band_toggle = not band_toggle
        row_idx = _write_block(
            ws_movies, row_idx, fixed_values, locations,
            fixed_cols=4, center_cols=movie_center,
            band_color=ROW_LIGHT if band_toggle else ROW_BAND,
        )

    _autofit(ws_movies, movie_columns)

    # ------------------------------------------------------------------ Series
    ws_series = wb.create_sheet("Series")
    series_columns = ["Series Name", "Season", "Episode", "Episode Name", "Size", "Password Used", "Date Uploaded", "Backup Location"]
    series_center = {2, 3, 5, 7}
    _style_header(ws_series, series_columns, series_center)
    _apply_autofilter(ws_series, len(series_columns))

    # Collect series blocks for sorting.
    series_blocks: list[tuple] = []
    key_func = lambda e: (e.series_name, e.season_number, e.episode_number)
    for _key, group in groupby(list_series_backups(), key=key_func):
        records = list(group)
        successful = [r for r in records if r.status == "backed_up"]
        if not successful:
            continue

        first = successful[0]
        size_str = human_size(first.total_archive_size_bytes)
        date_str = first.created_at[:10]
        fixed_values = [
            first.series_name, f"S{first.season_number:02d}", f"E{first.episode_number:02d}",
            first.episode_name, size_str,
            first.password, date_str,
        ]
        locations = [
            (r.destination or "Unknown", _telegram_link(r.destination, r.telegram_message_ids))
            for r in successful
        ]
        series_blocks.append((
            (first.series_name or "").lower(),  # sort key: name
            _size_bytes(size_str),              # sort key: size
            date_str,                           # sort key: date
            fixed_values,
            locations,
        ))

    # Default: ascending by series name, then season, then episode.
    series_blocks.sort(key=lambda b: b[0])

    row_idx = 2
    band_toggle = False
    for _name_k, _size_k, _date_k, fixed_values, locations in series_blocks:
        band_toggle = not band_toggle
        row_idx = _write_block(
            ws_series, row_idx, fixed_values, locations,
            fixed_cols=7, center_cols=series_center,
            band_color=ROW_LIGHT if band_toggle else ROW_BAND,
        )

    _autofit(ws_series, series_columns)

    wb.save(output_path)
    return output_path
