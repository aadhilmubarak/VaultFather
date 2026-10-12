"""
Cloud Vault Page — Cyber Obsidian Glass.

Fixes vs. previous version:
  1. Poster no longer overflows card bounds (Qt.KeepAspectRatio, setScaledContents=False).
  2. Backup destination dialog is shown every time — forces user to pick channels.
  3. Netflix-style poster grid with genre/director/language filter combos.
  4. Local + Cloud Vault browsing with smooth search.
"""

import os
import threading
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFileDialog,
    QScrollArea, QPushButton, QLineEdit, QComboBox, QFrame,
    QProgressBar, QMessageBox, QDialog, QVBoxLayout as QVL, QHBoxLayout as QHL
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QPixmap, QColor

from app.ui.widgets.glass_card import GlassCard
from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.ui.widgets.checkable_combo import CheckableComboBox
from app.ui.dialogs.movie_details_dialog import MovieDetailsDialog
from app.ui.dialogs.series_queue_dialog import SeriesQueueDialog
from app.core.movie_scanner import scan_movies, human_size
from app.core.series_scanner import scan_series
from app.core.database import list_movie_backups, list_series_backups, list_playback_history, list_destinations
from app.core.config import load_config, save_config
from app.core.title_cleaner import clean_movie_title, parse_movie_title_and_year
from app.core.poster_service import cached_poster_path, fetch_poster
from app.core.telegram_downloader import restore_and_extract_movie

GRID_COLS = 5
POSTER_W  = 168
POSTER_H  = 230
CARD_W    = POSTER_W + 16
CARD_H    = POSTER_H + 54


# ── Destination picker dialog ─────────────────────────────────────────────────

class _DestinationPickerDialog(QDialog):
    """Simple modal that always asks the user which Telegram channel to use."""

    def __init__(self, movie_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Backup Destination")
        self.setMinimumWidth(340)
        self.setStyleSheet("QDialog { background-color: #0E0C1E; }")

        lay = QVL()
        lay.setContentsMargins(24, 22, 24, 22)
        lay.setSpacing(14)
        self.setLayout(lay)

        title = QLabel(f"Backup: {movie_name}")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #E8F4FF;")
        title.setWordWrap(True)
        lay.addWidget(title)

        lbl = QLabel("Select destination channels:")
        lbl.setStyleSheet("color: #8BA8C8; font-size: 12px;")
        lay.addWidget(lbl)

        dest_names = [d.name for d in list_destinations()]
        self.combo = CheckableComboBox(dest_names)
        lay.addWidget(self.combo)

        btn_row = QHL()
        btn_row.addStretch()
        cancel = GhostButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)
        ok = PrimaryButton("+ Queue Backup")
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)

    def selected_destinations(self) -> list[str]:
        return self.combo.checked_items()


# ── Movie card ────────────────────────────────────────────────────────────────

