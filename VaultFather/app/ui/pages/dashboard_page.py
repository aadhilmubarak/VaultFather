"""
Dashboard Page — Futuristic Spacecraft Command Dashboard UI.
Inspired by Imran Jakir's Spacecraft UI on Dribbble.

Key Features:
  • Unwatched Movies Wishlist Vault (replaces sinewave canvas) with TMDb posters
    and 📋 Copy button (copies title + year in clean alphanumeric characters to clipboard).
  • Last Viewed Movie poster card with correct poster lookup and cyan watched progress line.
  • Slidable Upload Speed telemetry chart (Stock Market style timeline scrubber).
  • Transparent Glass Panels over Dynamic Movie Backdrops (7s rotation).
  • HUD Spotlights for current backdrop movie with plot summary and IMDb hyperlink.
  • Transmission Queue with Refresh button (clears failed uploads) and 3-dots (⋮) options menu.
"""

import os
import re
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QFrame,
    QScrollArea, QSlider, QPushButton, QProgressBar, QApplication, QMessageBox,
    QDialog
)
from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QSize
from PySide6.QtGui import (
    QPainter, QColor, QPen, QLinearGradient, QFont, QDesktopServices, QPixmap
)

from app.ui.widgets.glass_card import GlassCard
from app.ui.widgets.buttons import GhostButton, PrimaryButton
from app.ui.widgets.progress_ring import ProgressRing
from app.ui.widgets.queue_row import QueueRow
from app.ui.widgets.upload_stock_chart import SlidableStockHistoryWidget
from app.core.database import list_backups, get_last_viewed_movie, list_unwatched_movies, delete_unwatched_movie
from app.core.unwatched_sync import sync_unwatched_channel_async
from app.core.movie_scanner import human_size
from app.core.upload_history_tracker import UploadHistoryTracker
from app.core.poster_service import cached_poster_path, fetch_poster
from app.core.movie_metadata import fetch_movie_metadata as _fetch_full_metadata
from app.core.title_cleaner import clean_movie_title, parse_movie_title_and_year

RUNNING_STATES = ("archiving", "uploading")
ACTIVE_STATES  = ("queued", *RUNNING_STATES)


def _human_speed(bps: float) -> str:
    if bps <= 0:
        return "—"
    return f"{human_size(bps)}/s"


def _to_alphanumeric(title: str, year: str | None = None) -> str:
    """Converts movie title and year into clean alphanumeric characters for easy clipboard copy."""
    combined = f"{title} {year or ''}".strip()
    clean = re.sub(r"[^a-zA-Z0-9\s]", "", combined)
    return re.sub(r"\s+", " ", clean).strip()


class _StatCard(GlassCard):
    """Futuristic Glass Stat Card with glowing top accent."""

    def __init__(self, caption: str, accent_color: str = "#00F0FF", parent=None):
        super().__init__(parent, accent=True)
        self._accent_color = accent_color

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)

        self._value_lbl = QLabel("—")
        self._value_lbl.setProperty("role", "statValue")
        self._value_lbl.setStyleSheet(f"color: {accent_color};")
        self._value_lbl.setFont(QFont("Space Grotesk", 24, QFont.Bold))

        self._caption_lbl = QLabel(caption)
        self._caption_lbl.setProperty("role", "caption")
        self._caption_lbl.setStyleSheet("color: #8BA8C8; font-size: 11px;")

        lay.addWidget(self._value_lbl)
        lay.addWidget(self._caption_lbl)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, text: str):
        self._value_lbl.setText(text)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), 0)
        c = QColor(self._accent_color)
        c.setAlpha(0)
        grad.setColorAt(0.0, c)
        c2 = QColor(self._accent_color)
        c2.setAlpha(160)
        grad.setColorAt(0.4, c2)
        c3 = QColor(self._accent_color)
        c3.setAlpha(0)
        grad.setColorAt(1.0, c3)
        p.fillRect(0, 0, self.width(), 3, grad)


