"""
Runs Telegram login on a background thread and bridges it to Qt via
signals, so the phone number and verification code can be typed into
real dialog fields instead of a terminal prompt.

The trick: Telethon's client.start() wants synchronous callables for
code_callback/password (it calls them and blocks until they return a
value). Since this whole thing already runs on a background thread
(not the Qt thread), those callables can safely block on a
queue.Queue — they emit a signal asking the dialog to show the right
field, then wait. The dialog puts the typed value into the queue once
the person submits it, which unblocks the callable and lets Telethon
continue. The Qt main thread is never blocked at any point.
"""

import asyncio
import queue
import threading

from PySide6.QtCore import QObject, Signal

from app.core.telegram_client import get_client, TelegramNotConfiguredError


class TelegramLoginWorker(QObject):
    session_check_done = Signal(bool)          # already_authorized
    code_needed = Signal()
    password_needed = Signal()                  # 2FA
    login_succeeded = Signal(str)                # display name
    login_failed = Signal(str)
    channels_loaded = Signal(list)               # list of (id, title)
    channels_failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._code_queue: queue.Queue = queue.Queue()
        self._password_queue: queue.Queue = queue.Queue()

    # ---------- Called from the dialog (Qt thread) ----------

    def submit_code(self, code: str) -> None:
        self._code_queue.put(code)

    def submit_password(self, password: str) -> None:
        self._password_queue.put(password)

    def check_session_async(self) -> None:
        threading.Thread(target=self._check_session, daemon=True).start()

    def login_async(self, phone: str) -> None:
        threading.Thread(target=self._login, args=(phone,), daemon=True).start()

    def load_channels_async(self) -> None:
        threading.Thread(target=self._load_channels, daemon=True).start()

    # ---------- Background thread work ----------

    def _check_session(self) -> None:
        async def _run():
            try:
                client = get_client()
            except TelegramNotConfiguredError:
                self.session_check_done.emit(False)
                return
            await client.connect()
            try:
                authorized = await client.is_user_authorized()
                self.session_check_done.emit(authorized)
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except Exception as exc:
            self.login_failed.emit(str(exc))

    def _login(self, phone: str) -> None:
        def get_code():
            self.code_needed.emit()
            return self._code_queue.get()

        def get_password():
            self.password_needed.emit()
            return self._password_queue.get()

        async def _run():
            client = get_client()
            await client.connect()
            try:
                await client.start(phone=phone, code_callback=get_code, password=get_password)
                me = await client.get_me()
                name = f"{me.first_name} (@{me.username or 'no username'})"
                self.login_succeeded.emit(name)
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except Exception as exc:
            self.login_failed.emit(str(exc))

    def _load_channels(self) -> None:
        async def _run():
            client = get_client()
            await client.connect()
            try:
                channels = [
                    (d.id, d.name) async for d in client.iter_dialogs() if d.is_channel
                ]
                self.channels_loaded.emit(channels)
            finally:
                await client.disconnect()

        try:
            asyncio.run(_run())
        except Exception as exc:
            self.channels_failed.emit(str(exc))
