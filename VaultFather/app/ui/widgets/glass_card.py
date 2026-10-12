from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient
from PySide6.QtCore import Qt, QRectF


class GlassCard(QFrame):
    """
    Cyber Obsidian Glass panel — the foundational building block.

    Renders a deep translucent fill with a faint cyan hairline border.
    Pass glow_color to add a neon drop-shadow (use sparingly).
    Set accent=True to paint a thin cyan gradient line along the top edge
    (used for stat cards and highlighted panels).
    """

    def __init__(self, parent=None,
                 glow_color: QColor | None = None,
                 accent: bool = False):
        super().__init__(parent)
        self.setObjectName("GlassCard")
        self._accent = accent

        if glow_color is not None:
            fx = QGraphicsDropShadowEffect(self)
            fx.setBlurRadius(48)
            fx.setOffset(0, 0)
            fx.setColor(glow_color)
            self.setGraphicsEffect(fx)
