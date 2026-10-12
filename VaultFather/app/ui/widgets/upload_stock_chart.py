"""
Slidable Google Finance / Stock Market Style Upload Speed History Chart:
Interactive telemetry chart with draggable cursor/scrubber timeline, tooltips showing
exact upload time, speed in MB/s, and movie title, just like Google currency exchange
or stock graphs.
"""

import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QPainter, QColor, QPen, QPainterPath, QLinearGradient,
    QFont, QMouseEvent
)

from app.core.upload_history_tracker import UploadHistoryTracker, UploadPoint
from app.core.movie_scanner import human_size


class SlidableStockHistoryWidget(QWidget):
    """
    Shows upload speeds over time like Google currency or stock charts.
    Includes an interactive cursor line that tracks the mouse or slider,
    displaying exact time and upload speed so the user can easily see
    when uploads were slow.
    """

    cursor_moved = Signal(float, float, str)  # (timestamp, speed_bps, movie_name)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setMouseTracking(True)
        self._tracker = UploadHistoryTracker.instance()
        self._tracker.data_updated.connect(self.update)

        self._hover_x: float | None = None
        self._scrubber_ratio: float = 1.0  # 0.0 (oldest) to 1.0 (newest/live)

    def set_scrub_ratio(self, ratio: float):
        self._scrubber_ratio = max(0.0, min(1.0, ratio))
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        self._hover_x = event.position().x()
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_x = None
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad_l, pad_r, pad_t, pad_b = 40, 20, 24, 26

        # Dark glass telemetry background
        p.fillRect(self.rect(), QColor(10, 8, 26, 140))

        # Border
        p.setPen(QPen(QColor(0, 240, 255, 30), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 10, 10)

        points = self._tracker.get_points()

        # Generate realistic default curve if no data has been captured yet
        if len(points) < 2:
            p.setPen(QColor(139, 168, 200, 120))
            font = QFont("Inter", 11)
            p.setFont(font)
            p.drawText(self.rect(), Qt.AlignCenter, "Waiting for upload activity to map telemetry timeline…")
            return

        # Time range and speed range
        t_start = points[0].timestamp
        t_end = points[-1].timestamp
        t_span = max(1.0, t_end - t_start)

        max_speed = max(pt.speed_bps for pt in points)
        if max_speed <= 0:
            max_speed = 1024 * 1024 * 10  # 10 MB/s default scale

        graph_w = w - pad_l - pad_r
        graph_h = h - pad_t - pad_b

        # Grid lines (stock market style)
        grid_pen = QPen(QColor(0, 240, 255, 18), 1, Qt.DashLine)
        p.setPen(grid_pen)
        for i in range(1, 4):
            gy = pad_t + (graph_h * i / 4)
            p.drawLine(pad_l, gy, w - pad_r, gy)

        # Plot path
        path = QPainterPath()
        fill_path = QPainterPath()

        coords = []
        for i, pt in enumerate(points):
            nx = (pt.timestamp - t_start) / t_span
            cx = pad_l + nx * graph_w
            ny = pt.speed_bps / max_speed
            cy = (pad_t + graph_h) - (ny * graph_h)
            coords.append((cx, cy, pt))
            if i == 0:
                path.moveTo(cx, cy)
                fill_path.moveTo(cx, pad_t + graph_h)
                fill_path.lineTo(cx, cy)
            else:
                path.lineTo(cx, cy)
                fill_path.lineTo(cx, cy)

        fill_path.lineTo(coords[-1][0], pad_t + graph_h)
        fill_path.closeSubpath()

        # Gradient fill (Stock chart style)
        fill_grad = QLinearGradient(0, pad_t, 0, pad_t + graph_h)
        fill_grad.setColorAt(0.0, QColor(0, 240, 255, 60))
        fill_grad.setColorAt(0.6, QColor(0, 240, 255, 18))
        fill_grad.setColorAt(1.0, QColor(0, 240, 255, 0))
        p.fillPath(fill_path, fill_grad)

        # Stock market cyan line
        line_pen = QPen(QColor(0, 240, 255), 2.0)
        p.setPen(line_pen)
        p.drawPath(path)

        # ── Interactive Cursor Scrubbing (Mouse or Scrubber) ──────────────
        target_x = self._hover_x if self._hover_x is not None else (pad_l + self._scrubber_ratio * graph_w)
        target_x = max(pad_l, min(w - pad_r, target_x))

        # Find closest point
        closest = min(coords, key=lambda c: abs(c[0] - target_x))
        cur_x, cur_y, cur_pt = closest

        # Vertical cursor line
        p.setPen(QPen(QColor(0, 255, 200, 180), 1.2, Qt.DashLine))
        p.drawLine(cur_x, pad_t, cur_x, pad_t + graph_h)

        # Glowing Point on graph
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 255, 200, 80))
        p.drawEllipse(QPointF(cur_x, cur_y), 7, 7)
        p.setBrush(QColor(232, 244, 255))
        p.drawEllipse(QPointF(cur_x, cur_y), 3.5, 3.5)

        # ── Tooltip Badge at Top ──────────────────────────────────────────
        time_str = time.strftime("%H:%M:%S", time.localtime(cur_pt.timestamp))
        speed_str = f"{human_size(cur_pt.speed_bps)}/s" if cur_pt.speed_bps > 0 else "0 B/s"
        badge_text = f"{time_str}  ·  {speed_str}  ·  {cur_pt.job_name}"

        p.setFont(QFont("Consolas", 9, QFont.Bold))
        # Draw badge pill
        badge_w = 260
        badge_x = min(w - pad_r - badge_w, max(pad_l, cur_x - badge_w / 2))
        badge_rect = QRectF(badge_x, 4, badge_w, 18)

        p.setBrush(QColor(8, 6, 22, 220))
        p.setPen(QPen(QColor(0, 240, 255, 80), 1))
        p.drawRoundedRect(badge_rect, 4, 4)

        p.setPen(QColor(0, 240, 255))
        p.drawText(badge_rect, Qt.AlignCenter, badge_text)
