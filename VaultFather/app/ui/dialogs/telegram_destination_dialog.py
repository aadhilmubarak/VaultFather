from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QStackedWidget, QWidget, QCheckBox, QRadioButton, QButtonGroup, QScrollArea
)
from PySide6.QtCore import Qt

from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.core.telegram_login import TelegramLoginWorker
from app.core.config import load_config, set_telegram_credentials
from app.core.database import add_destination, list_destinations


class TelegramDestinationDialog(QDialog):
    """
    One dialog that covers Telegram channel setup for both Backup Destinations
    and dedicated Unwatched Wishlist channel.

    When is_unwatched_mode=True:
      Allows selecting one channel as the unwatched wishlist channel without
      adding it to the backup destinations database table.
    """

    def __init__(self, parent=None, is_unwatched_mode: bool = False):
        super().__init__(parent)
        self.is_unwatched_mode = is_unwatched_mode
        self.setWindowTitle("Connect Unwatched Wishlist Channel" if is_unwatched_mode else "Add Telegram Destination")
        self.setMinimumWidth(420)
        self.setStyleSheet("QDialog { background-color: #14112C; }")

        self._worker = TelegramLoginWorker()
        self._added_names: list[str] = []
        self._selected_unwatched: tuple[int, str] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 26, 26, 26)
        outer.setSpacing(16)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self._build_checking_step()
        self._build_credentials_step()
        self._build_phone_step()
        self._build_code_step()
        self._build_password_step()
        self._build_channels_step()
        self._build_error_step()

        self._connect_worker()
        self._start()

    # ---------- Steps ----------

    def _build_checking_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        label = QLabel("Checking your Telegram session…")
        label.setProperty("role", "subtitle")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)
        self.stack.addWidget(page)  # index 0

    def _build_credentials_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("Connect your Telegram account")
        title.setProperty("role", "h3")
        layout.addWidget(title)

        info = QLabel(
            "First time only — get these free from my.telegram.org: log in with "
            "your phone number, open \"API development tools,\" and register an app."
        )
        info.setWordWrap(True)
        info.setProperty("role", "caption")
        layout.addWidget(info)

        self.api_id_input = QLineEdit()
        self.api_id_input.setPlaceholderText("api_id")
        layout.addWidget(self.api_id_input)

        self.api_hash_input = QLineEdit()
        self.api_hash_input.setPlaceholderText("api_hash")
        layout.addWidget(self.api_hash_input)

        self.credentials_error = QLabel("")
        self.credentials_error.setStyleSheet("color: #FF5C7A; font-size: 11.5px;")
        self.credentials_error.hide()
        layout.addWidget(self.credentials_error)

        btn = PrimaryButton("Continue")
        btn.clicked.connect(self._submit_credentials)
        layout.addWidget(btn)

        self.stack.addWidget(page)  # index 1

    def _build_phone_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("Enter your phone number")
        title.setProperty("role", "h3")
        layout.addWidget(title)

        info = QLabel("Include the country code, e.g. +1 555 123 4567.")
        info.setProperty("role", "caption")
        layout.addWidget(info)

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+1 555 123 4567")
        layout.addWidget(self.phone_input)

        btn = PrimaryButton("Send Code")
        btn.clicked.connect(self._submit_phone)
        layout.addWidget(btn)

        self.stack.addWidget(page)  # index 2

    def _build_code_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("Enter the code")
        title.setProperty("role", "h3")
        layout.addWidget(title)

        info = QLabel("Telegram just sent a login code to your app.")
        info.setProperty("role", "caption")
        layout.addWidget(info)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("12345")
        layout.addWidget(self.code_input)

        btn = PrimaryButton("Verify")
        btn.clicked.connect(self._submit_code)
        layout.addWidget(btn)

        self.stack.addWidget(page)  # index 3

    def _build_password_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("Two-step verification")
        title.setProperty("role", "h3")
        layout.addWidget(title)

        info = QLabel("Enter your Telegram cloud password.")
        info.setProperty("role", "caption")
        layout.addWidget(info)

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.password_input)

        btn = PrimaryButton("Verify")
        btn.clicked.connect(self._submit_password)
        layout.addWidget(btn)

        self.stack.addWidget(page)  # index 4

    def _build_channels_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self.channels_title = QLabel(
            "Choose channel for your Unwatched Wishlist" if self.is_unwatched_mode else "Choose channels to back up to"
        )
        self.channels_title.setProperty("role", "h3")
        layout.addWidget(self.channels_title)

        self.channels_status = QLabel("Loading your channels…")
        self.channels_status.setProperty("role", "caption")
        layout.addWidget(self.channels_status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setMaximumHeight(220)

        self.channels_container = QWidget()
        self.channels_layout = QVBoxLayout(self.channels_container)
        self.channels_layout.setSpacing(6)
        scroll.setWidget(self.channels_container)
        layout.addWidget(scroll)

        btn = PrimaryButton("Connect Wishlist Channel" if self.is_unwatched_mode else "Add Selected")
        btn.clicked.connect(self._add_selected_channels)
        layout.addWidget(btn)

        self.stack.addWidget(page)  # index 5

    def _build_error_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #FF5C7A; font-size: 13px;")
        layout.addWidget(self.error_label)

        retry_btn = GhostButton("Close")
        retry_btn.clicked.connect(self.reject)
        layout.addWidget(retry_btn)

        self.stack.addWidget(page)  # index 6

    # ---------- Flow ----------

    def _start(self):
        config = load_config()
        if not config.get("telegram_api_id") or not config.get("telegram_api_hash"):
            self.stack.setCurrentIndex(1)  # credentials
            return
        self.stack.setCurrentIndex(0)  # checking
        self._worker.check_session_async()

    def _submit_credentials(self):
        try:
            api_id = int(self.api_id_input.text().strip())
        except ValueError:
            self.credentials_error.setText("api_id should be a number.")
            self.credentials_error.show()
            return
        api_hash = self.api_hash_input.text().strip()
        if not api_hash:
            self.credentials_error.setText("api_hash can't be empty.")
            self.credentials_error.show()
            return

        set_telegram_credentials(api_id, api_hash)
        self.stack.setCurrentIndex(0)
        self._worker.check_session_async()

    def _submit_phone(self):
        phone = self.phone_input.text().strip()
        if not phone:
            return
        self.stack.setCurrentIndex(0)
        self._worker.login_async(phone)

    def _submit_code(self):
        code = self.code_input.text().strip()
        if code:
            self._worker.submit_code(code)
            self.stack.setCurrentIndex(0)

    def _submit_password(self):
        password = self.password_input.text()
        if password:
            self._worker.submit_password(password)
            self.stack.setCurrentIndex(0)

    def _connect_worker(self):
        w = self._worker
        w.session_check_done.connect(self._on_session_checked)
        w.code_needed.connect(lambda: self.stack.setCurrentIndex(3))
        w.password_needed.connect(lambda: self.stack.setCurrentIndex(4))
        w.login_succeeded.connect(self._on_login_succeeded)
        w.login_failed.connect(self._on_error)
        w.channels_loaded.connect(self._on_channels_loaded)
        w.channels_failed.connect(self._on_error)

    def _on_session_checked(self, already_authorized: bool):
        if already_authorized:
            self.stack.setCurrentIndex(5)  # channels
            self._worker.load_channels_async()
        else:
            self.stack.setCurrentIndex(2)  # phone

    def _on_login_succeeded(self, _display_name: str):
        self.stack.setCurrentIndex(5)
        self._worker.load_channels_async()

    def _on_channels_loaded(self, channels: list):
        self.channels_status.setText(
            f"{len(channels)} channel{'s' if len(channels) != 1 else ''} found."
            if channels else "No channels found — create one in Telegram first."
        )

        while self.channels_layout.count():
            item = self.channels_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.is_unwatched_mode:
            self._radio_group = QButtonGroup(self)
            self._channel_radios = []
            for channel_id, title in channels:
                radio = QRadioButton(title)
                radio.setStyleSheet("QRadioButton { color: #E8F4FF; font-size: 12px; }")
                self.channels_layout.addWidget(radio)
                self._radio_group.addButton(radio)
                self._channel_radios.append((channel_id, title, radio))
            if self._channel_radios:
                self._channel_radios[0][2].setChecked(True)
        else:
            existing_names = {d.name for d in list_destinations()}
            self._channel_checkboxes = []
            for channel_id, title in channels:
                checkbox = QCheckBox(title)
                if title in existing_names:
                    checkbox.setText(f"{title}  (already added)")
                    checkbox.setEnabled(False)
                self.channels_layout.addWidget(checkbox)
                self._channel_checkboxes.append((channel_id, title, checkbox))

    def _add_selected_channels(self):
        if self.is_unwatched_mode:
            for channel_id, title, radio in getattr(self, "_channel_radios", []):
                if radio.isChecked():
                    self._selected_unwatched = (channel_id, title)
                    break
        else:
            for channel_id, title, checkbox in getattr(self, "_channel_checkboxes", []):
                if checkbox.isChecked() and checkbox.isEnabled():
                    add_destination(title, channel_id)
                    self._added_names.append(title)
        self.accept()

    def _on_error(self, message: str):
        self.error_label.setText(message)
        self.stack.setCurrentIndex(6)

    def added_destination_names(self) -> list[str]:
        return self._added_names

    def selected_unwatched_channel(self) -> tuple[int, str] | None:
        return getattr(self, "_selected_unwatched", None)
