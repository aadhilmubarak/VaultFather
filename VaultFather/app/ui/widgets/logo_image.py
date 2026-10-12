from pathlib import Path

from PySide6.QtWidgets import QLabel, QGraphicsDropShadowEffect
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtCore import Qt

LOGO_PATH = Path(__file__).resolve().parent.parent.parent / "assets" / "logo.png"


class LogoImage(QLabel):
    """
    VaultFather's brand mark — the real logo artwork (app/assets/logo.png),
    replacing the earlier procedurally-drawn black hole. Scales to a
    target height while preserving aspect ratio (the source art is
    landscape, not square), with the same soft violet glow used
    elsewhere in the theme so it still feels native to the UI rather
    than a pasted-in image.
    """

    def __init__(self, height: int = 40, glow: bool = True, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)

        pixmap = QPixmap(str(LOGO_PATH))
        if not pixmap.isNull():
            scaled = pixmap.scaledToHeight(height, Qt.SmoothTransformation)
            self.setPixmap(scaled)
            self.setFixedSize(scaled.size())
        else:
            # Fallback if the asset is ever missing, so the app doesn't crash.
            self.setText("VF")
            self.setFixedSize(height, height)
            self.setAlignment(Qt.AlignCenter)

        if glow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(height * 0.9)
            effect.setOffset(0, 0)
            effect.setColor(QColor(123, 47, 247, 140))
            self.setGraphicsEffect(effect)
