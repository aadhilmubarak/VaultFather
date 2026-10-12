from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QLinearGradient, QColor
from PySide6.QtCore import Qt, QRectF

from app.theme.tokens import Colors


class StatusTrack(QWidget):
    """
    The transparent -> green progress bar used in Backup Queue rows.

    state controls the color language:
      - "running" / "done"  -> green gradient, soft glow
      - "paused"             -> amber gradient (interrupted upload)
      - "queued"              -> flat, no glow, waiting its turn
    """

    def __init__(self, percent: float = 0, state: str = "queued", parent=None):
        super().__init__(parent)
        self._percent = percent
        self._state = state
        self.setFixedHeight(7)
        self.setMinimumWidth(80)

    def set_progress(self, percent: float, state: str) -> None:
        self._percent = max(0.0, min(100.0, percent))
        self._state = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())

        # Track
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 15))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        if self._percent <= 0 or self._state == "queued":
            return

        fill_width = rect.width() * (self._percent / 100)
        fill_rect = QRectF(0, 0, fill_width, rect.height())

        gradient = QLinearGradient(fill_rect.topLeft(), fill_rect.topRight())
        if self._state == "paused":
            gradient.setColorAt(0.0, QColor(255, 179, 71, 40))
            gradient.setColorAt(1.0, QColor(Colors.AMBER))
        elif self._state == "failed":
            gradient.setColorAt(0.0, QColor(255, 92, 122, 40))
            gradient.setColorAt(1.0, QColor(Colors.RED))
        else:  # running or done
            gradient.setColorAt(0.0, QColor(0, 240, 255, 60))
            gradient.setColorAt(1.0, QColor(Colors.CYAN))

        painter.setBrush(gradient)
        painter.drawRoundedRect(fill_rect, rect.height() / 2, rect.height() / 2)
