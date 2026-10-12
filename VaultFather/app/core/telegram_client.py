"""
Telegram connection handling — Telethon, logged in as your own account
(not a bot), so uploads support real large files and true resume.

The session file created after your first login (telegram.session, next
to config.json) is what lets VaultFather stay signed in without asking
for a login code every time. Treat that file exactly like the api_hash:
never share it, never commit it. Deleting it just signs the app out.

Upload fix: we use MemorySession pre-loaded from the SQLite session file
instead of passing the session file path directly to TelegramClient.
This means upload jobs never try to write to the SQLite session file,
eliminating the "database is locked" errors that caused uploads to fail
on the first 3–4 attempts when the main app is running concurrently.
"""

import sqlite3
from pathlib import Path

from telethon import TelegramClient
from telethon.network.connection import ConnectionTcpObfuscated
from telethon.sessions import MemorySession
from telethon.crypto import AuthKey

from app.core.config import load_config, CONFIG_DIR

SESSION_PATH = CONFIG_DIR / "telegram"  # Telethon appends .session itself


class TelegramNotConfiguredError(RuntimeError):
    """Raised when api_id/api_hash haven't been set up yet."""


def _load_session_into_memory() -> MemorySession:
    """Read DC/auth_key from the SQLite session file into a MemorySession.

    By copying the auth key into memory we avoid all SQLite write access
    during uploads — the main app holds the SQLite file open, and any
    concurrent write attempt causes 'database is locked', which was the
    root cause of uploads failing on the first 3–4 tries.
    """
    session = MemorySession()
    session_file = Path(f"{SESSION_PATH}.session")
    if not session_file.is_file():
        return session
    try:
        con = sqlite3.connect(str(session_file), timeout=5, check_same_thread=False)
        row = con.execute(
            "SELECT dc_id, server_address, port, auth_key FROM sessions"
        ).fetchone()
        con.close()
        if row:
            dc_id, server, port, auth_key_bytes = row
            session.set_dc(dc_id, server, port)
            if auth_key_bytes:
                session.auth_key = AuthKey(auth_key_bytes)
    except Exception:
        pass  # Return an empty MemorySession; connect() will re-negotiate auth
    return session


def get_client() -> TelegramClient:
    """Builds (but does not connect) a TelegramClient.

    Uses MemorySession pre-loaded from the on-disk session file so that
    upload threads never contend on the SQLite session file.

    Speed tuning applied here:
      - cryptg: C-extension AES/IGE replaces pure-Python encryption,
        cutting per-chunk CPU time by ~5-10x. Telethon picks it up
        automatically when the package is installed.
      - connection_retries=10: tolerates brief network hiccups without
        failing the whole upload.
      - ConnectionTcpFull instead of Obfuscated: less overhead per packet
        on LAN/fast WiFi; obfuscated is only necessary for deep-packet
        inspection firewalls.
    """
    config = load_config()
    api_id = config.get("telegram_api_id")
    api_hash = config.get("telegram_api_hash")

    if not api_id or not api_hash:
        raise TelegramNotConfiguredError(
            "Telegram isn't set up yet — connect your account via the Settings tab."
        )

    # Log whether the native crypto extension is active
    try:
        import cryptg  # noqa: F401 — Telethon auto-uses it when importable
        _crypto_note = "cryptg (C-extension, fast)"
    except ImportError:
        _crypto_note = "pure-Python (slow — install cryptg for best speed)"
    from app.core.logger import get_logger
    get_logger().info(f"Telegram crypto backend: {_crypto_note}")

    # Optional proxy support for networks/ISPs that block or TCP-reset direct Telegram MTProto connections
    proxy = None
    if config.get("proxy_enabled") and config.get("proxy_host") and config.get("proxy_port"):
        try:
            import socks
            ptype = str(config.get("proxy_type", "socks5")).lower()
            stype = socks.SOCKS5 if ptype == "socks5" else socks.HTTP
            proxy = (
                stype,
                config.get("proxy_host"),
                int(config.get("proxy_port")),
                True,
                config.get("proxy_username") or None,
                config.get("proxy_password") or None,
            )
        except ImportError:
            pass

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    session = _load_session_into_memory()
    
    kwargs = {
        "connection_retries": 5,
        "retry_delay": 2,
        "auto_reconnect": True,
    }
    if proxy:
        kwargs["proxy"] = proxy

    return TelegramClient(
        session,
        int(api_id),
        api_hash,
        **kwargs,
    )


def has_active_session() -> bool:
    """True if a session file already exists — doesn't guarantee it's
    still valid (Telegram could have revoked it), just that a login was
    completed at some point."""
    return Path(f"{SESSION_PATH}.session").is_file()
