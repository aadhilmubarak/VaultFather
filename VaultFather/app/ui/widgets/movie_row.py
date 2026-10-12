from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox, QPushButton
)
from PySide6.QtCore import Qt, Signal

from app.core.movie_scanner import MovieFile
from app.ui.widgets.checkable_combo import CheckableComboBox

STATUS_LABEL = {
    "not_backed_up": "Not backed up",
    "backed_up": "Backed up",
    "failed": "Failed",
    "queued": "Queued",
    "archiving": "Archiving…",
    "uploading": "Uploading…",
}


class MovieRow(QFrame):
    """
    One row in the Movies list: checkbox, filename, size/duration/status,
    a multi-select destination picker (upload the same movie to more
    than one channel), and a queue button.
    """

    selection_changed = Signal(str, bool)     # path, checked
    queue_requested = Signal(str, list)       # path, [destination, ...]

    def __init__(self, movie: MovieFile, destinations: list[str],
                 status: str = "not_backed_up", parent=None):
        super().__init__(parent)
        self.setObjectName("QueueRow")  # reuse the same glass row styling
        self.movie = movie

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 13, 14, 13)
        layout.setSpacing(14)

        self.checkbox = QCheckBox()
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.toggled.connect(lambda checked: self.selection_changed.emit(self.movie.path, checked))
        layout.addWidget(self.checkbox)

        thumb = QLabel("🎬")
        thumb.setObjectName("QueueThumb")
        thumb.setFixedSize(42, 42)
        thumb.setAlignment(Qt.AlignCenter)
        layout.addWidget(thumb)

        info_col = QVBoxLayout()
        info_col.setSpacing(5)

        title_row = QHBoxLayout()
        title_label = QLabel(movie.name)
        title_label.setStyleSheet("font-size: 13.5px; font-weight: 600;")
        title_row.addWidget(title_label, stretch=1)

        status_chip = QLabel(STATUS_LABEL.get(status, status))
        status_chip.setObjectName("StatusChip")
        status_chip.setProperty("state", status)
        title_row.addWidget(status_chip)
        info_col.addLayout(title_row)
        self.status_chip = status_chip

        meta_label = QLabel(f"{movie.size_human}  ·  {movie.duration_human}")
        meta_label.setStyleSheet("font-size: 11px; color: #6E6795;")
        info_col.addWidget(meta_label)

        layout.addLayout(info_col, stretch=1)

        self.destination_combo = CheckableComboBox(destinations)
        self.destination_combo.setMinimumWidth(160)
        layout.addWidget(self.destination_combo)

        queue_btn = QPushButton("+ Queue")
        queue_btn.setObjectName("GhostButton")
        queue_btn.setCursor(Qt.PointingHandCursor)
        queue_btn.clicked.connect(
            lambda: self.queue_requested.emit(self.movie.path, self.destination_combo.checked_items())
        )
        layout.addWidget(queue_btn)
        self.queue_btn = queue_btn

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def selected_destinations(self) -> list[str]:
        return self.destination_combo.checked_items()

    def set_status(self, status: str) -> None:
        self.status_chip.setText(STATUS_LABEL.get(status, status))
        self.status_chip.setProperty("state", status)
        self.status_chip.style().unpolish(self.status_chip)
        self.status_chip.style().polish(self.status_chip)

        in_flight = status in ("queued", "archiving", "uploading")
        self.queue_btn.setEnabled(not in_flight)
        self.queue_btn.setText("In queue" if in_flight else "+ Queue")
