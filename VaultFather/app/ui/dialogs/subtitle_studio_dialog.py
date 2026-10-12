"""
Subtitle Studio Dialog — Obsidian Glass.

Allows searching, dragging-and-dropping, previewing in VLC,
and lossless soft-remuxing of subtitles with 0.00% quality loss.
"""

import os
import shutil
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QFileDialog, QCheckBox, QMessageBox,
    QProgressBar, QWidget
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QIcon, QPixmap

from app.theme.tokens import Colors
from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.ui.widgets.glass_card import GlassCard
from app.core.subtitle_service import (
    search_subtitles_online, download_subtitle_file,
    remux_subtitle_lossless, compute_movie_hash
)
from app.core.vlc_launcher import launch_vlc_with_subtitles, find_vlc_path
from app.core.subtitle_detector import detect_subtitles, SUBTITLE_EXTENSIONS
from app.core.poster_service import cached_poster_path
from app.core.title_cleaner import parse_movie_title_and_year


class DropZoneWidget(QFrame):
    """Interactive drag & drop target for local subtitle files."""
    file_dropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            "QFrame {"
            "  border: 2px dashed rgba(0, 240, 255, 60);"
            "  border-radius: 12px;"
            "  background: rgba(14, 12, 34, 120);"
            "}"
            "QFrame:hover {"
            "  border: 2px dashed #00F0FF;"
            "  background: rgba(0, 240, 255, 20);"
            "}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 20, 16, 20)
        lay.setAlignment(Qt.AlignCenter)

        self.label = QLabel("📥 Drop subtitle file here (.srt, .vtt, .ass) or click to browse")
        self.label.setStyleSheet("color: #8BA8C8; font-size: 13px; font-weight: 600;")
        self.label.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, "Select Subtitle File", "", "Subtitles (*.srt *.vtt *.ass *.ssa *.sub)"
            )
            if path:
                self.file_dropped.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(Path(u.toLocalFile()).suffix.lower() in SUBTITLE_EXTENSIONS for u in urls):
                event.acceptProposedAction()
                self.setStyleSheet(
                    "QFrame {"
                    "  border: 2px dashed #00F0FF;"
                    "  background: rgba(0, 240, 255, 40);"
                    "}"
                )

    def dragLeaveEvent(self, event):
        self.setStyleSheet(
            "QFrame {"
            "  border: 2px dashed rgba(0, 240, 255, 60);"
            "  background: rgba(14, 12, 34, 120);"
            "}"
        )

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            local_path = url.toLocalFile()
            if Path(local_path).suffix.lower() in SUBTITLE_EXTENSIONS:
                self.file_dropped.emit(local_path)
                break
        self.dragLeaveEvent(None)


class SubtitleCandidateRow(QFrame):
    """Row widget representing one subtitle candidate with check mark."""
    toggled = Signal()

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.setObjectName("SubRow")
        self.setStyleSheet(
            "QFrame#SubRow {"
            "  background: rgba(16, 14, 38, 160);"
            "  border: 1px solid rgba(0, 240, 255, 30);"
            "  border-radius: 8px;"
            "}"
            "QFrame#SubRow:hover {"
            "  border: 1px solid rgba(0, 240, 255, 80);"
            "}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.toggled.connect(lambda: self.toggled.emit())
        lay.addWidget(self.checkbox)

        # Info column
        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        title_row = QHBoxLayout()
        name_lbl = QLabel(data.get("name", "Subtitle"))
        name_lbl.setStyleSheet("color: #E8F4FF; font-size: 13px; font-weight: bold;")
        name_lbl.setWordWrap(True)
        title_row.addWidget(name_lbl, stretch=1)

        if data.get("is_hash_match"):
            badge = QLabel("🌟 EXACT SYNC MATCH")
            badge.setStyleSheet(
                "background: rgba(0, 240, 255, 30); color: #00F0FF; "
                "font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;"
            )
            title_row.addWidget(badge)
        elif data.get("is_local"):
            badge = QLabel("📁 LOCAL FILE")
            badge.setStyleSheet(
                "background: rgba(100, 255, 120, 30); color: #50FA7B; "
                "font-size: 10px; font-weight: bold; border-radius: 4px; padding: 2px 6px;"
            )
            title_row.addWidget(badge)

        info_col.addLayout(title_row)

        meta_parts = []
        if data.get("release"):
            meta_parts.append(f"Release: {data['release']}")
        if data.get("downloads"):
            meta_parts.append(f"Downloads: {data['downloads']}")
        if data.get("rating") and data["rating"] != "0.0":
            meta_parts.append(f"Rating: {data['rating']}★")
        if data.get("language"):
            meta_parts.append(f"Lang: {data['language']}")

        meta_lbl = QLabel(" · ".join(meta_parts) if meta_parts else "Subtitle File")
        meta_lbl.setStyleSheet("color: #8BA8C8; font-size: 11px;")
        info_col.addWidget(meta_lbl)

        lay.addLayout(info_col, stretch=1)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)


