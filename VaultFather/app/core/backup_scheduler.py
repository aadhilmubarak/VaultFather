"""
Runs the Drive backup once per day, automatically. Since VaultFather
isn't a background service — it only does things while actually
open — "daily" means: check once whenever the app starts, and if
today's date doesn't match the last recorded backup date, do it now.
"""

import tempfile
import threading
from datetime import date

from PySide6.QtCore import QObject, Signal

from app.core.config import load_config, save_config
from app.core.excel_export import export_backup_history
from app.core.google_drive_service import upload_backup_file, has_saved_token
from app.core.logger import get_logger

logger = get_logger()


class BackupScheduler(QObject):
    backup_succeeded = Signal(str)   # date string
    backup_failed = Signal(str)      # error message

    def __init__(self):
        super().__init__()

    def maybe_run_daily_backup(self) -> None:
        """Call this on startup. No-ops instantly if backup isn't due
        — safe to call often."""
        config = load_config()
        if not config.get("google_drive_daily_backup", True):
            return
        if not has_saved_token():
            return

        today = date.today().isoformat()
        if config.get("last_drive_backup_date") == today:
            return

        threading.Thread(target=self._run_backup, args=(today,), daemon=True).start()

    def run_backup_now(self) -> None:
        """Manual trigger from Settings — runs regardless of whether
        today's automatic backup already happened."""
        threading.Thread(target=self._run_backup, args=(date.today().isoformat(),), daemon=True).start()

    def _run_backup(self, today: str) -> None:
        from app.core.google_drive_service import GoogleNotConnectedError
        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            export_backup_history(tmp_path)
            upload_backup_file(tmp_path)

            config = load_config()
            config["last_drive_backup_date"] = today
            save_config(config)

            self.backup_succeeded.emit(today)
        except GoogleNotConnectedError:
            # Token was revoked or never set up — silently skip, no popup.
            # The stale token (if any) was already deleted by _load_credentials().
            logger.info("Google Drive backup skipped: not connected or token revoked.")
        except Exception as exc:
            logger.exception("Daily Google Drive backup failed")
            self.backup_failed.emit(str(exc))


backup_scheduler = BackupScheduler()
