from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.ui.widgets.checkable_combo import CheckableComboBox


class MovieQueueDialog(QDialog):
    """Opens when a movie's poster is clicked — bigger poster, details,
    and the destination picker + Queue action in one place, instead of
    packing controls into the grid tile itself."""

    def __init__(self, movie, destinations: list[str], poster_path: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(movie.name)
        self.setMinimumWidth(360)
        self.setStyleSheet("QDialog { background-color: #14112C; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        if poster_path:
            pixmap = QPixmap(poster_path)
            if not pixmap.isNull():
                poster_label = QLabel()
                scaled = pixmap.scaled(160, 240, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                poster_label.setPixmap(scaled)
                poster_label.setStyleSheet("border-radius: 10px;")
                layout.addWidget(poster_label, alignment=Qt.AlignHCenter)

        title = QLabel(movie.name)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F3F1FF;")
        layout.addWidget(title)

        meta = QLabel(f"{movie.size_human}  ·  {movie.duration_human}")
        meta.setStyleSheet("color: #B3ACD9; font-size: 12px;")
        layout.addWidget(meta)

        layout.addWidget(QLabel("Send to:"))
        self.destination_combo = CheckableComboBox(destinations)
        layout.addWidget(self.destination_combo)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = GhostButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        queue_btn = PrimaryButton("+ Queue")
        queue_btn.clicked.connect(self.accept)
        btn_row.addWidget(queue_btn)
        layout.addLayout(btn_row)

    def selected_destinations(self) -> list[str]:
        return self.destination_combo.checked_items()
