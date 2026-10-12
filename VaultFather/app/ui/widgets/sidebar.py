"""
Cyber Obsidian Transparent Sidebar — navigation panel with neon glow states
and branded header, with background board removed as requested.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QLinearGradient, QColor

from app.ui.widgets.logo_image import LogoImage

NAV_ITEMS = ["Dashboard", "Movies", "Subtitles", "Cloud", "Backup History", "Settings"]


class _NavButton(QPushButton):
    """Single nav item — text label, cyan glow when active."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self._label_text = label
        self._active = False
        self.setObjectName("NavItem")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(f"  {label}")
        self.setMinimumHeight(44)

    def setActive(self, active: bool):
        self._active = active
        self.setChecked(active)
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    """
    Left navigation panel with clean transparent background.
    Emits nav_changed(label) when a tab is selected.
    """

    nav_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(210)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(0)

        # ── Brand header ────────────────────────────────────────────────────
        brand = QHBoxLayout()
        brand.setSpacing(10)

        logo = LogoImage(height=38)
        brand.addWidget(logo)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)

        title_lbl = QLabel("VAULTFATHER")
        title_lbl.setStyleSheet(
            "font-size: 14px; font-weight: 800; color: #00F0FF; letter-spacing: 2px;"
        )
        sub_lbl = QLabel("MOVIE VAULT")
        sub_lbl.setStyleSheet(
            "font-size: 9px; font-weight: 600; color: #3D5A7A; letter-spacing: 1.5px;"
        )
        brand_text.addWidget(title_lbl)
        brand_text.addWidget(sub_lbl)
        brand.addLayout(brand_text)
        brand.addStretch()
        layout.addLayout(brand)

        # ── Divider ─────────────────────────────────────────────────────────
        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: rgba(0,240,255,25); margin: 14px 0 18px 0;")
        layout.addWidget(divider)

        # ── Nav items ────────────────────────────────────────────────────────
        self._buttons: dict[str, _NavButton] = {}
        nav_col = QVBoxLayout()
        nav_col.setSpacing(4)

        for label in NAV_ITEMS:
            btn = _NavButton(label)
            btn.clicked.connect(lambda checked, l=label: self._select(l))
            nav_col.addWidget(btn)
            self._buttons[label] = btn

        layout.addLayout(nav_col)
        layout.addStretch()

        self._select(NAV_ITEMS[0])

    def _select(self, label: str) -> None:
        for name, btn in self._buttons.items():
            btn.setActive(name == label)
        self.nav_changed.emit(label)