class MovieCardItem(GlassCard):
    play_clicked    = Signal(object)   # item_data dict
    details_clicked = Signal(object)   # item_data dict

    def __init__(self, item_data: dict, parent=None):
        super().__init__(parent)
        self.item_data = item_data
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(CARD_W, CARD_H)
        self.setStyleSheet(
            "QFrame#GlassCard { background-color: rgba(14, 12, 32, 185);"
            "  border: 1px solid rgba(0,240,255,22); border-radius: 14px; }"
            "QFrame#GlassCard:hover { border: 1px solid rgba(0,240,255,90);"
            "  background-color: rgba(20, 16, 46, 220); }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)

        # ── Poster frame (fixed size clip) ───────────────────────────────────
        self.poster_lbl = QLabel()
        self.poster_lbl.setFixedSize(POSTER_W, POSTER_H)
        self.poster_lbl.setAlignment(Qt.AlignCenter)
        self.poster_lbl.setScaledContents(False)
        self.poster_lbl.setStyleSheet(
            "background-color: #0B0A18; border-radius: 9px; color: #3D5A7A;"
        )

        # Badges overlay: build in a stacked way with absolute positioning
        self._poster_container = QFrame()
        self._poster_container.setFixedSize(POSTER_W, POSTER_H)
        self._poster_container.setStyleSheet("background: transparent;")

        # Poster label fills container
        self.poster_lbl.setParent(self._poster_container)
        self.poster_lbl.move(0, 0)

        # Location badge (top-left)
        if item_data.get("is_cloud"):
            loc_txt, loc_style = "CLOUD", (
                "background:rgba(0,240,255,200);color:#080714;"
                "font-size:8.5px;font-weight:800;padding:2px 6px;border-radius:4px;"
            )
        else:
            loc_txt, loc_style = "LOCAL", (
                "background:rgba(0,255,200,200);color:#080714;"
                "font-size:8.5px;font-weight:800;padding:2px 6px;border-radius:4px;"
            )
        self._loc_badge = QLabel(loc_txt, self._poster_container)
        self._loc_badge.setStyleSheet(loc_style)
        self._loc_badge.adjustSize()
        self._loc_badge.move(8, 8)
        self._loc_badge.raise_()

        # Rating badge (top-right)
        rating = item_data.get("rating", 0)
        if rating and rating > 0:
            self._rat_badge = QLabel(f"★ {rating:.1f}", self._poster_container)
            self._rat_badge.setStyleSheet(
                "background:rgba(8,7,20,190);color:#FFB347;"
                "font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;"
            )
            self._rat_badge.adjustSize()
            self._rat_badge.move(POSTER_W - self._rat_badge.width() - 8, 8)
            self._rat_badge.raise_()

        # Play button (centre, hidden until hover — we always show for clarity)
        self._play_btn = QPushButton("▶", self._poster_container)
        self._play_btn.setFixedSize(40, 40)
        self._play_btn.setCursor(Qt.PointingHandCursor)
        self._play_btn.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "  stop:0 #00F0FF,stop:1 #7B2FF7);"
            "color:#080714;font-size:16px;font-weight:700;"
            "border:none;border-radius:20px;"
        )
        self._play_btn.move(
            (POSTER_W - 40) // 2,
            (POSTER_H - 40) // 2
        )
        self._play_btn.raise_()
        self._play_btn.clicked.connect(lambda: self.play_clicked.emit(self.item_data))

        # Progress bar (bottom strip if partially watched)
        progress = item_data.get("watch_progress", 0.0)
        if progress > 0.02:
            self._prog = QProgressBar(self._poster_container)
            self._prog.setFixedSize(POSTER_W, 4)
            self._prog.setTextVisible(False)
            self._prog.setRange(0, 100)
            self._prog.setValue(int(progress * 100))
            self._prog.setStyleSheet(
                "QProgressBar{background:rgba(255,255,255,28);border:none;border-radius:2px;}"
                "QProgressBar::chunk{background:#00F0FF;border-radius:2px;}"
            )
            self._prog.move(0, POSTER_H - 4)
            self._prog.raise_()

        lay.addWidget(self._poster_container)

        # ── Title + year ─────────────────────────────────────────────────────
        title_lbl = QLabel(item_data.get("title", "Untitled"))
        title_lbl.setStyleSheet(
            "font-size: 11.5px; font-weight: 700; color: #E8F4FF;"
        )
        title_lbl.setWordWrap(False)
        title_lbl.setMaximumWidth(POSTER_W)
        title_lbl.setToolTip(item_data.get("title", ""))
        lay.addWidget(title_lbl)

        sub_row = QHBoxLayout()
        sub_row.setContentsMargins(0, 0, 0, 0)
        year_lbl = QLabel(str(item_data.get("year") or ""))
        year_lbl.setStyleSheet("font-size: 10px; color: #3D5A7A;")
        sub_row.addWidget(year_lbl)
        sub_row.addStretch()

        info_btn = QPushButton("ℹ")
        info_btn.setCursor(Qt.PointingHandCursor)
        info_btn.setFixedSize(22, 22)
        info_btn.setStyleSheet(
            "QPushButton { background: rgba(0,240,255,18); color: #00F0FF;"
            "border: 1px solid rgba(0,240,255,50); border-radius: 11px; font-size: 11px; }"
            "QPushButton:hover { background: rgba(0,240,255,35); }"
        )
        info_btn.clicked.connect(lambda: self.details_clicked.emit(self.item_data))
        sub_row.addWidget(info_btn)
        lay.addLayout(sub_row)

        # Load poster asynchronously
        QTimer.singleShot(0, self._load_poster)

    def _load_poster(self):
        # Use the parsed clean title + year so the cache key matches exactly
        # what poster_service stored when the poster was first fetched.
        title = self.item_data.get("poster_title") or self.item_data.get("raw_name", self.item_data.get("title"))
        year  = self.item_data.get("year")
    def _load_poster(self):
        title = self.item_data.get("poster_title") or self.item_data.get("raw_name", self.item_data.get("title"))
        year  = self.item_data.get("year")
        from app.core.poster_loader import poster_loader, _cache_key
        self._cache_key = _cache_key(title, year, "movie")
        cached = poster_loader.request(title, year, "movie")
        if cached and os.path.isfile(cached):
            self._set_pixmap(cached)
        else:
            poster_loader.poster_ready.connect(self._on_poster_ready)

    def _on_poster_ready(self, key: str, path: str):
        if key == getattr(self, "_cache_key", None):
            try:
                from app.core.poster_loader import poster_loader
                poster_loader.poster_ready.disconnect(self._on_poster_ready)
            except Exception:
                pass
            if path and os.path.isfile(path):
                self._set_pixmap(path)

    def _set_pixmap(self, path: str):
        pix = QPixmap(path).scaled(
            POSTER_W, POSTER_H,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.poster_lbl.setPixmap(pix)

    def mouseDoubleClickEvent(self, event):
        self.play_clicked.emit(self.item_data)
        super().mouseDoubleClickEvent(event)


# ── Series card ────────────────────────────────────────────────────────────────

class SeriesCardItem(GlassCard):
    clicked = Signal(object)   # series_data dict: {"name": str, "seasons": dict}

    def __init__(self, series_data: dict, parent=None):
        super().__init__(parent)
        self.series_data = series_data
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(CARD_W, CARD_H)
        self.setStyleSheet(
            "QFrame#GlassCard { background-color: rgba(14, 12, 32, 185);"
            "  border: 1px solid rgba(0,240,255,22); border-radius: 14px; }"
            "QFrame#GlassCard:hover { border: 1px solid rgba(0,240,255,90);"
            "  background-color: rgba(20, 16, 46, 220); }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)

        self.poster_lbl = QLabel()
        self.poster_lbl.setFixedSize(POSTER_W, POSTER_H)
        self.poster_lbl.setAlignment(Qt.AlignCenter)
        self.poster_lbl.setScaledContents(False)
        self.poster_lbl.setStyleSheet(
            "background-color: #0B0A18; border-radius: 9px; color: #3D5A7A;"
        )

        self._poster_container = QFrame()
        self._poster_container.setFixedSize(POSTER_W, POSTER_H)
        self._poster_container.setStyleSheet("background: transparent;")

        self.poster_lbl.setParent(self._poster_container)
        self.poster_lbl.move(0, 0)

        # TV badge
        badge = QLabel("TV SERIES", self._poster_container)
        badge.setStyleSheet(
            "background:rgba(123,47,247,210);color:#FFFFFF;"
            "font-size:8.5px;font-weight:800;padding:2px 6px;border-radius:4px;"
        )
        badge.adjustSize()
        badge.move(8, 8)
        badge.raise_()

        # Seasons count badge
        seasons = series_data.get("seasons", {})
        s_count = len(seasons)
        s_badge = QLabel(f"{s_count} Season{'s' if s_count != 1 else ''}", self._poster_container)
        s_badge.setStyleSheet(
            "background:rgba(8,7,20,190);color:#00F0FF;"
            "font-size:9px;font-weight:700;padding:2px 6px;border-radius:4px;"
        )
        s_badge.adjustSize()
        s_badge.move(POSTER_W - s_badge.width() - 8, 8)
        s_badge.raise_()

        # Manage/Queue button
        self._queue_btn = QPushButton("Manage", self._poster_container)
        self._queue_btn.setFixedSize(68, 28)
        self._queue_btn.setCursor(Qt.PointingHandCursor)
        self._queue_btn.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "  stop:0 #00F0FF,stop:1 #7B2FF7);"
            "color:#080714;font-size:11px;font-weight:700;"
            "border:none;border-radius:14px;"
        )
        self._queue_btn.move((POSTER_W - 68) // 2, (POSTER_H - 28) // 2)
        self._queue_btn.raise_()
        self._queue_btn.clicked.connect(lambda: self.clicked.emit(self.series_data))

        lay.addWidget(self._poster_container)

        # Series Title
        title_lbl = QLabel(series_data.get("name", "Unknown Series"))
        title_lbl.setStyleSheet(
            "font-size: 11.5px; font-weight: 700; color: #E8F4FF;"
        )
        title_lbl.setWordWrap(False)
        title_lbl.setMaximumWidth(POSTER_W)
        title_lbl.setToolTip(series_data.get("name", ""))
        lay.addWidget(title_lbl)

        # Episode tally
        total_eps = sum(len(eps) for eps in seasons.values())
        sub_lbl = QLabel(f"{total_eps} total episodes")
        sub_lbl.setStyleSheet("font-size: 10px; color: #3D5A7A;")
        lay.addWidget(sub_lbl)

        QTimer.singleShot(0, self._load_poster)

    def _load_poster(self):
        name = self.series_data.get("name", "")
        from app.core.poster_loader import poster_loader, _cache_key
        self._cache_key = _cache_key(name, None, "tv")
        cached = poster_loader.request(name, None, "tv")
        if cached and os.path.isfile(cached):
            self._set_pixmap(cached)
        else:
            poster_loader.poster_ready.connect(self._on_poster_ready)

    def _on_poster_ready(self, key: str, path: str):
        if key == getattr(self, "_cache_key", None):
            try:
                from app.core.poster_loader import poster_loader
                poster_loader.poster_ready.disconnect(self._on_poster_ready)
            except Exception:
                pass
            if path and os.path.isfile(path):
                self._set_pixmap(path)

    def _set_pixmap(self, path: str):
        pix = QPixmap(path).scaled(
            POSTER_W, POSTER_H,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.poster_lbl.setPixmap(pix)

    def mouseDoubleClickEvent(self, event):
        self.clicked.emit(self.series_data)
        super().mouseDoubleClickEvent(event)


# ── Movies Page ───────────────────────────────────────────────────────────────

class CloudPage(QWidget):
    play_requested = Signal(str, str)   # (movie_path, display_name)

    def __init__(self, queue_manager, parent=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self._folder = ""
        self._view_mode: str = "movies"  # "movies" or "series"
        self._all_items:      list[dict] = []
        self._series_groups:  dict[str, dict] = {}
        self._filtered_items: list[dict] = []
        self._filtered_series: list[dict] = []
        self._render_token: int = 0          # incremented each render; lets batches cancel themselves

        # Debounce timer — search only fires after 280ms of no typing
        self._search_debounce = QTimer(self)
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(280)
        self._search_debounce.timeout.connect(self._apply_filters)

        self._populated: bool = False

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 0, 4, 0)
        root.setSpacing(14)

        root.addWidget(self._build_header())
        root.addWidget(self._build_filter_dock())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 4, 0, 16)
        self.grid_layout.setSpacing(14)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.grid_container)
        root.addWidget(scroll, stretch=1)

        # Defer first scan to showEvent so the window is fully drawn first
        # (avoids apparent freeze during startup)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._populated:
            self._scan_and_populate()


    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        h1 = QLabel("Cloud Vault")
        h1.setProperty("role", "h1")
        h1.setFixedHeight(28)
        title_col.addWidget(h1)
        lay.addLayout(title_col)
        lay.addStretch()

        

        



        return w

    # ── Filter dock ──────────────────────────────────────────────────────────

    def _build_filter_dock(self) -> GlassCard:
        card = GlassCard()
        card.setStyleSheet(
            "QFrame#GlassCard { background-color: rgba(14,12,32,170);"
            "border: 1px solid rgba(0,240,255,22); border-radius: 14px; }"
        )
        lay = QHBoxLayout(card)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(10)

        # View mode toggle: Movies vs Series
        self._mode_btns: dict[str, QPushButton] = {}
        for key, label in [("movies", "Movies"), ("series", "Series")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background:transparent; color:#8BA8C8;"
                "  border:1px solid rgba(0,240,255,25); border-radius:8px;"
                "  padding:6px 14px; font-size:11.5px; font-weight:700; }"
                "QPushButton:hover { background:rgba(0,240,255,12); color:#E8F4FF; }"
                "QPushButton:checked { background:rgba(0,240,255,30); color:#00F0FF;"
                "  border:1px solid rgba(0,240,255,80); }"
            )
            btn.clicked.connect(lambda _, k=key: self._set_view_mode(k))
            lay.addWidget(btn)
            self._mode_btns[key] = btn
        self._mode_btns["movies"].setChecked(True)

        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: rgba(0,240,255,30);")
        lay.addWidget(sep)

        

        lay.addStretch()

        # Array Layout: Search | Refresh
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search title, year...")
        self.search_input.setFixedWidth(190)
        self.search_input.textChanged.connect(self._search_debounce.start)
        lay.addWidget(self.search_input)

        ref_btn = GhostButton("⟳  Refresh")
        ref_btn.clicked.connect(self._force_refresh)
        lay.addWidget(ref_btn)

        return card

    @staticmethod
    def _make_combo(placeholder: str) -> QComboBox:
        c = QComboBox()
        c.addItem(placeholder)
        c.setStyleSheet(
            "QComboBox { background:rgba(0,240,255,7); color:#8BA8C8;"
            "border:1px solid rgba(0,240,255,30); border-radius:8px;"
            "padding:5px 10px; font-size:11px; }"
            "QComboBox:hover { border-color:#00F0FF; color:#E8F4FF; }"
        )
        return c

    # ── Folder management ─────────────────────────────────────────────────────

    def _restore_last_folder(self):
        cfg = load_config()
        folder = cfg.get("last_movie_folder")
        if folder and os.path.isdir(folder):
            self._folder = folder
            self.folder_label.setText(os.path.basename(folder))
            self._scan_and_populate()

    def _force_refresh(self):
        """Explicitly triggered by user — always re-scans even if already populated."""
        self._populated = False
        self._scan_and_populate()

    def _scan_and_populate(self):
        self._all_items = []
        self._series_groups = {}

        # Deduplicate: keep the latest backed_up record per movie name
        seen_movies: dict[str, object] = {}
        movie_backups = list_movie_backups()
        for mb in movie_backups:
            if mb.status != 'backed_up':
                continue
            if not mb.telegram_message_ids:
                continue  # skip if no Telegram messages recorded
            # Keep the one with the most recent id (db sorted alphabetically, so last wins)
            existing = seen_movies.get(mb.movie_name)
            if existing is None or mb.id > existing.id:
                seen_movies[mb.movie_name] = mb

        for mb in seen_movies.values():
            m_raw = (mb.movie_name or "").lower()
            m_path = (mb.movie_path or "").lower()
            if any(ex in m_raw or ex in m_path for ex in ("ken park", "aroopi")):
                continue
            poster_title, year = parse_movie_title_and_year(mb.movie_name)
            display_title = f"{poster_title} ({year})" if year else poster_title
            self._all_items.append({
                "title": display_title,
                "raw_name": mb.movie_name,
                "poster_title": poster_title,   # clean title for TMDb lookup
                "year": year,                   # year string e.g. "2009" or None
                "path": mb.movie_path,
                "is_cloud": True,
                "cloud_record": mb,
            })

        # Series
        seen_series: dict[tuple, object] = {}
        series_backups = list_series_backups()
        for sb in series_backups:
            if sb.status != 'backed_up':
                continue
            if not sb.telegram_message_ids:
                continue
            key = (sb.series_name, sb.season_number, sb.episode_number)
            if key not in seen_series or sb.id > seen_series[key].id:
                seen_series[key] = sb

        for sb in seen_series.values():
            if sb.series_name not in self._series_groups:
                self._series_groups[sb.series_name] = {"name": sb.series_name, "seasons": {}, "is_cloud": True}
            s_map = self._series_groups[sb.series_name]["seasons"]
            if sb.season_number not in s_map:
                s_map[sb.season_number] = []
            s_map[sb.season_number].append(sb)

        self._populated = True
        self._apply_filters()


    def _apply_filters(self):
        query = self.search_input.text().strip().lower()

        if self._view_mode == "series":
            out_series = []
            for name, seasons in self._series_groups.items():
                if query and query not in name.lower():
                    continue
                out_series.append({"name": name, "seasons": seasons})
            self._filtered_series = sorted(out_series, key=lambda s: s["name"].lower())
            self._render_series_grid()
            return

        excluded_keywords = {"ken park", "aroopi"}
        exclude_env = os.environ.get("VAULTFATHER_EXCLUDE_TITLES", "")
        if exclude_env:
            excluded_keywords |= {k.strip().lower() for k in exclude_env.split(",") if k.strip()}

        out = []
        for item in self._all_items:
            t_low = item["title"].lower()
            r_low = item.get("raw_name", "").lower()
            p_low = item.get("path", "").lower()
            if any(k in t_low or k in r_low or k in p_low for k in excluded_keywords):
                continue
            if query:
                if query not in t_low and query not in str(item.get("year") or ""):
                    continue
            out.append(item)

        self._filtered_items = out
        self._render_grid()

    def _clear_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _render_series_grid(self):
        self._render_token += 1
        current_token = self._render_token
        self._clear_grid()

        if not self._filtered_series:
            lbl = QLabel("No TV series found in this folder. Make sure episodes follow S01E01 naming.")
            lbl.setStyleSheet("color: #3D5A7A; font-size: 13px; margin-top: 40px;")
            lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(lbl, 0, 0, 1, GRID_COLS)
            return

        items = list(self._filtered_series)
        batch_size = 15

        def _step(start_idx: int):
            if self._render_token != current_token:
                return
            end_idx = min(start_idx + batch_size, len(items))
            for idx in range(start_idx, end_idx):
                card = SeriesCardItem(items[idx])
                card.clicked.connect(self._on_series_card_clicked)
                self.grid_layout.addWidget(card, idx // GRID_COLS, idx % GRID_COLS)
            if end_idx < len(items):
                QTimer.singleShot(0, lambda: _step(end_idx))

        _step(0)

    def _on_series_card_clicked(self, series_data: dict):
        dests = [d.name for d in list_destinations()]
        name = series_data["name"]
        poster = cached_poster_path(name, None, "tv")
        dlg = SeriesQueueDialog(
            series_name=name,
            seasons=series_data["seasons"],
            destinations=dests,
            queue_manager=self.queue_manager,
            poster_path=poster,
            parent=self,
        )
        dlg.exec()

    def _render_grid(self):
        self._render_token += 1
        current_token = self._render_token
        self._clear_grid()

        if not self._filtered_items:
            lbl = QLabel("No movies found. Select a folder or clear the search filter.")
            lbl.setStyleSheet("color: #3D5A7A; font-size: 13px; margin-top: 40px;")
            lbl.setAlignment(Qt.AlignCenter)
            self.grid_layout.addWidget(lbl, 0, 0, 1, GRID_COLS)
            return

        items = list(self._filtered_items)
        batch_size = 15

        def _step(start_idx: int):
            if self._render_token != current_token:
                return
            end_idx = min(start_idx + batch_size, len(items))
            for idx in range(start_idx, end_idx):
                item = items[idx]
                card = MovieCardItem(item)
                card.play_clicked.connect(self._on_card_play)
                card.details_clicked.connect(self._on_card_details)
                self.grid_layout.addWidget(card, idx // GRID_COLS, idx % GRID_COLS)
            if end_idx < len(items):
                QTimer.singleShot(0, lambda: _step(end_idx))

        _step(0)

    # ── Card actions ──────────────────────────────────────────────────────────

    def _on_card_play(self, item_data: dict):
        if item_data.get("is_cloud"):
            self._handle_cloud_stream(item_data)
        else:
            self.play_requested.emit(
                item_data["path"],
                clean_movie_title(item_data["raw_name"])
            )

    def _on_card_details(self, item_data: dict):
        display = clean_movie_title(item_data["raw_name"])
        rec = item_data.get("cloud_record")
        size_bytes = rec.total_archive_size_bytes if rec else None
        dlg = MovieDetailsDialog(
            movie_path=item_data["path"],
            display_name=display,
            is_cloud=item_data["is_cloud"],
            cloud_record=rec,
            file_size_bytes=size_bytes,
            parent=self,
        )
        dlg.watch_requested.connect(lambda p, t: self._on_card_play(item_data))
        dlg.backup_requested.connect(self._on_backup_requested)

        dlg.exec()

    def _on_backup_requested(self, movie_path: str, display_name: str, subtitle_paths: list[str] = None):
        """Always shows destination picker — user must choose every time."""
        if not list_destinations():
            QMessageBox.warning(
                self, "No Destinations",
                "No Telegram destinations configured.\n"
                "Add one in Settings → Destinations."
            )
            return

        dlg = _DestinationPickerDialog(display_name, parent=self)
        if dlg.exec():
            dests = dlg.selected_destinations()
            if not dests:
                QMessageBox.warning(self, "No Destination Selected",
                                    "Please select at least one channel.")
                return
            self.queue_manager.add_job(movie_path, display_name, dests)
            QMessageBox.information(
                self, "Queued",
                f"'{display_name}' added to backup queue for: {', '.join(dests)}"
            )

    # ── Cloud streaming ────────────────────────────────────────────────────────

    def _handle_cloud_stream(self, item_data: dict):
        rec = item_data.get("cloud_record")
        if not rec or not rec.telegram_message_ids:
            QMessageBox.warning(self, "Unavailable", "Cloud archive references not found.")
            return

        from app.core.database import get_destination_by_name
        dest_obj = get_destination_by_name(rec.destination) if rec.destination else None
        if not dest_obj or not dest_obj.telegram_channel_id:
            QMessageBox.warning(self, "Error", f"Channel for '{rec.destination}' not accessible.")
            return

        # Use the pre-configured download folder from Settings; fall back to picker
        cfg_dir = load_config().get("telegram_movie_download_dir") or ""
        if cfg_dir and os.path.isdir(cfg_dir):
            out_dir = cfg_dir
        else:
            out_dir = QFileDialog.getExistingDirectory(self, "Save Download To…")
            if not out_dir:
                return

        from app.core.download_manager import DownloadManager
        dm = DownloadManager.instance()
        try:
            dm.start_download(
                job_name=item_data['title'],
                channel_id=dest_obj.telegram_channel_id,
                message_ids=rec.telegram_message_ids,
                password=rec.password,
                output_dir=out_dir
            )
            QMessageBox.information(
                self, "Download Started",
                f"Download started for '{item_data['title']}'.\n"
                f"Saving to: {out_dir}\n\nCheck the Dashboard for progress."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Download Error", str(exc))

