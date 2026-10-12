"""
Sci-Fi Futuristic Audio & Telemetry Sine Wave Visualizer:
Renders dynamic real-time sine waves whose amplitude, frequency, and harmonic turbulence
react directly to active upload speed, network throughput, and audio/data carrier rate.
Includes visual frequency spectrum peaks, telemetry channel status, and dBm carrier scale.
"""

import math
import time
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QPainterPath, QLinearGradient,
    QFont, QBrush
)

from app.core.upload_history_tracker import UploadHistoryTracker
from app.core.movie_scanner import human_size


class SciFiHudSineWidget(QWidget):
    """
    Functional sine wave telemetry visualizer.
    Directly connected to live upload throughput — modulates wave amplitude and frequency
    in real time according to current upload speed.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(115)
        self._phase = 0.0
        self._current_speed_bps = 0.0
        self._current_job_name = ""

        # Connect to upload history tracker
        tracker = UploadHistoryTracker.instance()
        tracker.data_updated.connect(self._on_tracker_updated)

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 FPS
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_live_speed(self, speed_bps: float, job_name: str = ""):
        self._current_speed_bps = max(0.0, speed_bps)
        self._current_job_name = job_name

    def _on_tracker_updated(self):
        pts = UploadHistoryTracker.instance().get_points()
        if pts:
            self._current_speed_bps = pts[-1].speed_bps
            self._current_job_name = pts[-1].job_name

    def _tick(self):
        # Wave phase speed increases with higher upload throughput
        speed_factor = min(3.0, 1.0 + (self._current_speed_bps / (1024 * 1024 * 15)))
        self._phase += 0.05 * speed_factor
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Semi-transparent dark glass backing
        p.fillRect(self.rect(), QColor(10, 8, 26, 90))

        # Background coordinate reticle lines
        grid_pen = QPen(QColor(0, 240, 255, 14), 1)
        p.setPen(grid_pen)
        for x in range(0, w, 45):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 24):
            p.drawLine(0, y, w, y)

        # Calculate amplitude based on real activity
        # If idle, show a subtle resting carrier wave (~6px); when uploading, scales up to 34px
        mb_rate = self._current_speed_bps / (1024 * 1024)
        has_load = self._current_speed_bps > 0
        base_amp = 8.0 + min(26.0, mb_rate * 2.2) if has_load else 7.0
        freq_mult = 1.0 + min(1.5, mb_rate * 0.1)

        mid_y = h * 0.52

        # ── 1. Dual Harmonic Sine Waves Driven By Live Throughput ──────────
        path1 = QPainterPath()
        path2 = QPainterPath()
        fill_path = QPainterPath()

        points_count = max(50, int(w / 4))
        for i in range(points_count + 1):
            x = (i / points_count) * w
            envelope = math.sin((i / points_count) * math.pi)

            # Wave 1 (Primary Cyan Carrier Wave)
            y1 = mid_y + (math.sin(self._phase + i * 0.10 * freq_mult) * base_amp +
                          math.sin(self._phase * 0.6 + i * 0.04) * (base_amp * 0.4)) * envelope

            # Wave 2 (Harmonic Mint Wave)
            y2 = mid_y + (math.cos(self._phase * 1.3 + i * 0.14 * freq_mult) * (base_amp * 0.75)) * envelope

            if i == 0:
                path1.moveTo(x, y1)
                path2.moveTo(x, y2)
                fill_path.moveTo(x, mid_y)
                fill_path.lineTo(x, y1)
            else:
                path1.lineTo(x, y1)
                path2.lineTo(x, y2)
                fill_path.lineTo(x, y1)

        fill_path.lineTo(w, mid_y)
        fill_path.closeSubpath()

        # Ambient Glow beneath wave
        glow_grad = QLinearGradient(0, mid_y - base_amp, 0, mid_y + base_amp)
        glow_grad.setColorAt(0.0, QColor(0, 240, 255, 35 if has_load else 15))
        glow_grad.setColorAt(1.0, QColor(0, 240, 255, 0))
        p.fillPath(fill_path, glow_grad)

        # Draw Glow Stroke
        glow_pen = QPen(QColor(0, 240, 255, 70 if has_load else 30), 4)
        p.setPen(glow_pen)
        p.drawPath(path1)

        # Draw Sharp Primary Wave (Cyan)
        main_pen = QPen(QColor(0, 240, 255, 230), 1.8)
        p.setPen(main_pen)
        p.drawPath(path1)

        # Draw Harmonic Wave (Mint dashed)
        wave2_pen = QPen(QColor(0, 255, 200, 160), 1.2, Qt.DashLine)
        p.setPen(wave2_pen)
        p.drawPath(path2)

        # ── 2. Real Telemetry Readout & Modulation Meter ──────────────────
        p.setFont(QFont("Consolas", 8, QFont.Bold))
        speed_text = f"{human_size(self._current_speed_bps)}/s" if has_load else "IDLE / STANDBY"
        status_text = f"THROUGHPUT CARRIER WAVE: {speed_text}"
        p.setPen(QColor(0, 240, 255, 210))
        p.drawText(14, 18, status_text)

        osc_dbm = 10.0 + (mb_rate * 3.5) if has_load else 3.2
        mod_status = f"MODULATION: {osc_dbm:.1f} dBm  |  SYNC: LOCK  |  BUFFER: OPTIMAL"
        p.setPen(QColor(139, 168, 200, 160))
        p.drawText(14, h - 10, mod_status)

        # Live spectrum frequency meter on right edge
        spec_x = w - 160
        p.setPen(QColor(0, 240, 255, 120))
        p.drawText(spec_x, 18, "LIVE SPECTRUM")
        bars = 10
        bar_w = 7
        for b in range(bars):
            # Dynamic bar height based on wave oscillation & speed
            bh = 4 + int((math.sin(self._phase * 1.5 + b * 0.7) + 1.0) * (6 + min(12, mb_rate)))
            bx = spec_x + (b * (bar_w + 3))
            by = h - 12 - bh
            bar_color = QColor(0, 255, 200) if b < 7 else QColor(255, 179, 71)
            p.fillRect(bx, by, bar_w, bh, bar_color)

        # Top border scanline
        scan_grad = QLinearGradient(0, 0, w, 0)
        scan_grad.setColorAt(0.0, QColor(0, 240, 255, 0))
        scan_grad.setColorAt(0.3, QColor(0, 240, 255, 160))
        scan_grad.setColorAt(0.7, QColor(0, 255, 200, 160))
        scan_grad.setColorAt(1.0, QColor(0, 240, 255, 0))
        p.fillRect(0, 0, w, 2, scan_grad)
