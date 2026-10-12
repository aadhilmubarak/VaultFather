import sys

from PySide6.QtWidgets import QApplication

from app.theme.style import get_stylesheet
from app.ui.main_window import MainWindow
from app.core.queue_manager import QueueManager
from app.core.database import migrate_legacy_single_channel, migrate_split_backup_tables
from app.core.backup_scheduler import backup_scheduler


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(get_stylesheet())

    migrate_legacy_single_channel()
    migrate_split_backup_tables()

    queue_manager = QueueManager()
    window = MainWindow(queue_manager)
    window.show()

    # Fires off in the background if a Drive backup is due today —
    # no-ops instantly (and harmlessly) if Drive isn't connected yet.
    backup_scheduler.maybe_run_daily_backup()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
