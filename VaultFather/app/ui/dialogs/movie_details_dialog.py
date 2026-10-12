"""
Cyber Obsidian Movie Details Modal:
Displays full plot synopsis, IMDb ratings, Director, Cast, Genres,
direct clickable links to IMDb & Letterboxd, with 1-click Watch and Backup triggers.
"""

import os
import webbrowser
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QScrollArea, QFrame, QCheckBox
)
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap, QDesktopServices

from app.core.movie_metadata import fetch_movie_metadata, MovieMetadata
from app.core.poster_service import cached_poster_path
from app.core.movie_scanner import human_size
from app.ui.widgets.glass_card import GlassCard
from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.theme.tokens import Colors


class MovieDetailsDialog(QDialog):
    watch_requested = Signal(str, str)   # (movie_path, title)
    backup_requested = Signal(str, str, list)  # (movie_path, title, subtitle_paths)

    def __init__(self, movie_path: str, display_name: str, is_cloud: bool = False,
                 cloud_record=None, file_size_bytes: int | None = None, parent=None):
        super().__init__(parent)
        self.movie_path = movie_path
        self.display_name = display_name
        self.is_cloud = is_cloud
        self.cloud_record = cloud_record
        self.file_size_bytes = file_size_bytes

        self.setWindowTitle(f"VaultFather — {display_name}")
        self.setMinimumSize(680, 520)
        self.setStyleSheet(
            "QDialog { background-color: #0B0A14; }"
            "QLabel { color: #F3F1FF; font-family: 'Inter', 'Segoe UI', sans-serif; }"
        )

        self._meta: MovieMetadata = fetch_movie_metadata(display_name)
        self._init_ui()


    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(18)

        # Header Hero Card
        header_card = GlassCard()
        header_card.setStyleSheet(
            "QFrame#GlassCard { background-color: rgba(22, 19, 48, 200); border: 1px solid rgba(51,230,255,50); border-radius: 18px; }"
        )
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(18, 18, 18, 18)
        h_layout.setSpacing(18)

        # Poster Image
        self.poster_lbl = QLabel()
        self.poster_lbl.setFixedSize(110, 160)
        self.poster_lbl.setStyleSheet("background-color: rgba(10,9,24,180); border-radius: 12px; border: 1px solid rgba(150,130,255,40);")
        self.poster_lbl.setAlignment(Qt.AlignCenter)
        self._load_poster()
        h_layout.addWidget(self.poster_lbl)

        # Info Column
        info_col = QVBoxLayout()
        info_col.setSpacing(6)

        title_row = QHBoxLayout()
        title_lbl = QLabel(self._meta.title)
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #F3F1FF;")
        title_row.addWidget(title_lbl)

        if self._meta.year:
            year_lbl = QLabel(f"({self._meta.year})")
            year_lbl.setStyleSheet("font-size: 16px; color: #33E6FF; font-weight: 600;")
            title_row.addWidget(year_lbl)
        title_row.addStretch()
        info_col.addLayout(title_row)

        # Chips row
        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)

        # Rating chip
        if self._meta.rating > 0:
            rating_chip = QLabel(f"★ {self._meta.rating_formatted} / 10")
            rating_chip.setStyleSheet("background: rgba(255,179,71,30); color: #FFB347; font-weight: 700; padding: 4px 10px; border-radius: 8px; font-size: 11.5px;")
            chips_row.addWidget(rating_chip)

        # Location status chip
        if self.is_cloud:
            loc_chip = QLabel("CLOUD VAULT")
            loc_chip.setStyleSheet("background: rgba(51,230,255,30); color: #33E6FF; font-weight: 700; padding: 4px 10px; border-radius: 8px; font-size: 11.5px;")
        else:
            loc_chip = QLabel("LOCAL STORAGE")
            loc_chip.setStyleSheet("background: rgba(53,240,166,30); color: #35F0A6; font-weight: 700; padding: 4px 10px; border-radius: 8px; font-size: 11.5px;")
        chips_row.addWidget(loc_chip)

        # File size chip
        if self.file_size_bytes and self.file_size_bytes > 0:
            size_chip = QLabel(human_size(self.file_size_bytes))
            size_chip.setStyleSheet(
                "background: rgba(0,240,255,12); color: #8BA8C8; font-weight: 600; "
                "padding: 4px 10px; border-radius: 8px; font-size: 11.5px; "
                "border: 1px solid rgba(0,240,255,25);"
            )
            chips_row.addWidget(size_chip)

        # Genres chip
        genres_chip = QLabel(self._meta.genres_formatted)
        genres_chip.setStyleSheet("background: rgba(123,47,247,30); color: #B3ACD9; padding: 4px 10px; border-radius: 8px; font-size: 11.5px;")
        chips_row.addWidget(genres_chip)

        chips_row.addStretch()
        info_col.addLayout(chips_row)

        # Director & Cast
        credits_lbl = QLabel(f"Director: <b style='color:#F3F1FF;'>{self._meta.director}</b>  ·  Language: <b style='color:#F3F1FF;'>{self._meta.language}</b>")
        credits_lbl.setStyleSheet("color: #B3ACD9; font-size: 12px;")
        info_col.addWidget(credits_lbl)

        if self._meta.cast:
            cast_lbl = QLabel(f"Starring: <span style='color:#B3ACD9;'>{', '.join(self._meta.cast[:4])}</span>")
            cast_lbl.setStyleSheet("font-size: 11.5px; color: #6E6795;")
            info_col.addWidget(cast_lbl)

        # Web Links row (IMDb / Letterboxd)
        links_row = QHBoxLayout()
        links_row.setSpacing(10)

        if self._meta.imdb_url:
            imdb_btn = QPushButton("IMDb Page")
            imdb_btn.setCursor(Qt.PointingHandCursor)
            imdb_btn.setStyleSheet("background: rgba(245,197,24,25); color: #F5C518; border: 1px solid rgba(245,197,24,60); border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 600;")
            imdb_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._meta.imdb_url)))
            links_row.addWidget(imdb_btn)

        letterboxd_btn = QPushButton("Letterboxd")
        letterboxd_btn.setCursor(Qt.PointingHandCursor)
        letterboxd_btn.setStyleSheet("background: rgba(0,224,84,25); color: #00E054; border: 1px solid rgba(0,224,84,60); border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 600;")
        letterboxd_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._meta.letterboxd_url)))
        links_row.addWidget(letterboxd_btn)

        links_row.addStretch()
        info_col.addLayout(links_row)

        h_layout.addLayout(info_col, stretch=1)
        root.addWidget(header_card)

        # Plot Overview section
        plot_card = GlassCard()
        plot_card.setStyleSheet("QFrame#GlassCard { background-color: rgba(18,16,38,160); border: 1px solid rgba(150,130,255,25); border-radius: 14px; }")
        p_layout = QVBoxLayout(plot_card)
        p_layout.setContentsMargins(16, 14, 16, 14)
        p_layout.setSpacing(6)

        plot_title = QLabel("SYNOPSIS")
        plot_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #33E6FF; letter-spacing: 1px;")
        p_layout.addWidget(plot_title)

        p_layout.addSpacing(4)
        plot_text = QLabel(self._meta.plot)
        plot_text.setWordWrap(True)
        plot_text.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        plot_text.setStyleSheet("font-size: 12.5px; color: #B3ACD9; line-height: 1.4;")
        p_layout.addWidget(plot_text)
        
        # Subtitles detection (only for local files)
        self.subtitle_checkboxes = []
        if not self.is_cloud:
            from app.core.subtitle_detector import detect_subtitles
            detected_subs = detect_subtitles(self.movie_path)
            if detected_subs:
                p_layout.addSpacing(8)
                sub_title = QLabel("DETECTED SUBTITLES")
                sub_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #35F0A6; letter-spacing: 1px;")
                p_layout.addWidget(sub_title)
                
                for sub_path in detected_subs:
                    cb = QCheckBox(os.path.basename(sub_path))
                    cb.setStyleSheet(
                        "QCheckBox { color: #B3ACD9; font-size: 12px; }"
                        "QCheckBox::indicator { width: 14px; height: 14px; border-radius: 3px; border: 1px solid #6E6795; background: rgba(0,0,0,0.3); }"
                        "QCheckBox::indicator:checked { background: #35F0A6; border: 1px solid #35F0A6; }"
                    )
                    cb.setChecked(True)  # Default to backing up found subtitles
                    cb.setProperty("sub_path", sub_path)
                    self.subtitle_checkboxes.append(cb)
                    p_layout.addWidget(cb)
        
        root.addWidget(plot_card, stretch=1)

        # Action Buttons Row
        act_row = QHBoxLayout()
        act_row.setSpacing(12)

        # Watch / Stream Button
        watch_btn_text = "Watch Now" if not self.is_cloud else "Download & Restore"
        self.watch_btn = PrimaryButton(watch_btn_text)
        self.watch_btn.setCursor(Qt.PointingHandCursor)
        self.watch_btn.clicked.connect(self._on_watch_clicked)
        act_row.addWidget(self.watch_btn)

        # Backup Button
        if not self.is_cloud:
            self.backup_btn = GhostButton("Fast Backup to Telegram")
            self.backup_btn.setCursor(Qt.PointingHandCursor)
            self.backup_btn.clicked.connect(self._on_backup_clicked)
            act_row.addWidget(self.backup_btn)

        act_row.addStretch()

        close_btn = GhostButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        act_row.addWidget(close_btn)

        root.addLayout(act_row)

    def _load_poster(self):
        from app.core.title_cleaner import parse_movie_title_and_year
        title, year = parse_movie_title_and_year(self.display_name)
        cached = cached_poster_path(title, year, "movie")
        if cached and os.path.isfile(cached):
            pix = QPixmap(cached).scaled(110, 160, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.poster_lbl.setPixmap(pix)
        else:
            self.poster_lbl.setText("")
            self.poster_lbl.setStyleSheet("color: #6E6795; font-size: 32px; background-color: rgba(10,9,24,180);")

    def _on_watch_clicked(self):
        self.accept()
        self.watch_requested.emit(self.movie_path, self.display_name)

    def _on_backup_clicked(self):
        self.accept()
        selected_subs = [cb.property("sub_path") for cb in self.subtitle_checkboxes if cb.isChecked()]
        self.backup_requested.emit(self.movie_path, self.display_name, selected_subs)