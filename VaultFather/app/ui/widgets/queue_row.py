from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QMenu, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtGui import QAction

from app.ui.widgets.status_track import StatusTrack

TAG_TEXT = {
    "running": None,       # no tag while actively uploading, just the % and bar
    "paused": "PAUSED",
    "queued": "Queued",
    "done": "Done",
    "failed": "Failed",
}


class QueueRow(QFrame):
    """
    One row in the Backup Queue: thumbnail, title, meta line,
    the transparent->green status track, a status tag chip, and
    a 3-dots (⋮) context dropdown menu with Stop, Pause/Resume controls.
    """

    action_clicked = Signal(str)       # legacy signal fallback (job_id)
    pause_requested = Signal(str)      # job_id
    resume_requested = Signal(str)     # job_id
    retry_requested = Signal(str)      # job_id
    stop_requested = Signal(str)       # job_id

    def __init__(self, title: str, meta: str, percent: float, state: str, row_id: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("QueueRow")
        self._row_id = row_id if row_id is not None else title
        self._state = state
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(14)

        thumb = QLabel("🎬")
        thumb.setObjectName("QueueThumb")
        thumb.setFixedSize(42, 42)
        thumb.setAlignment(Qt.AlignCenter)
        layout.addWidget(thumb)

        info_col = QVBoxLayout()
        info_col.setSpacing(7)

        top_row = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-size: 13.5px; font-weight: 700; color: #E8F4FF;")
        top_row.addWidget(title_label, stretch=1)

        tag_text = TAG_TEXT.get(state)
        if tag_text:
            self.tag_or_pct_lbl = QLabel(tag_text)
            self.tag_or_pct_lbl.setObjectName("QueueTag")
            if state == "paused":
                self.tag_or_pct_lbl.setProperty("tone", "resume")
            elif state == "done":
                self.tag_or_pct_lbl.setProperty("tone", "done")
            elif state == "failed":
                self.tag_or_pct_lbl.setProperty("tone", "failed")
        else:
            self.tag_or_pct_lbl = QLabel(f"{int(percent)}%")
            self.tag_or_pct_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #00F0FF;")
        top_row.addWidget(self.tag_or_pct_lbl)

        info_col.addLayout(top_row)

        self.track = StatusTrack(percent, state)
        info_col.addWidget(self.track)

        self.meta_label = QLabel(meta)
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet("font-size: 11px; color: #8BA8C8;")
        info_col.addWidget(self.meta_label)

        layout.addLayout(info_col, stretch=1)


        # 3 Dots (⋮) context menu button at right end of row
        self.dots_btn = QPushButton("⋮")
        self.dots_btn.setObjectName("QueueAction")
        self.dots_btn.setFixedSize(30, 30)
        self.dots_btn.setCursor(Qt.PointingHandCursor)
        self.dots_btn.setToolTip("Queue Options")
        self.dots_btn.setStyleSheet(
            "QPushButton { background: rgba(0,240,255,14); color: #00F0FF; "
            "border: 1px solid rgba(0,240,255,35); border-radius: 8px; font-size: 16px; font-weight: 700; } "
            "QPushButton:hover { background: rgba(0,240,255,40); color: #FFF; }"
        )
        self.dots_btn.clicked.connect(self._show_options_menu)
        layout.addWidget(self.dots_btn)

    def update_state(self, percent: float, state: str, meta: str):
        """Update the row in-place without rebuilding widgets."""
        if self._state != state:
            self._state = state
            tag_text = TAG_TEXT.get(state)
            if tag_text:
                self.tag_or_pct_lbl.setText(tag_text)
                self.tag_or_pct_lbl.setObjectName("QueueTag")
                if state == "paused":
                    self.tag_or_pct_lbl.setProperty("tone", "resume")
                elif state == "done":
                    self.tag_or_pct_lbl.setProperty("tone", "done")
                elif state == "failed":
                    self.tag_or_pct_lbl.setProperty("tone", "failed")
                else:
                    self.tag_or_pct_lbl.setProperty("tone", None)
                self.tag_or_pct_lbl.setStyleSheet("") # reset explicit style
                self.tag_or_pct_lbl.style().unpolish(self.tag_or_pct_lbl)
                self.tag_or_pct_lbl.style().polish(self.tag_or_pct_lbl)
            else:
                self.tag_or_pct_lbl.setText(f"{int(percent)}%")
                self.tag_or_pct_lbl.setObjectName("")
                self.tag_or_pct_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #00F0FF;")
        elif not TAG_TEXT.get(state):
            self.tag_or_pct_lbl.setText(f"{int(percent)}%")

        self.track.set_progress(percent, state)
        self.meta_label.setText(meta)

    def _show_options_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background-color: #0E0C22; color: #E8F4FF; border: 1px solid rgba(0,240,255,50); "
            "  border-radius: 8px; padding: 6px; font-size: 12px; }"
            "QMenu::item { padding: 6px 18px; border-radius: 4px; }"
            "QMenu::item:selected { background-color: rgba(0,240,255,40); color: #00F0FF; }"
        )

        if self._state == "paused":
            resume_act = menu.addAction("▶  Resume")
            resume_act.triggered.connect(lambda: self.resume_requested.emit(self._row_id))
            stop_act = menu.addAction("⏹  Stop / Remove")
            stop_act.triggered.connect(lambda: self.stop_requested.emit(self._row_id))
        elif self._state in ("running", "queued"):
            pause_act = menu.addAction("⏸  Pause")
            pause_act.triggered.connect(lambda: self.pause_requested.emit(self._row_id))
            stop_act = menu.addAction("⏹  Stop / Cancel")
            stop_act.triggered.connect(lambda: self.stop_requested.emit(self._row_id))
        elif self._state == "failed":
            resume_act = menu.addAction("↻  Retry / Resume")
            resume_act.triggered.connect(lambda: self.retry_requested.emit(self._row_id))
            stop_act = menu.addAction("⏹  Remove")
            stop_act.triggered.connect(lambda: self.stop_requested.emit(self._row_id))
        else:  # done
            stop_act = menu.addAction("🗑  Remove from Queue")
            stop_act.triggered.connect(lambda: self.stop_requested.emit(self._row_id))

        pos = self.dots_btn.mapToGlobal(QPoint(0, self.dots_btn.height()))
        menu.exec(pos)