class LastViewedMovieCard(GlassCard):
    """
    Dashboard card displaying the last viewed movie as a poster card
    with a progress bar line at the bottom showing how much of the movie was watched.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(205)
        self.setStyleSheet("QFrame#GlassCard { background: rgba(14, 12, 32, 175); border: 1px solid rgba(0,240,255,30); border-radius: 12px; }")
        self.movie_path: str = ""

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        head = QLabel("RECENTLY VIEWED MOVIE")
        head.setStyleSheet("font-size: 10.5px; font-weight: 700; color: #00FFC8; letter-spacing: 0.5px;")
        lay.addWidget(head)

        # Poster container frame with bottom progress line
        self.poster_frame = QFrame()
        self.poster_frame.setFixedSize(181, 165)
        self.poster_frame.setStyleSheet("background: rgba(0,0,0,90); border-radius: 8px;")
        pf_lay = QVBoxLayout(self.poster_frame)
        pf_lay.setContentsMargins(0, 0, 0, 0)
        pf_lay.setSpacing(0)

        self.poster_img = QLabel(self.poster_frame)
        self.poster_img.setFixedSize(181, 140)
        self.poster_img.setAlignment(Qt.AlignCenter)
        self.poster_img.setStyleSheet("border-top-left-radius: 8px; border-top-right-radius: 8px; font-size: 32px; color: #3D5A7A;")
        self.poster_img.setText("🎬")
        pf_lay.addWidget(self.poster_img)

        # Progress bar container at the bottom of the poster
        self.prog_bar_bg = QFrame(self.poster_frame)
        self.prog_bar_bg.setFixedHeight(25)
        self.prog_bar_bg.setStyleSheet("background: rgba(8, 6, 20, 240); border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;")
        pb_lay = QVBoxLayout(self.prog_bar_bg)
        pb_lay.setContentsMargins(6, 3, 6, 3)
        pb_lay.setSpacing(2)

        self.prog_lbl = QLabel("0% watched", self.prog_bar_bg)
        self.prog_lbl.setStyleSheet("font-size: 9px; font-weight: 700; color: #00F0FF;")
        pb_lay.addWidget(self.prog_lbl)

        # Cyan glowing watched line at bottom
        self.watched_bar = QProgressBar(self.prog_bar_bg)
        self.watched_bar.setFixedHeight(4)
        self.watched_bar.setRange(0, 100)
        self.watched_bar.setValue(0)
        self.watched_bar.setTextVisible(False)
        self.watched_bar.setStyleSheet(
            "QProgressBar { background: rgba(0,240,255,20); border: none; border-radius: 2px; } "
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #00F0FF,stop:1 #00FFC8); border-radius: 2px; }"
        )
        pb_lay.addWidget(self.watched_bar)

        pf_lay.addWidget(self.prog_bar_bg)
        lay.addWidget(self.poster_frame, alignment=Qt.AlignCenter)

        self.title_lbl = QLabel("No playback history")
        self.title_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #E8F4FF;")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.title_lbl)

        self.play_btn = QPushButton("▶ Resume in VLC")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.setStyleSheet(
            "QPushButton { background: rgba(0,240,255,22); color: #00F0FF; border: 1px solid rgba(0,240,255,60); "
            "border-radius: 6px; padding: 4px 8px; font-size: 10px; font-weight: 700; } "
            "QPushButton:hover { background: rgba(0,240,255,45); color: #FFF; }"
        )
        self.play_btn.clicked.connect(self._on_play_clicked)
        self.play_btn.setVisible(False)
        lay.addWidget(self.play_btn)

        self.refresh_last_viewed()

    def refresh_last_viewed(self):
        if os.environ.get("VAULTFATHER_DEMO_DASHBOARD") == "1":
            self.title_lbl.setText("Interstellar (2014)")
            self.play_btn.setVisible(True)
            self.watched_bar.setValue(68)
            self.prog_lbl.setText("68% watched (115m / 169m)")
            poster_file = cached_poster_path("Interstellar", "2014", "movie")
            if poster_file and os.path.isfile(poster_file):
                pix = QPixmap(poster_file).scaled(181, 140, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self.poster_img.setPixmap(pix)
            return

        data = get_last_viewed_movie()
        if not data or not data.get("movie_path"):
            self.title_lbl.setText("No recent playback")
            self.prog_lbl.setText("0% watched")
            self.watched_bar.setValue(0)
            self.play_btn.setVisible(False)
            self.poster_img.setText("🎬")
            return

        path = data["movie_path"]
        self.movie_path = path
        filename = os.path.basename(path)

        # Accurately parse title and year for TMDb poster lookup
        title, year = parse_movie_title_and_year(filename)
        display_title = clean_movie_title(filename)
        self.title_lbl.setText(display_title)
        self.play_btn.setVisible(True)

        pos = data.get("position_seconds", 0)
        dur = data.get("duration_seconds", 0)
        if dur > 0:
            pct = min(100, max(0, int((pos / dur) * 100)))
            self.watched_bar.setValue(pct)
            pos_m = int(pos // 60)
            dur_m = int(dur // 60)
            self.prog_lbl.setText(f"{pct}% watched ({pos_m}m / {dur_m}m)")
        else:
            self.watched_bar.setValue(0)
            self.prog_lbl.setText("Recently Opened")

        # Check poster with exact title and year
        poster_file = cached_poster_path(title, year, "movie")
        if poster_file and os.path.isfile(poster_file):
            pix = QPixmap(poster_file).scaled(181, 140, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.poster_img.setPixmap(pix)
        else:
            self.poster_img.setText("🎬")
            def _fetch():
                try:
                    pf = fetch_poster(title, year, "movie")
                    if pf and os.path.isfile(pf):
                        pix2 = QPixmap(pf).scaled(181, 140, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        self.poster_img.setPixmap(pix2)
                except (RuntimeError, AttributeError):
                    pass
            QTimer.singleShot(50, _fetch)

    def _on_play_clicked(self):
        if self.movie_path and os.path.isfile(self.movie_path):
            from app.core.vlc_launcher import play_in_vlc
            play_in_vlc(self.movie_path)


class UnwatchedPosterCard(QFrame):
    """Poster card for an unwatched movie in the Unwatched channel wishlist."""

    card_clicked = Signal(int, str, str)   # movie_id, title, year
    copied = Signal(str)

    def __init__(self, movie_id: int, title: str, year: str | None = None, parent=None):
        super().__init__(parent)
        self.movie_id = movie_id
        self.title = title
        self.year = year
        self.setFixedSize(115, 175)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame { background: rgba(14, 11, 32, 210); border: 1px solid rgba(0,240,255,30); border-radius: 8px; }"
            "QFrame:hover { border: 1px solid rgba(0,240,255,80); }"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # Poster container frame
        self.poster_container = QFrame(self)
        self.poster_container.setFixedSize(107, 132)
        pc_lay = QVBoxLayout(self.poster_container)
        pc_lay.setContentsMargins(0, 0, 0, 0)

        self.poster_lbl = QLabel(self.poster_container)
        self.poster_lbl.setFixedSize(107, 132)
        self.poster_lbl.setAlignment(Qt.AlignCenter)
        self.poster_lbl.setStyleSheet("font-size: 24px; color: #3D5A7A; border-radius: 6px;")
        self.poster_lbl.setText("[ ]")
        pc_lay.addWidget(self.poster_lbl)

        lay.addWidget(self.poster_container)

        # Title label
        clean_text = f"{title} ({year})" if year else title
        title_lbl = QLabel(clean_text)
        title_lbl.setStyleSheet("font-size: 9.5px; font-weight: 700; color: #E8F4FF;")
        title_lbl.setWordWrap(True)
        title_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(title_lbl)

        QTimer.singleShot(10, self._load_poster)

    def _load_poster(self):
        cached = cached_poster_path(self.title, self.year, "movie")
        if cached and os.path.isfile(cached):
            pix = QPixmap(cached).scaled(107, 132, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            try:
                self.poster_lbl.setPixmap(pix)
            except (RuntimeError, AttributeError):
                pass
        else:
            def _fetch():
                try:
                    pf = fetch_poster(self.title, self.year, "movie")
                    if pf and os.path.isfile(pf):
                        # QPixmap must be created on the main thread — schedule via QTimer
                        def _apply():
                            try:
                                pix2 = QPixmap(pf).scaled(
                                    107, 132, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                                )
                                self.poster_lbl.setPixmap(pix2)
                            except (RuntimeError, AttributeError):
                                pass
                        QTimer.singleShot(0, _apply)
                except Exception:
                    pass
            import threading
            threading.Thread(target=_fetch, daemon=True).start()


    def _copy_to_clipboard(self):
        alpha_text = _to_alphanumeric(self.title, self.year)
        QApplication.clipboard().setText(alpha_text)
        self.copied.emit(alpha_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.card_clicked.emit(self.movie_id, self.title, self.year or "")
        super().mousePressEvent(event)



class UnwatchedMoviesCard(GlassCard):
    """
    Card replacing the sine wave telemetry canvas: displays unwatched movies
    from the Telegram Unwatched channel with TMDb posters and a 📋 copy icon.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QFrame#GlassCard { background: rgba(14, 12, 32, 175); border: 1px solid rgba(0,240,255,25); border-radius: 12px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("UNWATCHED MOVIES // TELEGRAM WISHLIST")
        title.setStyleSheet("font-size: 11px; font-weight: 700; color: #00F0FF; letter-spacing: 0.5px;")
        head.addWidget(title)
        head.addStretch()

        self.toast_lbl = QLabel("")
        self.toast_lbl.setStyleSheet("font-size: 10px; color: #8BA8C8; font-weight: 600;")
        head.addWidget(self.toast_lbl)
        lay.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(185)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.scroll_content = QWidget()
        self.cards_layout = QHBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.cards_layout.addStretch()

        scroll.setWidget(self.scroll_content)
        lay.addWidget(scroll)

        self.refresh_unwatched()

    def refresh_unwatched(self):
        """
        Step 1 – render whatever is already in the local DB immediately.
        Step 2 – kick off a background Telegram sync; repopulate when done.
        """
        if os.environ.get("VAULTFATHER_DEMO_DASHBOARD") == "1":
            gems = [
                {"id": 101, "title": "Coherence", "year": "2013"},
                {"id": 102, "title": "The Fall", "year": "2006"},
                {"id": 103, "title": "Incendies", "year": "2010"},
                {"id": 104, "title": "The Man from Earth", "year": "2007"},
                {"id": 105, "title": "Nightcrawler", "year": "2014"},
                {"id": 106, "title": "Memories of Murder", "year": "2003"},
                {"id": 107, "title": "Perfect Blue", "year": "1997"},
                {"id": 108, "title": "Moon", "year": "2009"},
                {"id": 109, "title": "Locke", "year": "2013"},
                {"id": 110, "title": "Cure", "year": "1997"},
                {"id": 111, "title": "Oldboy", "year": "2003"},
            ]
            self._render_cards(gems)
            self.toast_lbl.setText("✔ 11 gems synced")
            self.toast_lbl.setStyleSheet("font-size: 10px; color: #00FFC8; font-weight: 700;")
            return

        self._render_cards(list_unwatched_movies())
        self.toast_lbl.setText("⟳ Syncing from Telegram…")
        self.toast_lbl.setStyleSheet("font-size: 10px; color: #8BA8C8; font-weight: 600;")

        def _on_done(count: int):
            QTimer.singleShot(0, lambda: self._after_sync(count))

        def _on_error(msg: str):
            QTimer.singleShot(0, lambda: self._after_sync_error(msg))

        sync_unwatched_channel_async(on_done=_on_done, on_error=_on_error)

    def _render_cards(self, items: list):
        # Clear existing card widgets (keep trailing stretch)
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not items:
            placeholder = QLabel("No movies yet — connect your Telegram Unwatched channel in Settings.")
            placeholder.setStyleSheet("font-size: 11px; color: #556080; padding: 30px 10px;")
            placeholder.setWordWrap(True)
            self.cards_layout.insertWidget(0, placeholder)
            return

        for item in items:
            card = UnwatchedPosterCard(item["id"], item["title"], item.get("year"))
            card.copied.connect(self._on_item_copied)
            card.card_clicked.connect(self._on_card_popped)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def _after_sync(self, count: int):
        self._render_cards(list_unwatched_movies())
        self.toast_lbl.setText(f"✔ {count} movies synced")
        self.toast_lbl.setStyleSheet("font-size: 10px; color: #00FFC8; font-weight: 700;")
        QTimer.singleShot(4000, lambda: [
            self.toast_lbl.setText(""),
            self.toast_lbl.setStyleSheet("font-size: 10px; color: #8BA8C8; font-weight: 600;")
        ])

    def _after_sync_error(self, msg: str):
        # Keep whatever is already in the DB; just update toast
        self.toast_lbl.setText("⚠ Sync failed")
        self.toast_lbl.setStyleSheet("font-size: 10px; color: #FF6060; font-weight: 700;")
        QTimer.singleShot(5000, lambda: [
            self.toast_lbl.setText(""),
            self.toast_lbl.setStyleSheet("font-size: 10px; color: #8BA8C8; font-weight: 600;")
        ])

    def _on_item_copied(self, alpha_text: str):
        self.toast_lbl.setText(f"✔ Copied: {alpha_text}")
        self.toast_lbl.setStyleSheet("font-size: 10px; color: #00FFC8; font-weight: 700;")
        QTimer.singleShot(3500, lambda: [
            self.toast_lbl.setText(""),
            self.toast_lbl.setStyleSheet("font-size: 10px; color: #8BA8C8; font-weight: 600;")
        ])

    def _on_card_popped(self, movie_id: int, title: str, year: str):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"{title} ({year})" if year else title)
        dlg.setStyleSheet("background-color: #0E0C22; color: #E8F4FF;")
        dlg.setMinimumWidth(500)
        
        main_lay = QHBoxLayout(dlg)
        main_lay.setContentsMargins(20, 20, 20, 20)
        main_lay.setSpacing(20)

        # Left side - Poster
        poster_lbl = QLabel()
        poster_lbl.setFixedSize(150, 225)
        poster_lbl.setAlignment(Qt.AlignCenter)
        poster_lbl.setStyleSheet("background: #15122E; border-radius: 8px;")
        poster_lbl.setText("Loading...")
        main_lay.addWidget(poster_lbl)

        # Right side - Details
        det_lay = QVBoxLayout()
        
        title_lbl = QLabel(f"{title} ({year})" if year else title)
        title_lbl.setStyleSheet("font-size: 20px; font-weight: 700; color: #00F0FF;")
        title_lbl.setWordWrap(True)
        det_lay.addWidget(title_lbl)

        rating_lbl = QLabel("Rating: -")
        rating_lbl.setStyleSheet("font-size: 12px; color: #FFD700; font-weight: 600;")
        det_lay.addWidget(rating_lbl)

        synopsis_lbl = QLabel("Fetching details...")
        synopsis_lbl.setWordWrap(True)
        synopsis_lbl.setStyleSheet("font-size: 12px; color: #B3ACD9; line-height: 1.4;")
        synopsis_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        det_lay.addWidget(synopsis_lbl, stretch=1)

        btn_row = QHBoxLayout()
        
        imdb_btn = QPushButton("IMDb")
        imdb_btn.setCursor(Qt.PointingHandCursor)
        imdb_btn.setStyleSheet("background: #F5C518; color: #000000; font-weight: 800; padding: 6px 14px; border-radius: 6px;")
        imdb_btn.hide()
        btn_row.addWidget(imdb_btn)

        save_btn = QPushButton("Saved")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet("background: #00F0FF; color: #080614; font-weight: 700; padding: 6px 14px; border-radius: 6px;")
        def _on_save():
            delete_unwatched_movie(movie_id)
            dlg.accept()
            self.refresh_unwatched()
        save_btn.clicked.connect(_on_save)
        btn_row.addWidget(save_btn)
        
        close_btn = QPushButton("Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet("background: rgba(0,240,255,20); color: #E8F4FF; padding: 6px 14px; border-radius: 6px;")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        
        det_lay.addLayout(btn_row)
        main_lay.addLayout(det_lay)

        # Background fetch — use rich MovieMetadata (saves poster to local disk)
        def _fetch():
            display = f"{title} ({year})" if year else title
            meta = _fetch_full_metadata(display)

            def _update():
                try:
                    # poster_path is a local disk path once downloaded by movie_metadata
                    local_poster = meta.poster_path
                    if local_poster and os.path.isfile(local_poster):
                        pix = QPixmap(local_poster).scaled(
                            150, 225, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                        )
                        poster_lbl.setPixmap(pix)
                    else:
                        # Fall back to poster_service cache (may exist from card load)
                        cached = cached_poster_path(title, year, "movie")
                        if cached and os.path.isfile(cached):
                            pix = QPixmap(cached).scaled(
                                150, 225, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                            )
                            poster_lbl.setPixmap(pix)
                        else:
                            poster_lbl.setText("No Poster")

                    if meta.rating and meta.rating > 0:
                        rating_lbl.setText(f"Rating: \u2605 {meta.rating:.1f} / 10")
                    else:
                        rating_lbl.setText("Rating: \u2014")

                    synopsis_lbl.setText(
                        meta.plot
                        if meta.plot and meta.plot != "No overview available."
                        else "No synopsis available."
                    )

                    if meta.imdb_id:
                        imdb_btn.clicked.connect(
                            lambda: QDesktopServices.openUrl(
                                QUrl(f"https://www.imdb.com/title/{meta.imdb_id}/")
                            )
                        )
                        imdb_btn.show()
                except (RuntimeError, AttributeError):
                    pass  # dialog closed before update arrived

            QTimer.singleShot(0, _update)

        import threading
        threading.Thread(target=_fetch, daemon=True).start()


        dlg.exec()

class DashboardPage(QWidget):
    """
    Futuristic spacecraft command dashboard with unwatched wishlist poster cards,
    slidable upload speed history, last viewed movie card, and dynamic movie spotlight HUD.
    """

    prev_bg_requested = Signal()
    next_bg_requested = Signal()

    def __init__(self, queue_manager, parent=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self._imdb_url: str = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 0, 4, 0)
        root.setSpacing(12)

        # 1. Top Header
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        h1 = QLabel("Dashboard")
        h1.setProperty("role", "h1")
        h1.setFixedHeight(28)
        title_col.addWidget(h1)
        header_row.addLayout(title_col)
        header_row.addStretch()
        root.addLayout(header_row)



        # ── 3. Unwatched Movies Wishlist Card (Replaces Sine Wave) ───────────
        self.unwatched_card = UnwatchedMoviesCard()
        root.addWidget(self.unwatched_card)

        # ── 4. Slidable Upload Speed History Chart (Stock Market Style) ──────
        chart_card = GlassCard()
        chart_card.setStyleSheet("QFrame#GlassCard { background: rgba(14, 12, 32, 175); border: 1px solid rgba(0,240,255,30); border-radius: 12px; }")
        chart_lay = QVBoxLayout(chart_card)
        chart_lay.setContentsMargins(14, 10, 14, 10)
        chart_lay.setSpacing(6)

        c_head = QHBoxLayout()
        c_title = QLabel("UPLOAD VELOCITY TELEMETRY")
        c_title.setStyleSheet("font-size: 10.5px; font-weight: 700; color: #00F0FF; letter-spacing: 0.5px;")
        c_head.addWidget(c_title)
        c_head.addStretch()
        chart_lay.addLayout(c_head)

        self.stock_chart = SlidableStockHistoryWidget()
        chart_lay.addWidget(self.stock_chart)

        # Interactive timeline slider
        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)
        lbl_old = QLabel("T - 60m")
        lbl_old.setStyleSheet("font-size: 9px; color: #3D5A7A; font-weight: 600;")
        self.scrub_slider = QSlider(Qt.Horizontal)
        self.scrub_slider.setRange(0, 1000)
        self.scrub_slider.setValue(1000)
        self.scrub_slider.setCursor(Qt.PointingHandCursor)
        self.scrub_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: rgba(0,240,255,25); border-radius: 2px; } "
            "QSlider::sub-page:horizontal { background: #00F0FF; border-radius: 2px; } "
            "QSlider::handle:horizontal { background: #E8F4FF; border: 2px solid #00F0FF; width: 12px; margin: -4px 0; border-radius: 6px; }"
        )
        self.scrub_slider.valueChanged.connect(lambda val: self.stock_chart.set_scrub_ratio(val / 1000.0))
        lbl_now = QLabel("LIVE NOW")
        lbl_now.setStyleSheet("font-size: 9px; color: #00FFC8; font-weight: 700;")
        slider_row.addWidget(lbl_old)
        slider_row.addWidget(self.scrub_slider, stretch=1)
        slider_row.addWidget(lbl_now)
        chart_lay.addLayout(slider_row)

        root.addWidget(chart_card)

        # ── 5. Bottom Row: Left Column (Spotlight + Telegram Download) + Activity + Last Viewed + Queue ─────
        mid = QHBoxLayout()
        mid.setSpacing(12)

        left_col = QVBoxLayout()
        left_col.setSpacing(10)

        # 1. Spotlight Card (Half height)
        self.spotlight_card = GlassCard()
        self.spotlight_card.setFixedSize(270, 150)
        self.spotlight_card.setStyleSheet(
            "QFrame#GlassCard { background: rgba(14, 11, 32, 115); border: 1px solid rgba(0,240,255,45); border-radius: 12px; }"
        )
        spot_lay = QVBoxLayout(self.spotlight_card)
        spot_lay.setContentsMargins(12, 10, 12, 10)
        spot_lay.setSpacing(4)

        self.spot_title = QLabel("CINEMA SPOTLIGHT")
        self.spot_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #00FFC8;")
        spot_lay.addWidget(self.spot_title)

        self.spot_plot = QLabel("")
        self.spot_plot.setWordWrap(True)
        self.spot_plot.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.spot_plot.setStyleSheet("color: #E8F4FF; font-size: 10.5px; line-height: 1.2;")
        spot_lay.addWidget(self.spot_plot, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        
        self.prev_btn = QPushButton("◄")
        self.prev_btn.setCursor(Qt.PointingHandCursor)
        self.prev_btn.setStyleSheet("QPushButton { background: rgba(0,240,255,20); color: #00F0FF; border: 1px solid rgba(0,240,255,50); border-radius: 5px; padding: 2px 6px; font-size: 11px; } QPushButton:hover { background: rgba(0,240,255,45); color: #FFF; }")
        self.prev_btn.clicked.connect(self.prev_bg_requested.emit)
        btn_row.addWidget(self.prev_btn)
        
        self.next_btn = QPushButton("►")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn.setStyleSheet("QPushButton { background: rgba(0,240,255,20); color: #00F0FF; border: 1px solid rgba(0,240,255,50); border-radius: 5px; padding: 2px 6px; font-size: 11px; } QPushButton:hover { background: rgba(0,240,255,45); color: #FFF; }")
        self.next_btn.clicked.connect(self.next_bg_requested.emit)
        btn_row.addWidget(self.next_btn)

        self.imdb_btn = QPushButton("IMDb")
        self.imdb_btn.setCursor(Qt.PointingHandCursor)
        self.imdb_btn.setStyleSheet("QPushButton { background: rgba(245,197,24,20); color: #F5C518; border: 1px solid rgba(245,197,24,50); border-radius: 5px; padding: 2px 8px; font-size: 10.5px; font-weight: bold; } QPushButton:hover { background: rgba(245,197,24,45); color: #FFF; }")
        self.imdb_btn.clicked.connect(self._open_imdb)
        btn_row.addWidget(self.imdb_btn)
        
        btn_row.addStretch()
        spot_lay.addLayout(btn_row)

        left_col.addWidget(self.spotlight_card)

        # 2. Telegram Backup Download Card under Spotlight Card
        self.download_card = self._make_download_card()
        left_col.addWidget(self.download_card)

        mid.addLayout(left_col)
        mid.addWidget(self._make_activity_card())

        # Last Viewed Movie Poster Card
        self.last_viewed_card = LastViewedMovieCard()
        mid.addWidget(self.last_viewed_card)

        # Transmission Queue Card
        mid.addWidget(self._make_queue_card(), stretch=1)
        root.addLayout(mid, stretch=1)

        from app.core.download_manager import DownloadManager
        dm = DownloadManager.instance()
        dm.download_started.connect(self._on_download_started)
        dm.download_progress.connect(self._on_download_progress)
        dm.download_finished.connect(self._on_download_finished)
        dm.download_failed.connect(self._on_download_failed)


        # ── Queue Manager signals ────────────────────────────────────────────
        self.queue_manager.job_added.connect(self._on_queue_changed)
        self.queue_manager.job_updated.connect(self._on_queue_changed)
        self.queue_manager.job_removed.connect(self._on_queue_changed)

        self._refresh_queue()
        self._refresh_stats()

    def showEvent(self, event):
        super().showEvent(event)
        self.last_viewed_card.refresh_last_viewed()
        self.unwatched_card.refresh_unwatched()
        if os.environ.get("VAULTFATHER_DEMO_DASHBOARD") == "1":
            self._refresh_queue()

    def update_movie_spotlight(self, title: str, year: str, plot: str, imdb_url: str):
        """Update spotlight box when background image cycles (every 7s)."""
        self._imdb_url = imdb_url
        self.spot_title.setText(f"{title.upper()} ({year})")
        clean_plot = plot if len(plot) < 140 else plot[:137] + "…"
        self.spot_plot.setText(clean_plot)
        self.imdb_btn.setVisible(bool(imdb_url))

    def _open_imdb(self):
        if self._imdb_url:
            QDesktopServices.openUrl(QUrl(self._imdb_url))

    # ── Activity Card ────────────────────────────────────────────────────────

    def _make_activity_card(self) -> GlassCard:
        card = GlassCard()
        card.setFixedWidth(270)
        card.setMaximumHeight(340)
        card.setStyleSheet("QFrame#GlassCard { background: rgba(14, 12, 32, 175); border: 1px solid rgba(0,240,255,25); border-radius: 12px; }")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(10)

        title = QLabel("TELEMETRY STATUS")
        title.setStyleSheet("font-size: 11.5px; font-weight: 700; color: #00F0FF; letter-spacing: 0.5px;")
        lay.addWidget(title)

        rings = QHBoxLayout()
        rings.setSpacing(12)
        rings.addStretch()

        self.task_ring = ProgressRing(size=105, pen_width=8)
        rings.addWidget(self.task_ring)

        self.overall_ring = ProgressRing(size=105, pen_width=8)
        rings.addWidget(self.overall_ring)
        rings.addStretch()
        lay.addLayout(rings)

        self.stats_label = QLabel("No active backups")
        self.stats_label.setAlignment(Qt.AlignCenter)
        self.stats_label.setWordWrap(True)
        self.stats_label.setMaximumHeight(64)
        self.stats_label.setStyleSheet("color: #8BA8C8; font-size: 11px;")
        lay.addWidget(self.stats_label)

        # Legend
        legend = QVBoxLayout()
        legend.setSpacing(5)
        self._legend_values: dict[str, QLabel] = {}
        for dot_color, key, text in [
            ("#00FFC8", "backed_up", "DELIVERED"),
            ("#FFB347", "pending",   "QUEUED"),
            ("#FF3366", "failed",    "FAILED"),
        ]:
            row = QHBoxLayout()
            dot = QLabel()
            dot.setFixedSize(6, 6)
            dot.setStyleSheet(f"background-color: {dot_color}; border-radius: 3px;")
            lbl = QLabel(text)
            lbl.setStyleSheet("color: #8BA8C8; font-size: 10px; font-weight: 600;")
            val = QLabel("0")
            val.setStyleSheet("color: #E8F4FF; font-size: 11px; font-weight: 700;")
            row.addWidget(dot)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            legend.addLayout(row)
            self._legend_values[key] = val
        lay.addLayout(legend)
        return card

    # ── Queue Card ───────────────────────────────────────────────────────────


    def _make_download_card(self) -> GlassCard:
        card = GlassCard()
        card.setFixedSize(270, 180)
        card.setStyleSheet("QFrame#GlassCard { background: rgba(14, 12, 32, 175); border: 1px solid rgba(0,240,255,25); border-radius: 12px; }")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        title = QLabel("CLOUD DOWNLINK // TELEGRAM BACKUP")
        title.setStyleSheet("font-size: 10px; font-weight: 700; color: #00F0FF; letter-spacing: 0.5px;")
        lay.addWidget(title)

        rings = QHBoxLayout()
        rings.setSpacing(10)
        rings.addStretch()

        self.dl_ring = ProgressRing(size=64, pen_width=6)
        rings.addWidget(self.dl_ring)
        rings.addStretch()
        lay.addLayout(rings)

        self.dl_name_lbl = QLabel("No active download")
        self.dl_name_lbl.setAlignment(Qt.AlignCenter)
        self.dl_name_lbl.setWordWrap(True)
        self.dl_name_lbl.setStyleSheet("color: #F3F1FF; font-size: 11px; font-weight: 600;")
        lay.addWidget(self.dl_name_lbl)

        self.dl_stats_lbl = QLabel("IDLE")
        self.dl_stats_lbl.setAlignment(Qt.AlignCenter)
        self.dl_stats_lbl.setStyleSheet("color: #8BA8C8; font-size: 10px;")
        lay.addWidget(self.dl_stats_lbl)
        
        return card

    def _on_download_started(self, job_name):
        self.dl_name_lbl.setText(job_name)
        self.dl_stats_lbl.setText("Connecting...")
        self.dl_ring.set_progress(0, "running")

    def _on_download_progress(self, percent, text):
        from app.core.movie_scanner import human_size
        from app.core.download_manager import DownloadManager
        dm = DownloadManager.instance()
        speed_str = human_size(dm.speed_bps) + "/s" if dm.speed_bps > 0 else ""
        self.dl_stats_lbl.setText(f"{text} · {speed_str}".strip(" ·"))
        self.dl_ring.set_progress(percent, "running")

    def _on_download_finished(self, path):
        self.dl_name_lbl.setText("Download completed")
        self.dl_stats_lbl.setText("COMPLETE")
        self.dl_ring.set_progress(100, "done")

    def _on_download_failed(self, job_name, error):
        self.dl_stats_lbl.setText(f"Failed: {error}")
        self.dl_ring.set_progress(100, "failed")


    def _make_queue_card(self) -> GlassCard:
        card = GlassCard()
        card.setStyleSheet("QFrame#GlassCard { background: rgba(14, 12, 32, 175); border: 1px solid rgba(0,240,255,25); border-radius: 12px; }")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("TRANSMISSION QUEUE")
        title.setStyleSheet("font-size: 11.5px; font-weight: 700; color: #00F0FF; letter-spacing: 0.5px;")
        head.addWidget(title)
        head.addStretch()

        self.refresh_queue_btn = GhostButton("⟳  Refresh")
        self.refresh_queue_btn.setToolTip("Remove uploaded and failed entries from queue")
        self.refresh_queue_btn.clicked.connect(self._on_clear_failed_clicked)
        head.addWidget(self.refresh_queue_btn)

        self.queue_count_label = QLabel("0 ACTIVE")
        self.queue_count_label.setStyleSheet(
            "color: #00F0FF; background-color: rgba(0,240,255,18); "
            "font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 8px; "
            "border: 1px solid rgba(0,240,255,40);"
        )
        head.addWidget(self.queue_count_label)
        lay.addLayout(head)

        self.empty_label = QLabel("No backups queued — select movies to initiate archive and upload.")
        self.empty_label.setStyleSheet("color: #3D5A7A; font-size: 11.5px;")
        self.empty_label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.queue_rows_container = QWidget()
        self.queue_rows_layout = QVBoxLayout(self.queue_rows_container)
        self.queue_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_rows_layout.setSpacing(6)
        self.queue_rows_layout.addStretch()
        scroll.setWidget(self.queue_rows_container)
        scroll.setMinimumHeight(100)
        scroll.setMaximumHeight(320)
        lay.addWidget(scroll, stretch=1)
        return card

    def _on_clear_failed_clicked(self):
        self.queue_manager.clear_failed_jobs()
        self._refresh_queue()
        self._refresh_stats()

    # ── Refresh & Telemetry Recording ────────────────────────────────────────

    def _on_queue_changed(self, _job_id: str = None) -> None:
        self._refresh_queue()
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        pass

    def _refresh_queue(self) -> None:
        if os.environ.get("VAULTFATHER_DEMO_DASHBOARD") == "1":
            # Cloud Downlink card
            self.dl_name_lbl.setText("Interstellar (2014) [1080p Remux]")
            self.dl_stats_lbl.setText("Downloading Part 3/5 · 1.4 GB / 2.0 GB · 18.2 MB/s")
            self.dl_ring.set_value(68)

            # Cinema Spotlight
            self.update_movie_spotlight(
                "Interstellar",
                "2014",
                "When Earth becomes uninhabitable in the future, a farmer and ex-NASA pilot, Joseph Cooper, is tasked to pilot a spacecraft across galaxies to find humanity a new home.",
                "https://www.imdb.com/title/tt0816692/"
            )

            snapshots = [
                ("demo_1", "Dune: Part Two (2024)", ["VaultFather Alpha"], "uploading", 74, None, 74, int(8.2 * 1024 * 1024 * 1024), int(11.1 * 1024 * 1024 * 1024), int(24.8 * 1024 * 1024), "04m 12s remaining"),
                ("demo_2", "Blade Runner 2049 (2017)", ["VaultFather Alpha"], "queued", 0, None, 0, 0, int(9.4 * 1024 * 1024 * 1024), 0, None),
                ("demo_3", "Oppenheimer (2023)", ["VaultFather Alpha"], "done", 100, None, 100, int(14.2 * 1024 * 1024 * 1024), int(14.2 * 1024 * 1024 * 1024), 0, "Completed"),
            ]
        else:
            jobs = self.queue_manager.jobs_in_order()
            snapshots = [
                (j.id, j.movie_name, j.destinations, j.status, j.percent,
                 j.error, j.phase_percent, j.bytes_done, j.bytes_total,
                 j.upload_speed_bps, j.upload_time_str)
                for j in jobs
            ]

        if not hasattr(self, "_queue_rows"):
            self._queue_rows = {}

        # Remove deleted jobs
        current_jids = {s[0] for s in snapshots}
        for jid in list(self._queue_rows.keys()):
            if jid not in current_jids:
                row = self._queue_rows.pop(jid)
                self.queue_rows_layout.removeWidget(row)
                row.deleteLater()

        self.empty_label.setVisible(len(snapshots) == 0)
        active_count = sum(1 for s in snapshots if s[3] in ACTIVE_STATES)
        self.queue_count_label.setText(f"{active_count} ACTIVE")

        counts = {"backed_up": 0, "pending": 0, "failed": 0}
        active_snap = None

        # Reorder existing or insert new
        for i, (jid, movie_name, destinations, status, percent, error,
                phase_pct, bytes_done, bytes_total, speed, time_str) in enumerate(snapshots):
            track_state = "running" if status in RUNNING_STATES else status
            meta = self._meta_for_status(status, destinations, error, time_str)
            
            if jid in self._queue_rows:
                row = self._queue_rows[jid]
                row.update_state(percent, track_state, meta)
                # Ensure order
                self.queue_rows_layout.insertWidget(i, row)
            else:
                row = QueueRow(movie_name, meta, percent, track_state, row_id=jid)
                if os.environ.get("VAULTFATHER_DEMO_DASHBOARD") != "1":
                    row.pause_requested.connect(lambda j=jid: self.queue_manager.pause_job(j))
                    row.resume_requested.connect(lambda j=jid: self.queue_manager.resume_job(j))
                    row.retry_requested.connect(lambda j=jid: self.queue_manager.retry_job(j))
                    row.stop_requested.connect(lambda j=jid: self.queue_manager.cancel_job(j))
                self._queue_rows[jid] = row
                self.queue_rows_layout.insertWidget(i, row)

            if status in RUNNING_STATES and active_snap is None:
                active_snap = (movie_name, status, phase_pct,
                               bytes_done, bytes_total, speed, time_str)
                UploadHistoryTracker.instance().record_sample(
                    speed_bps=speed,
                    job_name=movie_name,
                    bytes_done=bytes_done,
                    percent=phase_pct
                )

            if status == "done":
                counts["backed_up"] += 1
            elif status == "failed":
                counts["failed"] += 1
            else:
                counts["pending"] += 1

        self._update_rings(active_snap, counts, len(snapshots))

        for key, lbl in self._legend_values.items():
            lbl.setText(str(counts[key]))

    def _update_rings(self, active_snap, counts: dict, total: int) -> None:
        if active_snap is None:
            self.task_ring.set_value(None, caption="STANDBY")
            self.stats_label.setText("No active transmission")
        else:
            movie_name, status, phase_pct, bd, bt, speed, time_str = active_snap
            phase_label = "ARCHIVING" if status == "archiving" else "UPLOADING"
            self.task_ring.set_value(phase_pct, caption=phase_label)
            lines = [f"<b>{movie_name}</b>", phase_label]
            if bt:
                lines.append(f"{human_size(bd)} / {human_size(bt)}")
            if status == "uploading":
                lines.append(f"Speed: {_human_speed(speed)}")
                if time_str:
                    lines.append(f"Upload time: {time_str}")
            self.stats_label.setText("<br>".join(lines))

        resolved = counts["backed_up"] + counts["failed"]
        if total == 0:
            self.overall_ring.set_value(None, caption="QUEUE")
        else:
            pct = int((resolved / total) * 100)
            self.overall_ring.set_value(pct, caption=f"{resolved}/{total}")

    def _meta_for_status(self, status: str, destinations: list,
                          error: str | None, time_str: str | None = None) -> str:
        names = ", ".join(destinations) if destinations else "a destination"
        time_part = f"<br>Upload time: {time_str}" if time_str else ""
        match status:
            case "queued":    return f"Waiting · target: {names}"
            case "archiving": return "Archiving volumes with 7z encryption…"
            case "uploading": return f"Transmitting to {names}{time_part}"
            case "done":      return f"Delivered to {names}{time_part}"
            case "failed":    return (error or "Transmission failed.") + time_part
            case _:           return ""
