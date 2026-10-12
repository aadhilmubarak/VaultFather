"""
Cyber Obsidian Glass — design tokens.

Single source of truth for every colour, radius, font and spacing used in
VaultFather.  All widgets and stylesheets pull from here; change one value
and the whole theme follows.
"""

from PySide6.QtGui import QColor


class Colors:
    # ── Void background ──────────────────────────────────────────────────────
    BG_VOID      = "#080714"          # deepest black-violet — window fill
    BG_DEEP      = "#0E0C1E"          # panel recesses / card bases
    BG_SURFACE   = "#13102A"          # slightly lighter panels

    # ── Glass panels ─────────────────────────────────────────────────────────
    PANEL           = "rgba(14, 11, 32, 95)"        # ultra-clear luminous glass
    PANEL_DARK      = "rgba(8, 6, 20, 115)"         # darker glass variant
    PANEL_SOLID     = "#13102A"                     # opaque fallback
    PANEL_BORDER    = "rgba(0, 240, 255, 38)"       # neon hairline
    PANEL_HOVER     = "rgba(0, 240, 255, 20)"       # hover surface tint

    # ── Neon accents ─────────────────────────────────────────────────────────
    CYAN    = "#00F0FF"   # primary accent — scan-line / glow
    MINT    = "#00FFC8"   # secondary green-teal
    VIOLET  = "#7B2FF7"   # deep violet
    BLUE    = "#2F6BFF"   # electric blue
    MAGENTA = "#FF3FCE"   # hot pink — danger / special

    # ── Status ───────────────────────────────────────────────────────────────
    GREEN = "#00FFC8"    # success / backed-up
    AMBER = "#FFB347"    # warning / pending
    RED   = "#FF3366"    # error / failed

    # ── Text ─────────────────────────────────────────────────────────────────
    TEXT_HI  = "#E8F4FF"    # primary text
    TEXT_MID = "#8BA8C8"    # secondary / labels
    TEXT_LOW = "#3D5A7A"    # tertiary / disabled / captions

    # ── Glow QColor helpers (for QPainter / QGraphicsDropShadowEffect) ───────
    @staticmethod
    def cyan_glow(alpha: int = 80) -> QColor:
        return QColor(0, 240, 255, alpha)

    @staticmethod
    def violet_glow(alpha: int = 80) -> QColor:
        return QColor(123, 47, 247, alpha)

    @staticmethod
    def mint_glow(alpha: int = 80) -> QColor:
        return QColor(0, 255, 200, alpha)


class Fonts:
    DISPLAY = "'Space Grotesk', 'Segoe UI Semibold', 'Segoe UI', sans-serif"
    BODY    = "'Inter', 'Segoe UI', sans-serif"
    MONO    = "'JetBrains Mono', 'Consolas', monospace"

    SIZE_DISPLAY_LG = 34
    SIZE_H1         = 22
    SIZE_H2         = 17
    SIZE_H3         = 14
    SIZE_BODY       = 13
    SIZE_SMALL      = 11


class Radii:
    PANEL  = 20
    CARD   = 14
    PILL   = 20
    BUTTON = 10
    CHIP   = 8


class Spacing:
    XS = 6
    SM = 10
    MD = 16
    LG = 22
    XL = 28
