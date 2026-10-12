"""
Runs the Google OAuth connect flow on a background thread — it opens a
real browser window and blocks until the person finishes signing in,
so it can never run on the Qt UI thread.
"""

import threading

from PySide6.QtCore import QObject, Signal

from app.core.google_drive_service import run_oauth_login, GoogleNotConfiguredError


class GoogleLoginWorker(QObject):
    login_succeeded = Signal(str)   # connected email
    login_failed = Signal(str)

    def connect_async(self) -> None:
        threading.Thread(target=self._connect, daemon=True).start()

    def _connect(self) -> None:
        try:
            email = run_oauth_login()
            self.login_succeeded.emit(email)
        except GoogleNotConfiguredError as exc:
            self.login_failed.emit(str(exc))
        except Exception as exc:
            self.login_failed.emit(f"Couldn't connect: {exc}")
