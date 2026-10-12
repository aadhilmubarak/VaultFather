from datetime import datetime

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel

from app.ui.widgets.buttons import PrimaryButton, GhostButton


class DuplicateConfirmDialog(QDialog):
    """
    Shown before queueing any movie that already has a successful backup
    on record. Lists every duplicate in this batch with where and when
    it was last backed up, and lets the person choose to skip them or
    back them up again anyway (e.g. the source file changed).
    """

    def __init__(self, duplicates: list[tuple[str, str, str]], parent=None):
        # duplicates: list of (movie_name, destination, date_str)
        super().__init__(parent)
        self.setWindowTitle("Already Backed Up")
        self.setMinimumWidth(440)
        self.setStyleSheet("QDialog { background-color: #14112C; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("⚠  Already backed up")
        title.setStyleSheet("color: #FF3FCE; font-size: 15px; font-weight: 700;")
        layout.addWidget(title)

        for name, destination, date in duplicates:
            line = QLabel(f"<b>{name}</b> was already backed up to {destination} on {date}.")
            line.setWordWrap(True)
            line.setStyleSheet(
                "color: #B3ACD9; font-size: 12.5px; padding: 8px 10px;"
                "background-color: rgba(255,63,206,15); border-radius: 10px;"
            )
            layout.addWidget(line)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        skip_btn = GhostButton("Skip These")
        skip_btn.clicked.connect(self.reject)
        btn_row.addWidget(skip_btn)

        anyway_btn = PrimaryButton("Upload Anyway")
        anyway_btn.clicked.connect(self.accept)
        btn_row.addWidget(anyway_btn)

        layout.addLayout(btn_row)


def format_backup_date(iso_timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%d %b")
    except ValueError:
        return iso_timestamp
