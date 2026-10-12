"""
Global Qt Stylesheet — Cyber Obsidian Glass.

Key design principles implemented here:
  * Deep translucent panels with cyan hairline borders.
  * Neon glow on focus / hover states built with border + background tints.
  * Thin scanline scrollbars.
  * All sizes / colours come from tokens, never hardcoded.
"""

from app.theme.tokens import Colors, Fonts, Radii


def get_stylesheet() -> str:
    c = Colors
    f = Fonts
    r = Radii

    return f"""
    /* === Base === */
    QWidget {{
        background: transparent;
        color: {c.TEXT_HI};
        font-family: {f.BODY};
        font-size: {f.SIZE_BODY}px;
        selection-background-color: rgba(0, 240, 255, 60);
    }}
    QMainWindow, #AppBackground {{
        background: {c.BG_VOID};
    }}

    /* === Typography === */
    QLabel[role="h1"] {{
        font-family: {f.DISPLAY};
        font-size: 20px;
        font-weight: 800;
        color: {c.CYAN};
        letter-spacing: 1px;
    }}
    QLabel[role="h2"] {{
        font-family: {f.DISPLAY};
        font-size: {f.SIZE_H2}px;
        font-weight: 600;
        color: {c.TEXT_HI};
    }}
    QLabel[role="h3"] {{
        font-family: {f.DISPLAY};
        font-size: {f.SIZE_H3}px;
        font-weight: 600;
        color: {c.TEXT_MID};
        letter-spacing: 0.3px;
    }}
    QLabel[role="subtitle"] {{
        font-size: {f.SIZE_BODY}px;
        color: {c.TEXT_LOW};
    }}
    QLabel[role="caption"] {{
        font-size: {f.SIZE_SMALL}px;
        color: {c.TEXT_LOW};
    }}
    QLabel[role="statValue"] {{
        font-family: {f.DISPLAY};
        font-size: 28px;
        font-weight: 700;
        color: {c.CYAN};
        letter-spacing: -0.5px;
    }}
    QLabel[role="neon"] {{
        color: {c.CYAN};
        font-weight: 700;
    }}

    /* === Glass panels === */
    QFrame#GlassCard {{
        background-color: {c.PANEL};
        border: 1px solid {c.PANEL_BORDER};
        border-radius: {r.PANEL}px;
    }}

    /* === Sidebar === */
    QFrame#Sidebar {{
        background-color: rgba(8, 6, 22, 210);
        border: 1px solid rgba(0, 240, 255, 22);
        border-radius: {r.PANEL}px;
    }}
    QPushButton#NavItem {{
        text-align: left;
        padding: 11px 16px;
        border-radius: 11px;
        border: 1px solid rgba(0, 240, 255, 30);
        background-color: rgba(14, 11, 32, 220);
        color: {c.TEXT_MID};
        font-size: {f.SIZE_BODY}px;
        font-weight: 600;
    }}
    QPushButton#NavItem:hover {{
        background-color: rgba(0, 240, 255, 45);
        color: #FFFFFF;
        border: 1px solid rgba(0, 240, 255, 75);
    }}
    QPushButton#NavItem[active="true"] {{
        color: {c.CYAN};
        background-color: rgba(0, 240, 255, 55);
        border: 1px solid rgba(0, 240, 255, 120);
        font-weight: 700;
    }}

    /* === Primary Button === */
    QPushButton#PrimaryButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c.CYAN}, stop:1 {c.VIOLET});
        color: #080714;
        border: none;
        border-radius: {r.BUTTON}px;
        padding: 10px 20px;
        font-weight: 700;
        font-size: {f.SIZE_BODY}px;
    }}
    QPushButton#PrimaryButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #33F5FF, stop:1 #9B5FFF);
    }}
    QPushButton#PrimaryButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #00C8D5, stop:1 #6020CC);
    }}
    QPushButton#PrimaryButton:disabled {{
        background: rgba(0, 240, 255, 20);
        color: {c.TEXT_LOW};
    }}

    /* === Ghost Button === */
    QPushButton#GhostButton {{
        background-color: rgba(0, 240, 255, 8);
        color: {c.TEXT_MID};
        border: 1px solid rgba(0, 240, 255, 38);
        border-radius: {r.BUTTON}px;
        padding: 9px 18px;
        font-weight: 600;
        font-size: {f.SIZE_BODY}px;
    }}
    QPushButton#GhostButton:hover {{
        background-color: rgba(0, 240, 255, 18);
        color: {c.CYAN};
        border-color: rgba(0, 240, 255, 80);
    }}
    QPushButton#GhostButton:pressed {{
        background-color: rgba(0, 240, 255, 30);
    }}

    /* === Backup Queue rows === */
    QFrame#QueueRow {{
        background-color: rgba(0, 240, 255, 4);
        border: 1px solid rgba(0, 240, 255, 20);
        border-radius: {r.CARD}px;
    }}
    QFrame#QueueRow:hover {{
        background-color: rgba(0, 240, 255, 8);
        border-color: rgba(0, 240, 255, 45);
    }}
    QLabel#QueueThumb {{
        background-color: {c.BG_DEEP};
        border-radius: 10px;
        border: 1px solid rgba(0, 240, 255, 20);
    }}
    QLabel#QueueTag {{
        font-size: 9px;
        font-weight: 700;
        padding: 3px 9px;
        border-radius: {r.PILL}px;
        color: {c.TEXT_LOW};
        background-color: rgba(255, 255, 255, 10);
        letter-spacing: 0.5px;
    }}
    QLabel#QueueTag[tone="resume"] {{
        color: {c.AMBER};
        background-color: rgba(255, 179, 71, 28);
        border: 1px solid rgba(255, 179, 71, 50);
    }}
    QLabel#QueueTag[tone="done"] {{
        color: {c.MINT};
        background-color: rgba(0, 255, 200, 25);
        border: 1px solid rgba(0, 255, 200, 50);
    }}
    QLabel#QueueTag[tone="failed"] {{
        color: {c.RED};
        background-color: rgba(255, 51, 102, 25);
        border: 1px solid rgba(255, 51, 102, 50);
    }}
    QPushButton#QueueAction {{
        background-color: rgba(0, 240, 255, 10);
        border: 1px solid rgba(0, 240, 255, 30);
        border-radius: 8px;
        color: {c.TEXT_MID};
        font-size: 12px;
        padding: 2px 8px;
    }}
    QPushButton#QueueAction:hover {{
        background-color: rgba(0, 240, 255, 22);
        color: {c.CYAN};
    }}
    QPushButton#QueueAction[tone="resume"] {{
        background-color: rgba(255, 179, 71, 30);
        border-color: rgba(255, 179, 71, 60);
        color: {c.AMBER};
    }}

    /* === Duplicate notice === */
    QFrame#DupeNotice {{
        background-color: rgba(255, 51, 206, 12);
        border: 1px solid rgba(255, 51, 206, 50);
        border-radius: {r.CARD}px;
    }}
    QPushButton#DupeCancel {{
        background-color: rgba(255,255,255,10);
        color: {c.TEXT_MID};
        border: 1px solid rgba(255,255,255,20);
        border-radius: 8px;
        padding: 7px 13px;
        font-weight: 600;
        font-size: 11px;
    }}
    QPushButton#DupeAnyway {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c.MAGENTA}, stop:1 {c.VIOLET});
        color: white;
        border: none;
        border-radius: 8px;
        padding: 7px 13px;
        font-weight: 700;
        font-size: 11px;
    }}

    /* === Checkbox === */
    QCheckBox {{ color: {c.TEXT_MID}; spacing: 8px; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px;
        border-radius: 5px;
        border: 1.5px solid rgba(0, 240, 255, 40);
        background-color: rgba(0, 240, 255, 5);
    }}
    QCheckBox::indicator:hover {{
        border-color: {c.CYAN};
        background-color: rgba(0, 240, 255, 12);
    }}
    QCheckBox::indicator:checked {{
        background-color: {c.CYAN};
        border-color: {c.CYAN};
    }}

    /* === ComboBox === */
    QComboBox {{
        background-color: rgba(0, 240, 255, 7);
        border: 1px solid rgba(0, 240, 255, 35);
        border-radius: {r.CHIP}px;
        padding: 7px 12px;
        color: {c.TEXT_MID};
        font-size: 12px;
        min-width: 130px;
    }}
    QComboBox:hover {{
        border-color: {c.CYAN};
        color: {c.TEXT_HI};
        background-color: rgba(0, 240, 255, 14);
    }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background-color: {c.BG_SURFACE};
        border: 1px solid rgba(0, 240, 255, 50);
        border-radius: {r.CHIP}px;
        color: {c.TEXT_HI};
        selection-background-color: rgba(0, 240, 255, 50);
        outline: none;
        padding: 4px;
    }}

    /* === Status chips === */
    QLabel#StatusChip {{
        font-size: 10px; font-weight: 700;
        padding: 3px 10px;
        border-radius: {r.PILL}px;
        letter-spacing: 0.4px;
    }}
    QLabel#StatusChip[state="backed_up"] {{
        color: {c.MINT}; background-color: rgba(0,255,200,25);
        border: 1px solid rgba(0,255,200,50);
    }}
    QLabel#StatusChip[state="not_backed_up"] {{
        color: {c.TEXT_LOW}; background-color: rgba(255,255,255,10);
        border: 1px solid rgba(255,255,255,18);
    }}
    QLabel#StatusChip[state="failed"] {{
        color: {c.RED}; background-color: rgba(255,51,102,25);
        border: 1px solid rgba(255,51,102,50);
    }}
    QLabel#StatusChip[state="queued"] {{
        color: {c.TEXT_MID}; background-color: rgba(0,240,255,10);
        border: 1px solid rgba(0,240,255,25);
    }}
    QLabel#StatusChip[state="archiving"], QLabel#StatusChip[state="uploading"] {{
        color: {c.CYAN}; background-color: rgba(0,240,255,22);
        border: 1px solid rgba(0,240,255,60);
    }}

    /* === Search / LineEdit === */
    QLineEdit {{
        background-color: rgba(0, 240, 255, 7);
        border: 1px solid rgba(0, 240, 255, 35);
        border-radius: {r.CHIP}px;
        padding: 8px 13px;
        color: {c.TEXT_HI};
        font-size: 12.5px;
    }}
    QLineEdit:focus {{
        border: 1.5px solid {c.CYAN};
        background-color: rgba(0, 240, 255, 13);
    }}

    /* === Scrollbars === */
    QScrollBar:vertical {{
        background: transparent; width: 6px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: rgba(0, 240, 255, 50);
        border-radius: 3px; min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c.CYAN}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent; height: 6px;
    }}
    QScrollBar::handle:horizontal {{
        background: rgba(0, 240, 255, 50);
        border-radius: 3px; min-width: 20px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {c.CYAN}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

    /* === Progress bar === */
    QProgressBar {{
        background-color: rgba(0, 240, 255, 12);
        border: none; border-radius: 4px; height: 6px; text-align: center;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c.CYAN}, stop:1 {c.MINT});
        border-radius: 4px;
    }}

    /* === Tooltip === */
    QToolTip {{
        background-color: {c.BG_SURFACE};
        color: {c.TEXT_HI};
        border: 1px solid rgba(0, 240, 255, 50);
        padding: 6px 11px; border-radius: 8px; font-size: 11.5px;
    }}

    /* === Dialog === */
    QDialog {{ background-color: {c.BG_DEEP}; }}

    /* === Tabs === */
    QTabWidget::pane {{
        background: transparent;
        border: 1px solid rgba(0, 240, 255, 25);
        border-radius: 14px;
    }}
    QTabBar::tab {{
        background: transparent; color: {c.TEXT_LOW};
        padding: 8px 18px; border: none;
        font-weight: 600; font-size: 12px;
    }}
    QTabBar::tab:hover {{ color: {c.TEXT_MID}; }}
    QTabBar::tab:selected {{
        color: {c.CYAN};
        border-bottom: 2px solid {c.CYAN};
    }}
    """
