"""
Dialog to connect/authenticate a Telegram account.
Uses TelegramLoginWorker for the async Telethon flow.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QStackedWidget, QWidget, QLabel,
    QLineEdit, QHBoxLayout, QMessageBox
)
from PySide6.QtCore import Qt
from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.core.telegram_login import TelegramLoginWorker
from app.core.config import load_config, save_config

def set_telegram_credentials(api_id: int, api_hash: str) -> None:
    config = load_config()
    config["telegram_api_id"] = api_id
    config["telegram_api_hash"] = api_hash
    save_config(config)

class TelegramAccountDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect Telegram Account")
        self.setMinimumWidth(420)
        self.setStyleSheet("QDialog { background-color: #14112C; }")

        self._worker = TelegramLoginWorker()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(26, 26, 26, 26)
        outer.setSpacing(16)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self._build_checking_step()      # index 0
        self._build_credentials_step()   # index 1
        self._build_phone_step()         # index 2
        self._build_code_step()          # index 3
        self._build_password_step()      # index 4
        self._build_success_step()       # index 5
        self._build_error_step()         # index 6

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
        self.stack.addWidget(page)

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
        self.stack.addWidget(page)

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
        self.stack.addWidget(page)

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
        self.stack.addWidget(page)

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
        self.stack.addWidget(page)

    def _build_success_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(10)

        title = QLabel("Successfully connected!")
        title.setProperty("role", "h3")
        title.setStyleSheet("color: #00FFC8;")
        layout.addWidget(title)
        
        self.success_label = QLabel("Logged in as ...")
        self.success_label.setProperty("role", "subtitle")
        layout.addWidget(self.success_label)

        btn = PrimaryButton("Close")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)
        self.stack.addWidget(page)

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
        self.stack.addWidget(page)

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
        if not code:
            return
        self.stack.setCurrentIndex(0)
        self._worker.submit_code(code)

    def _submit_password(self):
        pwd = self.password_input.text()
        if not pwd:
            return
        self.stack.setCurrentIndex(0)
        self._worker.submit_password(pwd)

    # ---------- Worker Signals ----------

    def _connect_worker(self):
        self._worker.session_check_done.connect(self._on_session_check_done)
        self._worker.code_needed.connect(lambda: self.stack.setCurrentIndex(3))
        self._worker.password_needed.connect(lambda: self.stack.setCurrentIndex(4))
        self._worker.login_succeeded.connect(self._on_login_succeeded)
        self._worker.login_failed.connect(self._on_login_failed)

    def _on_session_check_done(self, authorized: bool):
        if authorized:
            self.success_label.setText("Your Telegram session is active.")
            self.stack.setCurrentIndex(5)  # success
        else:
            self.stack.setCurrentIndex(2)  # phone

    def _on_login_succeeded(self, display_name: str):
        self.success_label.setText(f"Logged in as {display_name}")
        self.stack.setCurrentIndex(5)  # success

    def _on_login_failed(self, error: str):
        self.error_label.setText(f"Login failed:\n{error}")
        self.stack.setCurrentIndex(6)  # error
