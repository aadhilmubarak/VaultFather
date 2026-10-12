from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

from app.ui.widgets.season_row import SeasonRow


class SeriesQueueDialog(QDialog):
    """Opens when a series' poster is clicked — bigger poster, series
    name, and every season listed underneath (same season rows used in
    the old Series view), each queueable independently."""

    def __init__(self, series_name: str, seasons: dict, destinations: list[str],
                 queue_manager, poster_path: str | None = None, parent=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self.setWindowTitle(series_name)
        self.setMinimumWidth(440)
        self.setMinimumHeight(420)
        self.setStyleSheet("QDialog { background-color: #14112C; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(14)
        if poster_path:
            pixmap = QPixmap(poster_path)
            if not pixmap.isNull():
                poster_label = QLabel()
                scaled = pixmap.scaled(90, 135, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                poster_label.setPixmap(scaled)
                poster_label.setStyleSheet("border-radius: 8px;")
                header.addWidget(poster_label)

        title = QLabel(series_name)
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #F3F1FF;")
        header.addWidget(title, stretch=1)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(10)

        for season_number in sorted(seasons.keys()):
            episodes = seasons[season_number]
            row = SeasonRow(season_number, episodes, destinations)
            row.queue_requested.connect(
                lambda season_num, dests, sn=series_name, eps=episodes, r=row:
                    self._on_queue(sn, season_num, eps, dests, r)
            )
            container_layout.addWidget(row)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

    def _on_queue(self, series_name: str, season_number: int, episodes: list, destinations: list[str], row: SeasonRow) -> None:
        if not destinations:
            return
        self.queue_manager.add_series_season(series_name, season_number, episodes, destinations)
        row.set_queued()
