"""
Subtitles Studio Page — Cyber Obsidian Glass.

Displays all movies in your library with their subtitle status:
  • 🟢 SUBBED (has companion subtitle or embedded track)
  • 🟡 NO SUBTITLES (needs subtitle matching)

Clicking any movie card opens the SubtitleStudioDialog for searching,
previewing in VLC, and lossless remuxing.
"""

import os
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFileDialog,
    QScrollArea, QPushButton, QLineEdit, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap

from app.theme.tokens import Colors
from app.ui.widgets.glass_card import GlassCard
from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.ui.dialogs.subtitle_studio_dialog import SubtitleStudioDialog
from app.core.movie_scanner import scan_movies, human_size
from app.core.config import load_config, save_config
from app.core.title_cleaner import clean_movie_title, parse_movie_title_and_year
from app.core.poster_service import cached_poster_path, fetch_poster
from app.core.poster_loader import poster_loader, _cache_key
from app.core.subtitle_detector import detect_subtitles

GRID_COLS = 5
POSTER_W = 168
POSTER_H = 230
CARD_W = POSTER_W + 16
CARD_H = POSTER_H + 64


class SubtitleMovieCard(GlassCard):
    """Movie card in Subtitles Studio showing subtitle status badge."""
    card_clicked = Signal(object)

    def __init__(self, movie_data: dict, parent=None):
        super().__init__(parent)
        self.movie_data = movie_data
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

        # Poster container
        self._poster_container = QFrame()
        self._poster_container.setFixedSize(POSTER_W, POSTER_H)
        self._poster_container.setStyleSheet("background: transparent;")

        self.poster_lbl = QLabel(self._poster_container)
        self.poster_lbl.setFixedSize(POSTER_W, POSTER_H)
        self.poster_lbl.setAlignment(Qt.AlignCenter)
        self.poster_lbl.setScaledContents(False)
        self.poster_lbl.setStyleSheet("background-color: #0B0A18; border-radius: 9px; color: #3D5A7A;")
        self.poster_lbl.setText("🎬")

        # Subtitle Status Badge (top-left)
        has_sub = movie_data.get("has_sub", False)
        if has_sub:
            badge_text = "🟢 SUBBED"
            badge_style = "background: rgba(53, 240, 166, 210); color: #080714; font-size: 8.5px; font-weight: 800; padding: 2px 6px; border-radius: 4px;"
        else:
            badge_text = "🟡 NO SUBTITLE"
            badge_style = "background: rgba(255, 184, 108, 210); color: #080714; font-size: 8.5px; font-weight: 800; padding: 2px 6px; border-radius: 4px;"

        self.sub_badge = QLabel(badge_text, self._poster_container)
        self.sub_badge.setStyleSheet(badge_style)
        self.sub_badge.adjustSize()
        self.sub_badge.move(8, 8)
        self.sub_badge.raise_()

        # Format badge (top-right)
        ext_text = Path(movie_data["path"]).suffix.upper().lstrip(".")
        self.ext_badge = QLabel(ext_text, self._poster_container)
        self.ext_badge.setStyleSheet(
            "background: rgba(0, 240, 255, 180); color: #080714; "
            "font-size: 8.5px; font-weight: 800; padding: 2px 5px; border-radius: 4px;"
        )
        self.ext_badge.adjustSize()
        self.ext_badge.move(POSTER_W - self.ext_badge.width() - 8, 8)
        self.ext_badge.raise_()

        lay.addWidget(self._poster_container)

        # Title
        self.title_lbl = QLabel(movie_data["title"])
        self.title_lbl.setStyleSheet("font-size: 11.5px; font-weight: 700; color: #E8F4FF;")
        self.title_lbl.setWordWrap(False)
        self.title_lbl.setFixedHeight(16)
        lay.addWidget(self.title_lbl)

        # Meta (Year, Size)
        year_str = f" · {movie_data['year']}" if movie_data.get("year") else ""
        meta_txt = f"{movie_data.get('size_human', '')}{year_str}"
        self.meta_lbl = QLabel(meta_txt)
        self.meta_lbl.setStyleSheet("font-size: 10px; color: #8BA8C8;")
        lay.addWidget(self.meta_lbl)

        # Load poster asynchronously via shared poster_loader (linked with Movies tab)
        QTimer.singleShot(0, self._load_poster)

    def _load_poster(self):
        title = self.movie_data.get("raw_title", self.movie_data.get("title"))
        year = self.movie_data.get("year")
        self._cache_key = _cache_key(title, year, "movie")
        cached = poster_loader.request(title, year, "movie")
        if cached and os.path.isfile(cached):
            self._set_pixmap(cached)
        else:
            poster_loader.poster_ready.connect(self._on_poster_ready)

    def _on_poster_ready(self, key: str, path: str):
        if key == getattr(self, "_cache_key", None):
            try:
                poster_loader.poster_ready.disconnect(self._on_poster_ready)
            except Exception:
                pass
            if path and os.path.isfile(path):
                self._set_pixmap(path)

    def _set_pixmap(self, path: str):
        pix = QPixmap(path).scaled(POSTER_W, POSTER_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.poster_lbl.setPixmap(pix)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.card_clicked.emit(self.movie_data)
        super().mousePressEvent(event)


class SubtitlesPage(QWidget):
    """Subtitles Studio main tab view."""
    scan_completed = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SubtitlesPage")
        self._all_movies: list[dict] = []
        self._filtered_movies: list[dict] = []
        self._current_filter: str = "all"  # all | missing | subbed
        self._current_folder: str = ""
        self._active_dialog: SubtitleStudioDialog | None = None

        self.scan_completed.connect(self._on_scan_finished)

        self._search_debounce = QTimer()
        self._search_debounce.setSingleShot(True)
        self._search_debounce.setInterval(220)
        self._search_debounce.timeout.connect(self._apply_filters)

        self._build_ui()
        QTimer.singleShot(100, self._scan_and_populate)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        # Header Title
        top_bar = QHBoxLayout()
        header_vbox = QVBoxLayout()
        header_vbox.setSpacing(3)

        title = QLabel("SUBTITLES STUDIO")
        title.setStyleSheet("font-size: 20px; font-weight: 900; color: #00F0FF; letter-spacing: 2px;")
        header_vbox.addWidget(title)

        subtitle = QLabel("Search, sync with VLC, and losslessly embed soft subtitles with 0% quality loss.")
        subtitle.setStyleSheet("font-size: 12px; color: #8BA8C8;")
        header_vbox.addWidget(subtitle)

        top_bar.addLayout(header_vbox)
        top_bar.addStretch()

        self.stats_pill = QLabel("Scanning library...")
        self.stats_pill.setStyleSheet(
            "background: rgba(0, 240, 255, 20); border: 1px solid rgba(0, 240, 255, 50); "
            "color: #00F0FF; font-size: 11px; font-weight: 700; border-radius: 8px; padding: 6px 14px;"
        )
        top_bar.addWidget(self.stats_pill)
        root.addLayout(top_bar)

        # Filter & Action Control Card
        control_card = GlassCard()
        ctrl_lay = QHBoxLayout(control_card)
        ctrl_lay.setContentsMargins(14, 10, 14, 10)
        ctrl_lay.setSpacing(10)

        self._filter_btns = {}
        for key, label in [("all", "All Movies"), ("missing", "🟡 Missing Subtitles"), ("subbed", "🟢 Subbed")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: rgba(0,240,255,8); color: #8BA8C8;"
                "  border: 1px solid rgba(0,240,255,25); border-radius: 8px; padding: 6px 14px; font-size: 11px; font-weight: 600; }"
                "QPushButton:checked { background: rgba(0,240,255,30); color: #00F0FF; border-color: #00F0FF; }"
            )
            btn.clicked.connect(lambda _, k=key: self._set_filter(k))
            ctrl_lay.addWidget(btn)
            self._filter_btns[key] = btn
        self._filter_btns["all"].setChecked(True)

        ctrl_lay.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search title...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(
            "QLineEdit { background: rgba(0,240,255,8); color: #E8F4FF; border: 1px solid rgba(0,240,255,30); "
            "border-radius: 8px; padding: 6px 12px; font-size: 12px; }"
        )
        self.search_input.textChanged.connect(self._search_debounce.start)
        ctrl_lay.addWidget(self.search_input)

        ref_btn = GhostButton("⟳  Refresh")
        ref_btn.clicked.connect(self._scan_and_populate)
        ctrl_lay.addWidget(ref_btn)

        folder_btn = GhostButton("Select Folder")
        folder_btn.clicked.connect(self._select_folder)
        ctrl_lay.addWidget(folder_btn)

        root.addWidget(control_card)

        # Movies Grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(0, 4, 0, 16)
        self.grid_layout.setSpacing(14)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.scroll.setWidget(self.grid_container)
        root.addWidget(self.scroll, stretch=1)

    def _set_filter(self, filter_key: str):
        self._current_filter = filter_key
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == filter_key)
        self._apply_filters()

    def _get_active_folder(self) -> str:
        cfg = load_config()
        folder = cfg.get("last_movie_folder") or cfg.get("movies_directory", "")
        return folder if (folder and os.path.isdir(folder)) else ""

    def showEvent(self, event):
        super().showEvent(event)
        folder = self._get_active_folder()
        if folder != self._current_folder or not self._all_movies:
            self._scan_and_populate()

    def _select_folder(self):
        curr = self._get_active_folder()
        folder = QFileDialog.getExistingDirectory(self, "Select Movie Library Folder", curr)
        if folder:
            cfg = load_config()
            cfg["last_movie_folder"] = folder
            cfg["movies_directory"] = folder
            save_config(cfg)
            self._scan_and_populate()

    def _scan_and_populate(self):
        folder = self._get_active_folder()
        if not folder:
            self.stats_pill.setText("No movie folder selected")
            return

        if getattr(self, "_is_scanning", False):
            return
        self._is_scanning = True

        self._current_folder = folder
        self.stats_pill.setText("Scanning library...")

        def _worker():
            try:
                raw_movies = scan_movies(folder)
                movie_list = []
                for m in raw_movies:
                    clean_t, yr = parse_movie_title_and_year(m.name)
                    subs = detect_subtitles(m.path)
                    has_sub = len(subs) > 0

                    movie_list.append({
                        "path": m.path,
                        "raw_name": m.name,
                        "title": clean_t,
                        "raw_title": clean_t,
                        "year": yr,
                        "size_human": m.size_human,
                        "size_bytes": m.size_bytes,
                        "has_sub": has_sub,
                        "subs": subs,
                    })

                self.scan_completed.emit(movie_list)
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_scan_finished(self, movie_list: list[dict]):
        self._is_scanning = False
        self._all_movies = movie_list
        subbed_cnt = sum(1 for m in movie_list if m["has_sub"])
        missing_cnt = len(movie_list) - subbed_cnt
        self.stats_pill.setText(f"{len(movie_list)} Movies · {subbed_cnt} Subbed · {missing_cnt} Missing")
        self._apply_filters()

    def _apply_filters(self):
        # Clear grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        query = self.search_input.text().strip().lower()
        self._filtered_movies = []

        for m in self._all_movies:
            if query and query not in m["title"].lower():
                continue
            if self._current_filter == "missing" and m["has_sub"]:
                continue
            if self._current_filter == "subbed" and not m["has_sub"]:
                continue
            self._filtered_movies.append(m)

        for idx, m in enumerate(self._filtered_movies):
            row = idx // GRID_COLS
            col = idx % GRID_COLS
            card = SubtitleMovieCard(m)
            card.card_clicked.connect(self._open_subtitle_studio)
            self.grid_layout.addWidget(card, row, col)

    def _open_subtitle_studio(self, movie_data: dict):
        dialog = SubtitleStudioDialog(movie_data["path"], movie_data["title"], self)
        self._active_dialog = dialog
        if dialog.exec():
            # Refresh card list if subtitle was embedded/saved
            self._scan_and_populate()
