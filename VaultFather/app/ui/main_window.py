"""
VaultFather Main Window — Futuristic Spacecraft Command UI.

Features:
  • Real-time rotating top 100 movies backdrops from TMDb changing every 7 seconds.
  • Dashboard background displays the sharp cinematic backdrop with deep vignette.
  • Other tabs (Movies, Backup History, Settings) display the softly blurred version
    of the current movie backdrop so content remains perfectly readable.
  • Updates the Dashboard's Cinema Spotlight HUD with the current movie title, year,
    overview, and IMDb link.
  • Frameless always-fullscreen spacecraft command shell.
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QPushButton
from PySide6.QtGui import QPainter, QRadialGradient, QColor, QIcon, QLinearGradient, QPixmap, QCursor
from PySide6.QtCore import QPointF, Qt, QTimer, QRect, QEvent, QPropertyAnimation

class WindowControlsOverlay(QWidget):
    """
    Always-visible window controls overlay for frameless window.
    Positions Minimize, Maximize/Restore, and Close buttons flush in the top-right corner.
    """
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedSize(138, 28)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        btn_style = """
            QPushButton {
                background: transparent;
                color: #B3ACD9;
                font-family: "Segoe UI", -apple-system, sans-serif;
                font-size: 13px;
                font-weight: bold;
                border: none;
                border-radius: 0px;
            }
            QPushButton:hover {
                background: rgba(0, 240, 255, 0.16);
                color: #00F0FF;
            }
            QPushButton:pressed {
                background: rgba(0, 240, 255, 0.28);
            }
            QPushButton#close:hover {
                background: #E81123;
                color: #FFFFFF;
            }
            QPushButton#close:pressed {
                background: #BA0E1C;
                color: #FFFFFF;
            }
        """

        self.min_btn = QPushButton("—")
        self.min_btn.setFixedSize(46, 28)
        self.min_btn.setCursor(Qt.PointingHandCursor)
        self.min_btn.setToolTip("Minimize")
        self.min_btn.setStyleSheet(btn_style)
        self.min_btn.clicked.connect(self._minimize_window)

        self.max_btn = QPushButton("□")
        self.max_btn.setFixedSize(46, 28)
        self.max_btn.setCursor(Qt.PointingHandCursor)
        self.max_btn.setToolTip("Restore / Maximize")
        self.max_btn.setStyleSheet(btn_style)
        self.max_btn.clicked.connect(self._toggle_maximize)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("close")
        self.close_btn.setFixedSize(46, 28)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setToolTip("Close")
        self.close_btn.setStyleSheet(btn_style)
        self.close_btn.clicked.connect(parent.close)

        lay.addWidget(self.min_btn)
        lay.addWidget(self.max_btn)
        lay.addWidget(self.close_btn)

        self.sync_state()

    def _minimize_window(self):
        if self.parent():
            self.parent().showMinimized()

    def _toggle_maximize(self):
        parent = self.parent()
        if not parent:
            return
        if parent.isMaximized():
            parent.showNormal()
        else:
            parent.showMaximized()
        self.sync_state()

    def sync_state(self):
        parent = self.parent()
        if parent:
            if parent.isMaximized():
                self.max_btn.setText("⧉")
                self.max_btn.setToolTip("Restore Down")
            else:
                self.max_btn.setText("□")
                self.max_btn.setToolTip("Maximize")
            self.update_position()

    def update_position(self):
        parent = self.parent()
        if parent:
            x = parent.width() - self.width()
            y = 0
            self.move(max(0, x), y)
            self.raise_()


from app.theme.tokens import Colors
from app.ui.widgets.logo_image import LOGO_PATH
from app.ui.widgets.sidebar import Sidebar, NAV_ITEMS
from app.ui.pages.dashboard_page import DashboardPage
from app.ui.pages.movies_page import MoviesPage
from app.ui.pages.subtitles_page import SubtitlesPage
from app.ui.pages.cloud_page import CloudPage
from app.ui.pages.backup_history_page import BackupHistoryPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.placeholder_page import PlaceholderPage
from app.ui.widgets.embedded_player_widget import EmbeddedPlayerWidget
from app.core.top_movies_bg_service import TopMoviesBackgroundService

PLACEHOLDER_NOTES: dict[str, str] = {}


class MainWindow(QMainWindow):
    """Application shell — sidebar + page stack + embedded player overlay."""

    def __init__(self, queue_manager):
        super().__init__()
        self.queue_manager = queue_manager
        self.setWindowTitle("VaultFather")
        self.setObjectName("AppBackground")
        self.setWindowIcon(QIcon(str(LOGO_PATH)))

        # Full-screen always-on with taskbar minimize support
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowMinimizeButtonHint)
        self.showMaximized()
        self._setup_taskbar_minimize()

        # Dynamic Movie Backdrop Storage
        self._current_backdrop: QPixmap | None = None
        self._current_blurred: QPixmap | None = None
        self._scaled_backdrop: QPixmap | None = None
        self._scaled_blurred: QPixmap | None = None
        self._last_size: tuple | None = None
        self._current_nav: str = NAV_ITEMS[0]

        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(12, 28, 12, 12)
        root.setSpacing(14)

        self.sidebar = Sidebar()
        self.sidebar.nav_changed.connect(self._on_nav_changed)
        root.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, stretch=1)

        # Embedded player (shown over the stack when playing)
        self.player_widget = EmbeddedPlayerWidget()
        self.player_widget.closed.connect(self._on_player_closed)

        self._pages: dict[str, QWidget] = {}
        self._build_pages()
        self._on_nav_changed(NAV_ITEMS[0])

        # Initialize and start Top 100 Movies Background Service
        self._bg_service = TopMoviesBackgroundService(self)
        self._bg_service.movie_changed.connect(self._on_bg_movie_changed)
        self._bg_service.start()
        
        # Always-visible Window Controls Overlay (top-right: minimize, screen/maximize, close)
        self.controls_overlay = WindowControlsOverlay(self)
        self.controls_overlay.show()
        self.controls_overlay.sync_state()
        self.controls_overlay.raise_()

    def _build_pages(self) -> None:
        dashboard_page = DashboardPage(self.queue_manager)
        dashboard_page.prev_bg_requested.connect(lambda: self._bg_service.show_previous())
        dashboard_page.next_bg_requested.connect(lambda: self._bg_service.show_next())
        self._pages["Dashboard"] = dashboard_page

        movies_page = MoviesPage(self.queue_manager)
        movies_page.play_requested.connect(self._on_play_movie)
        self._pages["Movies"] = movies_page

        self._pages["Subtitles"] = SubtitlesPage()

        cloud_page = CloudPage(self.queue_manager)
        cloud_page.play_requested.connect(self._on_play_movie)
        self._pages["Cloud"] = cloud_page

        self._pages["Backup History"] = BackupHistoryPage()
        self._pages["Settings"] = SettingsPage(
            on_database_cleared=self._on_database_cleared
        )

        for label in NAV_ITEMS:
            if label not in self._pages:
                self._pages[label] = PlaceholderPage(
                    label, PLACEHOLDER_NOTES.get(label, "")
                )

        for label in NAV_ITEMS:
            self.stack.addWidget(self._pages[label])

        # Player sits at the end of the stack — swapped in on demand
        self.stack.addWidget(self.player_widget)

    def _setup_taskbar_minimize(self) -> None:
        """Enables native Windows taskbar icon minimize toggle for frameless window."""
        import sys
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = int(self.winId())
                GWL_STYLE = -16
                WS_MINIMIZEBOX = 0x00020000
                WS_SYSMENU = 0x00080000
                style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_MINIMIZEBOX | WS_SYSMENU)
            except Exception:
                pass

    # ── Background movie rotation (every 7 seconds) ──────────────────────────

    def _on_bg_movie_changed(self, pixmap: QPixmap, blurred_pixmap: QPixmap,
                             title: str, year: str, plot: str, imdb_url: str):
        self._current_backdrop = pixmap
        self._current_blurred = blurred_pixmap
        # Invalidate cached scaled copies so they're rebuilt on next paint
        self._scaled_backdrop = None
        self._scaled_blurred = None

        # Update the spotlight box on Dashboard
        dashboard = self._pages.get("Dashboard")
        if dashboard and hasattr(dashboard, "update_movie_spotlight"):
            dashboard.update_movie_spotlight(title, year, plot, imdb_url)

        # Repaint window background smoothly
        self.update()

    # ── Navigation ──────────────────────────────────────────────────────────

    def _on_nav_changed(self, label: str) -> None:
        self._current_nav = label
        self.stack.setCurrentWidget(self._pages[label])
        if hasattr(self, "controls_overlay"):
            self.controls_overlay.raise_()
        # Repaint so Dashboard gets sharp backdrop and other tabs get blurred
        self.update()


    # ── Player lifecycle ─────────────────────────────────────────────────────

    def _on_play_movie(self, movie_path: str, title: str) -> None:
        from app.core.vlc_launcher import play_movie
        from PySide6.QtWidgets import QMessageBox
        try:
            play_movie(movie_path)
        except Exception as exc:
            QMessageBox.critical(self, "Playback Error", f"Could not launch media player:\n{exc}")

    def _on_player_closed(self) -> None:
        self.sidebar.show()
        self.stack.setCurrentWidget(self._pages["Movies"])
        movies = self._pages["Movies"]
        if hasattr(movies, "_scan_and_populate"):
            movies._scan_and_populate()

    # ── DB cleared (settings) ────────────────────────────────────────────────

    def _on_database_cleared(self) -> None:
        self._pages["Dashboard"]._refresh_stats()
        self._pages["Dashboard"]._refresh_queue()
        self._pages["Backup History"].refresh()
        movies = self._pages["Movies"]
        if hasattr(movies, "_scan_and_populate"):
            movies._scan_and_populate()

    # ── Window Drag & Double-Click Titlebar Behavior ────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 50:
            if self.windowHandle():
                self.windowHandle().startSystemMove()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 50:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
            if hasattr(self, "controls_overlay"):
                self.controls_overlay.sync_state()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "controls_overlay"):
            self.controls_overlay.update_position()
            self.controls_overlay.raise_()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            if hasattr(self, "controls_overlay"):
                self.controls_overlay.sync_state()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "controls_overlay"):
            self.controls_overlay.sync_state()
            self.controls_overlay.raise_()

    # ── Keyboard shortcuts ───────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            if self.isFullScreen():
                self.showMaximized()
            else:
                pass  # Fullscreen always-on
        else:
            super().keyPressEvent(event)

    # ── Dynamic Background Painting ──────────────────────────────────────────

    def paintEvent(self, event):
        """
        Paints dynamic TMDb top 100 movie backdrops with cached scaling:
          - Dashboard: Sharp backdrop with deep atmospheric vignette
          - Other tabs: Softly blurred backdrop for high UI contrast
        Scaled pixmaps are cached per-size so rescaling only happens when
        the window is resized or a new backdrop arrives — not on every tab switch.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        w, h = rect.width(), rect.height()

        # 1. Deep void base
        painter.fillRect(rect, QColor(8, 7, 20))

        # 2. Movie Backdrop — rebuild scaled cache only when size changes
        is_dashboard = (self._current_nav == "Dashboard")
        current_size = (w, h)
        if self._last_size != current_size:
            self._scaled_backdrop = None
            self._scaled_blurred = None
            self._last_size = current_size

        if is_dashboard:
            if self._scaled_backdrop is None and self._current_backdrop and not self._current_backdrop.isNull():
                self._scaled_backdrop = self._current_backdrop.scaled(
                    w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
            active_pix = self._scaled_backdrop
        else:
            if self._scaled_blurred is None and self._current_blurred and not self._current_blurred.isNull():
                self._scaled_blurred = self._current_blurred.scaled(
                    w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
            active_pix = self._scaled_blurred

        if active_pix and not active_pix.isNull():
            sx = (active_pix.width() - w) // 2
            sy = (active_pix.height() - h) // 2
            painter.save()
            painter.setOpacity(0.58 if is_dashboard else 0.40)
            painter.drawPixmap(0, 0, active_pix, sx, sy, w, h)
            painter.restore()

        # 3. Soft vignette gradient over background
        vignette = QRadialGradient(QPointF(w * 0.5, h * 0.5), max(w, h) * 0.75)
        vignette.setColorAt(0.0, QColor(8, 7, 20, 60))
        vignette.setColorAt(0.65, QColor(8, 7, 20, 150))
        vignette.setColorAt(1.0, QColor(8, 7, 20, 205))
        painter.fillRect(rect, vignette)

        # 4. Sci-Fi spacecraft neon ambient glows
        g1 = QRadialGradient(QPointF(w * 0.12, h * 0.05), w * 0.45)
        g1.setColorAt(0.0, QColor(0, 240, 255, 30))
        g1.setColorAt(1.0, QColor(0, 240, 255, 0))
        painter.fillRect(rect, g1)

        g2 = QRadialGradient(QPointF(w * 0.90, h * 0.05), w * 0.40)
        g2.setColorAt(0.0, QColor(123, 47, 247, 30))
        g2.setColorAt(1.0, QColor(123, 47, 247, 0))
        painter.fillRect(rect, g2)

        g3 = QRadialGradient(QPointF(w * 0.5, h * 1.0), w * 0.45)
        g3.setColorAt(0.0, QColor(0, 255, 200, 18))
        g3.setColorAt(1.0, QColor(0, 255, 200, 0))
        painter.fillRect(rect, g3)

        super().paintEvent(event)
