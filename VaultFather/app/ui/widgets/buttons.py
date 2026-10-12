from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt


class PrimaryButton(QPushButton):
    """Violet -> blue gradient, filled button. Main call-to-action."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("PrimaryButton")
        self.setCursor(Qt.PointingHandCursor)


class GhostButton(QPushButton):
    """Low-emphasis outlined button, for secondary actions."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setObjectName("GhostButton")
        self.setCursor(Qt.PointingHandCursor)
