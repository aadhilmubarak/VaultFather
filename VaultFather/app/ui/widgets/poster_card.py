from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QCheckBox, QGraphicsDropShadowEffect
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtCore import Qt, Signal

from app.core.poster_loader import poster_loader
from app.core.poster_service import _cache_key

POSTER_WIDTH = 150
POSTER_HEIGHT = 225  # standard 2:3 poster aspect ratio

STATUS_DOT_COLORS = {
    "not_backed_up": None,               # no badge — nothing noteworthy yet
    "backed_up": "#35F0A6",
    "failed": "#FF5C7A",
    "queued": "#B3ACD9",
    "archiving": "#33E6FF",
    "uploading": "#33E6FF",
}


class PosterCard(QFrame):
    """
    One tile in the Netflix-style grid — a poster (fetched async via the
    shared poster_loader, showing a placeholder until/unless one's
    found), a title underneath, a small status-color corner dot, and an
    optional selection checkbox for bulk actions. Clicking the poster
    itself (not the checkbox) emits `activated` — the page decides what
    that means (open a queue dialog for a movie, open a season list for
    a series).
    """

    activated = Signal()
    selection_changed = Signal(bool)

    def __init__(self, title: str, poster_title: str, poster_year: str | None,
                 media_type: str = "movie", status: str | None = None,
                 selectable: bool = True, parent=None):
        super().__init__(parent)
        self.setFixedWidth(POSTER_WIDTH)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- Poster ---
        self.poster_frame = QFrame()
        self.poster_frame.setFixedSize(POSTER_WIDTH, POSTER_HEIGHT)
        self.poster_frame.setStyleSheet(
            "background-color: #1A1638; border-radius: 12px; border: 1px solid rgba(150,130,255,36);"
        )
        glow = QGraphicsDropShadowEffect(self.poster_frame)
        glow.setBlurRadius(24)
        glow.setOffset(0, 4)
        glow.setColor(QColor(0, 0, 0, 140))
        self.poster_frame.setGraphicsEffect(glow)

        poster_layout = QVBoxLayout(self.poster_frame)
        poster_layout.setContentsMargins(0, 0, 0, 0)

        self.poster_label = QLabel("🎬")
        self.poster_label.setAlignment(Qt.AlignCenter)
        self.poster_label.setStyleSheet("font-size: 32px; color: #6E6795; background: transparent; border: none;")
        poster_layout.addWidget(self.poster_label)

        if selectable:
            self.checkbox = QCheckBox(self.poster_frame)
            self.checkbox.move(8, 8)
            self.checkbox.toggled.connect(self.selection_changed.emit)
        else:
            self.checkbox = None

        self.status_dot = QLabel(self.poster_frame)
        self.status_dot.setFixedSize(12, 12)
        self.status_dot.move(POSTER_WIDTH - 20, 8)
        self._set_status_dot(status)

        layout.addWidget(self.poster_frame)

        # --- Title ---
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setFixedWidth(POSTER_WIDTH)
        title_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #F3F1FF;")
        title_label.setMaximumHeight(34)
        layout.addWidget(title_label)

        self._request_poster(poster_title, poster_year, media_type)

    def _set_status_dot(self, status: str | None) -> None:
        color = STATUS_DOT_COLORS.get(status) if status else None
        if color:
            self.status_dot.setStyleSheet(
                f"background-color: {color}; border-radius: 6px; border: 2px solid #1A1638;"
            )
            self.status_dot.show()
        else:
            self.status_dot.hide()

    def _request_poster(self, poster_title: str, poster_year: str | None, media_type: str) -> None:
        self._cache_key = _cache_key(poster_title, poster_year, media_type)
        cached = poster_loader.request(poster_title, poster_year, media_type)
        if cached:
            self._apply_poster(cached)
        else:
            poster_loader.poster_ready.connect(self._on_poster_ready)

    def _on_poster_ready(self, key: str, path: str) -> None:
        if key != self._cache_key:
            return
        poster_loader.poster_ready.disconnect(self._on_poster_ready)
        if path:
            self._apply_poster(path)

    def _apply_poster(self, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            POSTER_WIDTH, POSTER_HEIGHT, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        self.poster_label.setPixmap(scaled)
        self.poster_label.setStyleSheet("background: transparent; border: none;")

    def set_status(self, status: str | None) -> None:
        self._set_status_dot(status)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked() if self.checkbox else False

    def set_checked(self, value: bool) -> None:
        if self.checkbox:
            self.checkbox.setChecked(value)

    def mousePressEvent(self, event):
        if self.checkbox and self.checkbox.geometry().contains(event.position().toPoint()):
            return  # let the checkbox handle its own click
        self.activated.emit()
        super().mousePressEvent(event)