class SubtitleStudioDialog(QDialog):
    """Full-featured Subtitle Studio popup for an individual movie."""
    search_finished = Signal(object)
    preview_ready = Signal(object)
    embed_finished = Signal(bool, str, str)

    def __init__(self, movie_path: str, movie_name: str, parent=None):
        super().__init__(parent)
        self.movie_path = movie_path
        self.movie_name = movie_name
        self.movie_dir = Path(movie_path).parent
        self.movie_stem = Path(movie_path).stem

        self.setWindowTitle(f"Subtitle Studio — {movie_name}")
        self.resize(760, 680)
        self.setStyleSheet(
            "QDialog {"
            "  background-color: #0B091B;"
            "}"
            "QScrollBar:vertical {"
            "  border: none; background: rgba(0,0,0,20); width: 8px; margin: 0; border-radius: 4px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(0, 240, 255, 40); min-height: 20px; border-radius: 4px;"
            "}"
        )

        self._candidate_rows: list[SubtitleCandidateRow] = []
        self._preview_dir = self.movie_dir / f".vf_subtitles_{self.movie_stem}"

        self.search_finished.connect(self._on_search_finished)
        self.preview_ready.connect(self._finish_vlc_launch)
        self.embed_finished.connect(self._on_embed_finished)

        self._build_ui()
        self._load_existing_local_subtitles()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Header Hero
        header = QHBoxLayout()
        header.setSpacing(14)

        # Poster thumbnail
        clean_t, yr = parse_movie_title_and_year(Path(self.movie_path).name)
        c_path = cached_poster_path(clean_t, yr, "movie")
        if c_path and os.path.isfile(c_path):
            poster_thumb = QLabel()
            poster_thumb.setFixedSize(54, 76)
            poster_thumb.setScaledContents(False)
            poster_thumb.setAlignment(Qt.AlignCenter)
            poster_thumb.setStyleSheet("border-radius: 6px; border: 1px solid rgba(0,240,255,40); background: #0B0A18;")
            pix = QPixmap(c_path).scaled(54, 76, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            poster_thumb.setPixmap(pix)
            header.addWidget(poster_thumb)

        header_text = QVBoxLayout()
        header_text.setSpacing(4)

        title = QLabel(f"Subtitle Studio: {self.movie_name}")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #00F0FF; letter-spacing: 0.5px;")
        header_text.addWidget(title)

        sub_info = QLabel(f"Format: {Path(self.movie_path).suffix.upper()} · Location: {self.movie_path}")
        sub_info.setStyleSheet("font-size: 11px; color: #8BA8C8;")
        header_text.addWidget(sub_info)

        header.addLayout(header_text)
        header.addStretch()

        close_btn = GhostButton("✕ Close")
        close_btn.clicked.connect(self.reject)
        header.addWidget(close_btn)
        root.addLayout(header)

        # Drop-in rectangle
        self.drop_zone = DropZoneWidget()
        self.drop_zone.file_dropped.connect(self._on_local_file_dropped)
        root.addWidget(self.drop_zone)

        # Search Controls Bar
        search_bar = QHBoxLayout()
        search_bar.setSpacing(10)

        self.find_btn = PrimaryButton("🔍 Find Subtitles Online")
        self.find_btn.setMinimumHeight(38)
        self.find_btn.clicked.connect(self._on_find_subtitles_clicked)
        search_bar.addWidget(self.find_btn)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #00F0FF; font-size: 12px; font-weight: 600;")
        search_bar.addWidget(self.status_lbl, stretch=1)

        self.spinner = QProgressBar()
        self.spinner.setRange(0, 0)
        self.spinner.setFixedHeight(4)
        self.spinner.setVisible(False)
        self.spinner.setStyleSheet(
            "QProgressBar { background: transparent; border: none; }"
            "QProgressBar::chunk { background: #00F0FF; }"
        )

        root.addLayout(search_bar)
        root.addWidget(self.spinner)

        # Candidate List Scroll Area
        list_card = GlassCard()
        list_card_lay = QVBoxLayout(list_card)
        list_card_lay.setContentsMargins(14, 14, 14, 14)
        list_card_lay.setSpacing(8)

        list_header = QLabel("AVAILABLE SUBTITLES")
        list_header.setStyleSheet("color: #8BA8C8; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        list_card_lay.addWidget(list_header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_container)
        list_card_lay.addWidget(self.scroll, stretch=1)
        root.addWidget(list_card, stretch=1)

        # Action Buttons Footer
        footer = QHBoxLayout()
        footer.setSpacing(14)

        self.play_btn = GhostButton("▶  Play & Preview in VLC")
        self.play_btn.setMinimumHeight(42)
        self.play_btn.clicked.connect(self._on_play_preview_clicked)
        footer.addWidget(self.play_btn)

        footer.addStretch()

        self.run_btn = PrimaryButton("⚡  Run (Embed & Finalize)")
        self.run_btn.setMinimumHeight(42)
        self.run_btn.clicked.connect(self._on_run_embed_clicked)
        footer.addWidget(self.run_btn)

        root.addLayout(footer)

    def _load_existing_local_subtitles(self):
        """Discovers any subtitles already existing in the movie directory."""
        found = detect_subtitles(self.movie_path)
        for s in found:
            self._add_candidate_row({
                "id": s,
                "name": Path(s).name,
                "local_path": s,
                "is_local": True,
                "format": Path(s).suffix.lstrip("."),
                "is_hash_match": False,
            })

    def _add_candidate_row(self, data: dict):
        # Prevent duplicates
        for existing in self._candidate_rows:
            if existing.data.get("id") == data.get("id"):
                return

        row = SubtitleCandidateRow(data)
        self._candidate_rows.append(row)
        # Insert before the stretch
        self.list_layout.insertWidget(len(self._candidate_rows) - 1, row)

    def _on_local_file_dropped(self, file_path: str):
        self._add_candidate_row({
            "id": file_path,
            "name": Path(file_path).name,
            "local_path": file_path,
            "is_local": True,
            "format": Path(file_path).suffix.lstrip("."),
            "is_hash_match": False,
        })
        self.status_lbl.setText(f"Added local subtitle: {Path(file_path).name}")

    def _on_find_subtitles_clicked(self):
        self.find_btn.setEnabled(False)
        self.spinner.setVisible(True)
        self.status_lbl.setText("Computing hash & searching OpenSubtitles...")

        def _search():
            try:
                results = search_subtitles_online(self.movie_path)
            except Exception as e:
                results = []
            self.search_finished.emit(results)

        threading.Thread(target=_search, daemon=True).start()

    def _on_search_finished(self, results: list[dict]):
        self.find_btn.setEnabled(True)
        self.spinner.setVisible(False)

        if not results:
            self.status_lbl.setText("No online subtitles found for this title.")
            return

        for r in results:
            self._add_candidate_row(r)

        hash_count = sum(1 for r in results if r.get("is_hash_match"))
        if hash_count > 0:
            self.status_lbl.setText(f"Found {len(results)} subtitles ({hash_count} exact hash matches)!")
        else:
            self.status_lbl.setText(f"Found {len(results)} subtitles matching title.")

    def _on_play_preview_clicked(self):
        """Downloads selected candidate subtitles into a dedicated folder and launches VLC."""
        selected_rows = [r for r in self._candidate_rows if r.isChecked()]
        if not selected_rows:
            QMessageBox.information(
                self, "Select Subtitles",
                "Please check one or more subtitles in the list to preview in VLC."
            )
            return

        self.play_btn.setEnabled(False)
        self.status_lbl.setText("Downloading selected subtitle candidates...")
        self.spinner.setVisible(True)

        def _prepare_and_launch():
            self._preview_dir.mkdir(parents=True, exist_ok=True)
            ready_sub_paths = []

            for index, row in enumerate(selected_rows):
                data = row.data
                if data.get("is_local") and data.get("local_path"):
                    ready_sub_paths.append(data["local_path"])
                elif data.get("download_url"):
                    sub_filename = f"{self.movie_stem}.candidate_{index + 1}.{data.get('format', 'srt')}"
                    target_file = str(self._preview_dir / sub_filename)
                    if not os.path.isfile(target_file):
                        download_subtitle_file(data["download_url"], target_file)
                    if os.path.isfile(target_file):
                        ready_sub_paths.append(target_file)
                        row.data["preview_path"] = target_file

            self.preview_ready.emit(ready_sub_paths)

        threading.Thread(target=_prepare_and_launch, daemon=True).start()

    def _finish_vlc_launch(self, sub_paths: list[str]):
        self.play_btn.setEnabled(True)
        self.spinner.setVisible(False)

        if not sub_paths:
            self.status_lbl.setText("Could not download candidate subtitles.")
            return

        self.status_lbl.setText("Launching player...")
        try:
            used_vlc = launch_vlc_with_subtitles(self.movie_path, sub_paths)
            if used_vlc:
                self.status_lbl.setText(f"VLC launched with {len(sub_paths)} subtitle track(s). Verify sync in VLC.")
            else:
                self.status_lbl.setText("Playing in default player (Install VLC for multi-track subtitle switching).")
        except Exception as exc:
            QMessageBox.critical(self, "Player Error", f"Could not launch media player:\n{exc}")

    def _on_run_embed_clicked(self):
        """
        Renames chosen subtitle to match movie filename, losslessly remuxes into the video,
        moves selected subtitle into the movies folder, and cleans up other candidates.
        """
        selected_rows = [r for r in self._candidate_rows if r.isChecked()]
        if len(selected_rows) != 1:
            QMessageBox.warning(
                self, "Select Single Subtitle",
                "Please keep checked ONLY the one best-matching subtitle you want to embed."
            )
            return

        best_row = selected_rows[0]
        self.run_btn.setEnabled(False)
        self.play_btn.setEnabled(False)
        self.spinner.setVisible(True)
        self.status_lbl.setText("Preparing subtitle for lossless remux...")

        def _execute_run():
            data = best_row.data
            selected_sub_file = data.get("preview_path") or data.get("local_path")

            # If not yet downloaded:
            if not selected_sub_file and data.get("download_url"):
                self._preview_dir.mkdir(parents=True, exist_ok=True)
                selected_sub_file = str(self._preview_dir / f"selected.{data.get('format', 'srt')}")
                download_subtitle_file(data["download_url"], selected_sub_file)

            if not selected_sub_file or not os.path.isfile(selected_sub_file):
                self.embed_finished.emit(False, "Could not acquire selected subtitle file.", "")
                return

            # Target companion subtitle path alongside movie:
            ext = Path(selected_sub_file).suffix.lower() or ".srt"
            final_companion_sub = self.movie_dir / f"{self.movie_stem}{ext}"

            # Step 1: Copy selected subtitle to movie folder as companion file
            try:
                shutil.copy2(selected_sub_file, final_companion_sub)
            except Exception as e:
                pass

            # Step 2: Lossless remux into the video container (0% quality loss, disabled by default)
            success, msg = remux_subtitle_lossless(self.movie_path, str(final_companion_sub))

            # Step 3: Cleanup temporary preview directory
            if self._preview_dir.is_dir():
                try:
                    shutil.rmtree(self._preview_dir, ignore_errors=True)
                except Exception:
                    pass

            self.embed_finished.emit(success, msg, str(final_companion_sub))

        threading.Thread(target=_execute_run, daemon=True).start()

    def _on_embed_finished(self, success: bool, message: str, companion_path: str = ""):
        self.run_btn.setEnabled(True)
        self.play_btn.setEnabled(True)
        self.spinner.setVisible(False)

        if success:
            self.status_lbl.setText("Subtitles embedded losslessly and saved alongside movie!")
            QMessageBox.information(
                self, "Subtitle Studio Complete",
                f"✅ Subtitle successfully embedded into {self.movie_name} with 0% quality loss!\n\n"
                f"• Subtitle set as optional/disabled by default (matches VLC).\n"
                f"• Companion subtitle file saved as:\n{companion_path}\n"
                f"• Cleaned up candidate preview files."
            )
            self.accept()
        else:
            self.status_lbl.setText("Embedding failed.")
            QMessageBox.critical(self, "Embed Error", f"Could not embed subtitle:\n{message}")
