from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt, Signal


class DuplicateNotice(QFrame):
    """
    "This movie was already backed up..." prompt, shown before re-uploading
    something that already has a successful backup on record.
    """

    cancelled = Signal()
    upload_anyway = Signal()

    def __init__(self, movie_title: str, destination: str, date: str, parent=None):
        super().__init__(parent)
        self.setObjectName("DupeNotice")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        icon = QLabel("⚠")
        icon.setFixedSize(34, 34)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(
            "background-color: rgba(255,63,206,40); border-radius: 10px;"
            "color: #FF3FCE; font-size: 15px;"
        )
        layout.addWidget(icon)

        text = QLabel(
            f"Already backed up: <b>{movie_title}</b> was archived to "
            f"{destination} on <b>{date}</b>."
        )
        text.setWordWrap(True)
        text.setStyleSheet("font-size: 12.5px; color: #B3ACD9;")
        layout.addWidget(text, stretch=1)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("DupeCancel")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.cancelled.emit)
        layout.addWidget(cancel_btn)

        anyway_btn = QPushButton("Upload Anyway")
        anyway_btn.setObjectName("DupeAnyway")
        anyway_btn.setCursor(Qt.PointingHandCursor)
        anyway_btn.clicked.connect(self.upload_anyway.emit)
        layout.addWidget(anyway_btn)
