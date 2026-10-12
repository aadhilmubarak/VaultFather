from PySide6.QtWidgets import QWidget, QGraphicsDropShadowEffect
from PySide6.QtGui import QPainter, QPen, QConicalGradient, QColor, QFont
from PySide6.QtCore import Qt, QRectF

from app.theme.tokens import Colors


class ProgressRing(QWidget):
    """
    A glowing cyber obsidian progress ring widget.
    Renders real-time percentage and phase caption ("UPLOADING", "ARCHIVING", etc.)
    fully fitted inside the circle without overflow.
    """

    def __init__(self, size: int = 120, pen_width: int | None = None, parent=None):
        super().__init__(parent)
        self._percent: float | None = None
        self._main_text: str = ""
        self._caption: str = ""
        self._pen_width = pen_width or max(8, int(size * 0.08))
        self.setFixedSize(size, size)

        glow = QGraphicsDropShadowEffect(self)
        glow.setBlurRadius(size * 0.6)
        glow.setOffset(0, 0)
        glow.setColor(QColor(0, 240, 255, 180))
        self.setGraphicsEffect(glow)

    def set_value(self, percent: float | None, main_text: str = "", caption: str = "") -> None:
        """percent=None means idle (dim ring, dash in center)."""
        self._percent = percent
        self._main_text = main_text
        self._caption = caption
        self.update()

    def set_progress(self, percent: float | None, state: str = "running") -> None:
        """Convenience method matching standard progress contracts."""
        caption = state.upper() if state not in ("running", "idle") else ""
        self.set_value(percent, caption=caption)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        side = min(self.width(), self.height())
        margin = self._pen_width
        rect = QRectF(
            (self.width() - side) / 2 + margin,
            (self.height() - side) / 2 + margin,
            side - margin * 2,
            side - margin * 2,
        )

        is_idle = self._percent is None

        # Track background arc
        track_pen = QPen(QColor(255, 255, 255, 16))
        track_pen.setWidth(self._pen_width)
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        # Real-time progress arc
        if not is_idle:
            gradient = QConicalGradient(rect.center(), 90)
            gradient.setColorAt(0.0, QColor(Colors.CYAN))
            gradient.setColorAt(0.55, QColor(Colors.VIOLET))
            gradient.setColorAt(1.0, QColor(Colors.MAGENTA))

            prog_pen = QPen(gradient, self._pen_width)
            prog_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(prog_pen)

            span_angle = int(-360 * 16 * (max(0.0, min(100.0, self._percent)) / 100))
            painter.drawArc(rect, 90 * 16, span_angle)

        # Content text inside circle
        has_caption = bool(self._caption)
        if not is_idle:
            main_text = self._main_text if self._main_text else f"{int(self._percent)}%"
        else:
            main_text = self._main_text if self._main_text else "—"

        inner_rect = rect.adjusted(4, 4, -4, -4)

        # Main percentage / text
        painter.setPen(QColor(Colors.TEXT_HI if not is_idle else Colors.TEXT_LOW))
        big_font = QFont("Inter", max(10, int(side * (0.13 if len(main_text) <= 4 else 0.09))), QFont.Bold)
        painter.setFont(big_font)

        if has_caption:
            # Lift main percentage up slightly
            top_rect = QRectF(inner_rect.x(), inner_rect.y() + side * 0.08, inner_rect.width(), side * 0.38)
            painter.drawText(top_rect, Qt.AlignCenter, main_text)

            # Draw "UPLOADING" / "ARCHIVING" caption inside circle below percentage
            painter.setPen(QColor("#00F0FF" if not is_idle else Colors.TEXT_LOW))
            small_font = QFont("Inter", max(7, int(side * 0.065)), QFont.Bold)
            painter.setFont(small_font)
            bot_rect = QRectF(inner_rect.x(), inner_rect.y() + side * 0.44, inner_rect.width(), side * 0.30)
            painter.drawText(bot_rect, Qt.AlignCenter, self._caption.upper())
        else:
            painter.drawText(inner_rect, Qt.AlignCenter, main_text)
