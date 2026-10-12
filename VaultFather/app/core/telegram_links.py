"""
Opens a Telegram message link with a real priority order: try the
installed desktop/mobile app first via a tg:// deep link, and only if
the OS reports no handler for that scheme, fall back to the plain
https://t.me/ URL in a browser.

This distinction matters because Excel hyperlinks can't run this kind
of fallback logic themselves (see excel_export.py, which uses the
https://t.me/ link directly for that reason) — but here, inside the
app, we get to check whether the app-open attempt actually worked and
react accordingly.
"""

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices


def build_telegram_links(channel_id: int | str, message_id: str) -> tuple[str, str]:
    """Returns (tg_deep_link, https_fallback_link) for one message."""
    clean_id = str(channel_id).removeprefix("-100").removeprefix("-")
    tg_link = f"tg://privatepost?channel={clean_id}&post={message_id}"
    https_link = f"https://t.me/c/{clean_id}/{message_id}"
    return tg_link, https_link


def open_telegram_message(channel_id: int | str, message_id: str) -> None:
    """
    Tries the Telegram app first; QDesktopServices.openUrl() returns
    False when the OS has no handler registered for the tg:// scheme
    (i.e. Telegram isn't installed), in which case this falls back to
    opening the https:// link in the default browser.
    """
    tg_link, https_link = build_telegram_links(channel_id, message_id)
    opened = QDesktopServices.openUrl(QUrl(tg_link))
    if not opened:
        QDesktopServices.openUrl(QUrl(https_link))
