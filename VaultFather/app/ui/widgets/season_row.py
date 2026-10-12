from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal

from app.ui.widgets.checkable_combo import CheckableComboBox
from app.core.movie_scanner import human_size


class SeasonRow(QFrame):
    """
    One season within a series group in the Series tab — e.g.
    "Season 1 · 3 episodes · 4.2 GB" with a destination picker and a
    queue button. Queueing a season queues every episode in it as its
    own job; VaultFather announces the series name (once, ever) and
    the season label (every time) ahead of the episode files.
    """

    queue_requested = Signal(int, list)   # season_number, [destination, ...]

    def __init__(self, season_number: int, episodes: list, destinations: list[str], parent=None):
        super().__init__(parent)
        self.setObjectName("QueueRow")
        self.season_number = season_number
        self.episodes = episodes

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(14)

        icon = QLabel("📺")
        icon.setObjectName("QueueThumb")
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)

        total_size = sum(e.size_bytes for e in episodes)
        label = QLabel(f"Season {season_number}")
        label.setStyleSheet("font-size: 13px; font-weight: 600;")
        meta = QLabel(f"{len(episodes)} episode{'s' if len(episodes) != 1 else ''} · {human_size(total_size)}")
        meta.setStyleSheet("font-size: 11px; color: #6E6795;")

        text_col_widget = QFrame()
        from PySide6.QtWidgets import QVBoxLayout
        text_col = QVBoxLayout(text_col_widget)
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        text_col.addWidget(label)
        text_col.addWidget(meta)
        layout.addWidget(text_col_widget, stretch=1)

        self.destination_combo = CheckableComboBox(destinations)
        self.destination_combo.setMinimumWidth(160)
        layout.addWidget(self.destination_combo)

        self.queue_btn = QPushButton("+ Queue")
        self.queue_btn.setObjectName("GhostButton")
        self.queue_btn.setCursor(Qt.PointingHandCursor)
        self.queue_btn.clicked.connect(
            lambda: self.queue_requested.emit(self.season_number, self.destination_combo.checked_items())
        )
        layout.addWidget(self.queue_btn)

    def set_queued(self) -> None:
        self.queue_btn.setEnabled(False)
        self.queue_btn.setText("In queue")
