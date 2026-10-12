from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

from app.ui.widgets.glass_card import GlassCard


class PlaceholderPage(QWidget):
    """
    Stand-in for a screen that hasn't been built yet. Keeps the nav
    fully clickable during development instead of leaving tabs dead.
    """

    def __init__(self, title: str, note: str, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(20)

        h1 = QLabel(title)
        h1.setProperty("role", "h1")
        root.addWidget(h1)

        card = GlassCard()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(30, 30, 30, 30)

        note_label = QLabel(note)
        note_label.setProperty("role", "subtitle")
        note_label.setAlignment(Qt.AlignCenter)
        note_label.setWordWrap(True)
        card_layout.addWidget(note_label)

        root.addWidget(card, stretch=1)
