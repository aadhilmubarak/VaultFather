from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QMessageBox, QCheckBox, QComboBox, QSlider, QRadioButton, QButtonGroup,
    QScrollArea
)
from PySide6.QtCore import Qt

from app.ui.widgets.glass_card import GlassCard
from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.ui.dialogs.telegram_destination_dialog import TelegramDestinationDialog
from app.ui.dialogs.telegram_account_dialog import TelegramAccountDialog
import os
from app.core.config import CONFIG_DIR
from app.core.database import (
    list_destinations, remove_destination,
    list_movie_backups, list_series_backups, clear_all_backup_history,
)
from app.core.config import load_config, save_config
from app.core.google_drive_service import has_saved_token, disconnect as google_disconnect
from app.core.google_login import GoogleLoginWorker
from app.core.backup_scheduler import backup_scheduler


class SettingsPage(QWidget):
    def __init__(self, on_database_cleared=None, parent=None):
        super().__init__(parent)
        self.on_database_cleared = on_database_cleared

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(4, 0, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        h1 = QLabel("Settings")
        h1.setProperty("role", "h1")
        h1.setFixedHeight(28)
        title_col.addWidget(h1)
        header.addLayout(title_col)
        header.addStretch()
        root.addLayout(header)

        root.addWidget(self._build_speed_booster_section())
        root.addWidget(self._build_engine_section())
        root.addWidget(self._build_posters_section())
        root.addWidget(self._build_telegram_account_section())
        root.addWidget(self._build_google_drive_section())
        root.addWidget(self._build_unwatched_channel_section())
        root.addWidget(self._build_destinations_section())
        root.addWidget(self._build_movie_download_destination_section())
        root.addWidget(self._build_danger_zone())
        root.addStretch()

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)

    # ---------- Help Dialogs ----------

    def _show_help(self, title: str, html_content: str) -> None:
        from PySide6.QtWidgets import QDialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Help: {title}")
        dlg.setMinimumWidth(400)
        dlg.setStyleSheet("background-color: #0E0C22; color: #E8F4FF;")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 20, 20, 20)
        
        lbl = QLabel(html_content)
        lbl.setWordWrap(True)
        lbl.setOpenExternalLinks(True)
        lbl.setStyleSheet("font-size: 13px; line-height: 1.5;")
        lay.addWidget(lbl)
        
        btn = PrimaryButton("Got it")
        btn.clicked.connect(dlg.accept)
        btn_lay = QHBoxLayout()
        btn_lay.addStretch()
        btn_lay.addWidget(btn)
        lay.addLayout(btn_lay)
        dlg.exec()

    def _create_help_btn(self, title: str, html_content: str) -> QPushButton:
        btn = QPushButton("?")
        btn.setFixedSize(22, 22)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 240, 255, 30);
                color: #00F0FF;
                border-radius: 11px;
                font-size: 13px;
                font-weight: 900;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 80);
            }
        """)
        btn.clicked.connect(lambda: self._show_help(title, html_content))
        return btn

    # ---------- Upload Speed Booster ----------

    def _build_speed_booster_section(self) -> GlassCard:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel("Upload Speed Booster (Parallel MTProto Senders)")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #33E6FF;")
        layout.addWidget(title)


        desc = QLabel(
            "Controls the number of simultaneous MTProto sender connections dispatched to Telegram. "
            "Higher streams eliminate single-socket round-trip latency and boost speeds on both Wi-Fi and Ethernet."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #B3ACD9;")
        layout.addWidget(desc)

        config = load_config()
        cur_concurrency = int(config.get("upload_concurrency", 8))

        row = QHBoxLayout()
        row.setSpacing(20)

        self.stream_group = QButtonGroup(self)
        self.r_4 = QRadioButton("4 Streams (Normal)")
        self.r_8 = QRadioButton("8 Streams (Turbo - Recommended)")
        self.r_16 = QRadioButton("16 Streams (Extreme)")

        for r in (self.r_4, self.r_8, self.r_16):
            r.setStyleSheet("QRadioButton { color: #F3F1FF; font-size: 12px; } QRadioButton::indicator:checked { background-color: #33E6FF; }")
            self.stream_group.addButton(r)
            row.addWidget(r)

        if cur_concurrency <= 4:
            self.r_4.setChecked(True)
        elif cur_concurrency >= 16:
            self.r_16.setChecked(True)
        else:
            self.r_8.setChecked(True)

        self.r_4.toggled.connect(lambda: self._set_concurrency(4))
        self.r_8.toggled.connect(lambda: self._set_concurrency(8))
        self.r_16.toggled.connect(lambda: self._set_concurrency(16))

        row.addStretch()
        layout.addLayout(row)
        return card

    def _set_concurrency(self, val: int):
        config = load_config()
        config["upload_concurrency"] = val
        save_config(config)

    # ---------- Archiving & 7-Zip Engine ----------

    def _build_engine_section(self) -> GlassCard:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel("Archiving & Encryption Engine")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F3F1FF;")
        layout.addWidget(title)

        config = load_config()

        # Split size & compression
        row1 = QHBoxLayout()
        row1.setSpacing(16)

        split_col = QVBoxLayout()
        split_col.setSpacing(4)
        split_lbl = QLabel("Split Volume Size (MB):")
        split_lbl.setStyleSheet("font-size: 11.5px; color: #B3ACD9;")
        self.split_input = QLineEdit(str(config.get("split_volume_size_mb") or 1800))
        self.split_input.setPlaceholderText("1800")
        split_col.addWidget(split_lbl)
        split_col.addWidget(self.split_input)
        row1.addLayout(split_col)

        comp_col = QVBoxLayout()
        comp_col.setSpacing(4)
        comp_lbl = QLabel("7z Compression Level:")
        comp_lbl.setStyleSheet("font-size: 11.5px; color: #B3ACD9;")
        self.comp_combo = QComboBox()
        self.comp_combo.addItems(["store (Fastest / No CPU overhead)", "fast", "normal", "max"])
        cur_comp = config.get("compression_level", "store")
        idx = 0 if cur_comp == "store" else (1 if cur_comp == "fast" else (2 if cur_comp == "normal" else 3))
        self.comp_combo.setCurrentIndex(idx)
        comp_col.addWidget(comp_lbl)
        comp_col.addWidget(self.comp_combo)
        row1.addLayout(comp_col)

        layout.addLayout(row1)

        # Delete after upload toggle
        self.delete_checkbox = QCheckBox("Delete local .7z archives after upload completes successfully")
        self.delete_checkbox.setChecked(config.get("delete_archive_after_upload", True))
        self.delete_checkbox.setStyleSheet("color: #B3ACD9; font-size: 12px;")
        layout.addWidget(self.delete_checkbox)

        save_engine_btn = PrimaryButton("Save Archiving Settings")
        save_engine_btn.clicked.connect(self._save_engine_settings)
        layout.addWidget(save_engine_btn, alignment=Qt.AlignLeft)

        return card

    def _save_engine_settings(self):
        try:
            val = int(self.split_input.text().strip())
        except ValueError:
            val = 1800

        comp_map = {0: "store", 1: "fast", 2: "normal", 3: "max"}
        chosen_comp = comp_map.get(self.comp_combo.currentIndex(), "store")

        config = load_config()
        config["split_volume_size_mb"] = val
        config["compression_level"] = chosen_comp
        config["delete_archive_after_upload"] = self.delete_checkbox.isChecked()
        save_config(config)
        QMessageBox.information(self, "Saved", "Archiving settings updated.")

    # ---------- Poster artwork ----------

    def _build_posters_section(self) -> GlassCard:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("TMDb Movie Artwork & Metadata")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F3F1FF;")
        header.addWidget(title)
        
        tmdb_help = (
            "<b>How to get your TMDb API Key:</b><br><br>"
            "1. Go to <a href='https://www.themoviedb.org/' style='color:#33E6FF;'>themoviedb.org</a> and create a free account.<br>"
            "2. Click on your profile icon (top right) and select <b>Settings</b>.<br>"
            "3. From the left sidebar menu, click on <b>API</b>.<br>"
            "4. Click the link to <b>Create</b> or Request an API key, and choose <b>Developer</b>.<br>"
            "5. Accept the terms and fill out the basic form (you can enter 'Personal use' for the URL and description).<br>"
            "6. Once submitted, you will immediately see your <b>API Key (v3 auth)</b>.<br>"
            "7. Copy that key and paste it here!"
        )
        header.addWidget(self._create_help_btn("TMDb API Key", tmdb_help))
        header.addStretch()
        layout.addLayout(header)

        desc = QLabel(
            "Movie and series posters, plots, ratings, and director info are fetched from TMDb (themoviedb.org). "
            "Get a free API key by creating an account there, then paste it below."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #B3ACD9;")
        layout.addWidget(desc)

        row = QHBoxLayout()
        self.tmdb_key_input = QLineEdit()
        self.tmdb_key_input.setPlaceholderText("TMDb API key")
        config = load_config()
        if os.environ.get("VAULTFATHER_DEMO_SETTINGS") == "1":
            self.tmdb_key_input.setText("••••••••••••••••••••••••••••••••")
        elif config.get("tmdb_api_key"):
            self.tmdb_key_input.setText(config["tmdb_api_key"])
        row.addWidget(self.tmdb_key_input, stretch=1)

        save_btn = PrimaryButton("Save")
        save_btn.clicked.connect(self._save_tmdb_key)
        row.addWidget(save_btn)
        layout.addLayout(row)

        return card

    def _save_tmdb_key(self) -> None:
        key = self.tmdb_key_input.text().strip()
        config = load_config()
        config["tmdb_api_key"] = key or None
        save_config(config)
        QMessageBox.information(self, "Saved", "TMDb API key saved. Posters & metadata will start updating as you browse.")

    # ---------- Google Drive backup ----------

    def _build_google_drive_section(self) -> GlassCard:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("Google Drive Cloud Sync")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F3F1FF;")
        header.addWidget(title)
        
        gdrive_help = (
            "<b>How to get your Google Client ID & Secret:</b><br><br>"
            "1. Go to the <a href='https://console.cloud.google.com/' style='color:#33E6FF;'>Google Cloud Console</a> and sign in.<br>"
            "2. Create a new Project (e.g., 'VaultFather').<br>"
            "3. Go to <b>APIs & Services</b> > <b>Library</b>, search for 'Google Drive API' and click <b>Enable</b>.<br>"
            "4. Go to <b>OAuth consent screen</b>, choose 'External', and fill out the required App name and email fields. <b>Crucial:</b> Add your own email under 'Test users'.<br>"
            "5. Go to <b>Credentials</b> > <b>Create Credentials</b> > <b>OAuth client ID</b>. Choose 'Desktop app'.<br>"
            "6. You will see your <b>Client ID</b> and <b>Client Secret</b>.<br>"
            "7. Copy and paste them here to securely link your Drive."
        )
        header.addWidget(self._create_help_btn("Google Drive API Credentials", gdrive_help))
        header.addStretch()
        layout.addLayout(header)

        desc = QLabel(
            "Backs up your movie/series history (an Excel file) "
            "to a 'VaultFather Backups' folder in your Google Drive, overwriting the previous file each day."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #B3ACD9;")
        layout.addWidget(desc)

        config = load_config()

        id_row = QHBoxLayout()
        self.google_client_id_input = QLineEdit()
        self.google_client_id_input.setPlaceholderText("Google Client ID")
        if os.environ.get("VAULTFATHER_DEMO_SETTINGS") == "1":
            self.google_client_id_input.setText("109823471928-app.apps.googleusercontent.com")
        elif config.get("google_client_id"):
            self.google_client_id_input.setText(config["google_client_id"])
        id_row.addWidget(self.google_client_id_input)
        layout.addLayout(id_row)

        secret_row = QHBoxLayout()
        self.google_client_secret_input = QLineEdit()
        self.google_client_secret_input.setPlaceholderText("Google Client Secret")
        self.google_client_secret_input.setEchoMode(QLineEdit.Password)
        if os.environ.get("VAULTFATHER_DEMO_SETTINGS") == "1":
            self.google_client_secret_input.setText("••••••••••••••••••••••••")
        elif config.get("google_client_secret"):
            self.google_client_secret_input.setText(config["google_client_secret"])
        secret_row.addWidget(self.google_client_secret_input)

        save_creds_btn = PrimaryButton("Save")
        save_creds_btn.clicked.connect(self._save_google_credentials)
        secret_row.addWidget(save_creds_btn)
        layout.addLayout(secret_row)

        # Connection status
        self.google_status_label = QLabel()
        self.google_status_label.setWordWrap(True)
        layout.addWidget(self.google_status_label)

        action_row = QHBoxLayout()
        self.google_connect_btn = GhostButton("Connect Google Account")
        self.google_connect_btn.clicked.connect(self._connect_google)
        action_row.addWidget(self.google_connect_btn)

        self.google_disconnect_btn = GhostButton("Disconnect")
        self.google_disconnect_btn.clicked.connect(self._disconnect_google)
        action_row.addWidget(self.google_disconnect_btn)

        self.google_backup_now_btn = GhostButton("Backup Now")
        self.google_backup_now_btn.clicked.connect(self._backup_now)
        action_row.addWidget(self.google_backup_now_btn)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.google_daily_checkbox = QCheckBox("Automatically back up once a day")
        self.google_daily_checkbox.setChecked(config.get("google_drive_daily_backup", True))
        self.google_daily_checkbox.toggled.connect(self._toggle_daily_backup)
        layout.addWidget(self.google_daily_checkbox)

        self._login_worker = GoogleLoginWorker()
        self._login_worker.login_succeeded.connect(self._on_google_connected)
        self._login_worker.login_failed.connect(self._on_google_login_failed)

        backup_scheduler.backup_succeeded.connect(self._on_backup_succeeded)
        backup_scheduler.backup_failed.connect(self._on_backup_failed)

        self._refresh_google_status()
        return card

    def _save_google_credentials(self) -> None:
        client_id = self.google_client_id_input.text().strip()
        client_secret = self.google_client_secret_input.text().strip()
        config = load_config()
        config["google_client_id"] = client_id or None
        config["google_client_secret"] = client_secret or None
        save_config(config)
        QMessageBox.information(self, "Saved", "Google credentials saved. You can now connect your account.")
        self._refresh_google_status()

    def _connect_google(self) -> None:
        config = load_config()
        if not config.get("google_client_id") or not config.get("google_client_secret"):
            QMessageBox.warning(self, "Missing credentials", "Save your Google Client ID and Secret first.")
            return
        self.google_connect_btn.setEnabled(False)
        self.google_connect_btn.setText("Waiting for sign-in in your browser…")
        self._login_worker.connect_async()

    def _on_google_connected(self, email: str) -> None:
        self.google_connect_btn.setEnabled(True)
        self.google_connect_btn.setText("Connect Google Account")
        self._refresh_google_status()
        QMessageBox.information(self, "Connected", f"Connected as {email}.")
        backup_scheduler.maybe_run_daily_backup()

    def _on_google_login_failed(self, message: str) -> None:
        self.google_connect_btn.setEnabled(True)
        self.google_connect_btn.setText("Connect Google Account")
        QMessageBox.critical(self, "Connection failed", message)

    def _disconnect_google(self) -> None:
        google_disconnect()
        self._refresh_google_status()

    def _backup_now(self) -> None:
        self.google_backup_now_btn.setEnabled(False)
        self.google_backup_now_btn.setText("Backing up…")
        backup_scheduler.run_backup_now()

    def _on_backup_succeeded(self, backup_date: str) -> None:
        self.google_backup_now_btn.setEnabled(True)
        self.google_backup_now_btn.setText("Backup Now")
        self._refresh_google_status()

    def _on_backup_failed(self, message: str) -> None:
        self.google_backup_now_btn.setEnabled(True)
        self.google_backup_now_btn.setText("Backup Now")
        QMessageBox.critical(self, "Backup failed", message)

    def _toggle_daily_backup(self, checked: bool) -> None:
        config = load_config()
        config["google_drive_daily_backup"] = checked
        save_config(config)

    def _refresh_google_status(self) -> None:
        if os.environ.get("VAULTFATHER_DEMO_SETTINGS") == "1":
            self.google_status_label.setText("🟢 Connected as cinephile@gmail.com  ·  Last backup: Today")
            self.google_status_label.setStyleSheet("color: #35F0A6; font-size: 12px;")
            self.google_connect_btn.setVisible(False)
            self.google_disconnect_btn.setVisible(True)
            self.google_backup_now_btn.setVisible(True)
            return

        config = load_config()
        connected = has_saved_token()
        email = config.get("google_drive_connected_email")
        last_backup = config.get("last_drive_backup_date")

        if connected:
            status = f"🟢 Connected as {email}" if email else "🟢 Connected"
            if last_backup:
                status += f"  ·  Last backup: {last_backup}"
            else:
                status += "  ·  No backup yet"
            self.google_status_label.setText(status)
            self.google_status_label.setStyleSheet("color: #35F0A6; font-size: 12px;")
        else:
            self.google_status_label.setText("⚪ Not connected")
            self.google_status_label.setStyleSheet("color: #6E6795; font-size: 12px;")

        self.google_connect_btn.setVisible(not connected)
        self.google_disconnect_btn.setVisible(connected)
        self.google_backup_now_btn.setVisible(connected)

    # ---------- Telegram Account ----------

    def _build_telegram_account_section(self) -> GlassCard:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Telegram Account Connection")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F3F1FF;")
        header.addWidget(title)
        
        tg_help = (
            "<b>How to get your Telegram API credentials:</b><br><br>"
            "1. Go to <a href='https://my.telegram.org/' style='color:#33E6FF;'>my.telegram.org</a> and log in with your phone number.<br>"
            "2. Click on <b>API development tools</b>.<br>"
            "3. If it's your first time, register a new application. Fill in an App title and Short name (e.g., 'VaultFatherBackup'). The rest can be left blank.<br>"
            "4. Click <b>Create application</b>.<br>"
            "5. You will now see your <b>api_id</b> (a number) and <b>api_hash</b> (a long string of characters).<br>"
            "6. Click 'Connect Telegram' here and paste them in when prompted!"
        )
        header.addWidget(self._create_help_btn("Telegram api_id & api_hash", tg_help))
        header.addStretch()

        self.tg_connect_btn = PrimaryButton("Connect Telegram")
        self.tg_connect_btn.clicked.connect(self._open_telegram_login)
        header.addWidget(self.tg_connect_btn)

        self.tg_disconnect_btn = GhostButton("Disconnect")
        self.tg_disconnect_btn.clicked.connect(self._disconnect_telegram)
        header.addWidget(self.tg_disconnect_btn)

        layout.addLayout(header)

        desc = QLabel(
            "Connect your primary Telegram account to VaultFather. This safely stores your session "
            "credentials locally so you can upload movies and pull your unwatched wishlist."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11.5px; color: #B3ACD9;")
        layout.addWidget(desc)

        self.tg_status_label = QLabel("Loading...")
        self.tg_status_label.setStyleSheet("font-size: 12.5px; font-weight: 600;")
        layout.addWidget(self.tg_status_label)

        self._refresh_telegram_status()
        return card

    def _refresh_telegram_status(self) -> None:
        session_file = CONFIG_DIR / "telegram.session"
        if session_file.exists():
            self.tg_status_label.setText("✅ Connected (Session active)")
            self.tg_status_label.setStyleSheet("font-size: 12.5px; font-weight: 600; color: #35F0A6;")
            self.tg_connect_btn.hide()
            self.tg_disconnect_btn.show()
        else:
            self.tg_status_label.setText("⚪ Not connected")
            self.tg_status_label.setStyleSheet("font-size: 12.5px; font-weight: 600; color: #6E6795;")
            self.tg_connect_btn.show()
            self.tg_disconnect_btn.hide()

    def _open_telegram_login(self) -> None:
        dlg = TelegramAccountDialog(self)
        dlg.exec()
        self._refresh_telegram_status()

    def _disconnect_telegram(self) -> None:
        reply = QMessageBox.question(
            self, "Disconnect Telegram",
            "This will delete your local Telegram session. You will need to log in again to use the app.\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            session_file = CONFIG_DIR / "telegram.session"
            if session_file.exists():
                try:
                    os.remove(session_file)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not delete session: {e}")
            self._refresh_telegram_status()

    # ---------- Telegram Unwatched Wishlist Channel ----------

    def _build_unwatched_channel_section(self) -> GlassCard:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Telegram Unwatched Wishlist Channel")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F3F1FF;")
        header.addWidget(title)
        
        unwatched_help = (
            "<b>How to set up your Unwatched Wishlist:</b><br><br>"
            "1. Open your Telegram app on your phone or desktop.<br>"
            "2. Create a new <b>Private Channel</b> (e.g., 'VaultFather Unwatched').<br>"
            "3. Click the <b>+ Connect Wishlist Channel</b> button here in settings.<br>"
            "4. Select the channel you just created from the popup list.<br>"
            "5. Now, whenever you see a movie you want to watch, just forward its name or type it into that Telegram channel. It will automatically sync to your Dashboard with full posters and details!"
        )
        header.addWidget(self._create_help_btn("Unwatched Wishlist", unwatched_help))
        header.addStretch()

        self.unwatched_connect_btn = PrimaryButton("+ Connect Wishlist Channel")
        self.unwatched_connect_btn.clicked.connect(self._open_connect_unwatched_channel)
        header.addWidget(self.unwatched_connect_btn)

        self.unwatched_disconnect_btn = GhostButton("Disconnect")
        self.unwatched_disconnect_btn.clicked.connect(self._disconnect_unwatched_channel)
        header.addWidget(self.unwatched_disconnect_btn)

        layout.addLayout(header)

        desc = QLabel(
            "Connect a dedicated Telegram channel for your unwatched movies wishlist. "
            "Titles posted in this channel populate the Unwatched Movies Vault on your "
            "Command Dashboard with TMDb posters."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 11.5px; color: #B3ACD9;")
        layout.addWidget(desc)

        self.unwatched_status_label = QLabel("Not connected")
        self.unwatched_status_label.setStyleSheet(
            "font-size: 12.5px; font-weight: 600; color: #33E6FF;"
        )
        layout.addWidget(self.unwatched_status_label)

        self._refresh_unwatched_channel_status()
        return card

    def _refresh_unwatched_channel_status(self) -> None:
        if os.environ.get("VAULTFATHER_DEMO_SETTINGS") == "1":
            self.unwatched_status_label.setText(
                "✅ Connected:  VaultFather Wishlist  (ID: -100192837465)"
            )
            self.unwatched_connect_btn.setText("Change Channel")
            self.unwatched_disconnect_btn.show()
            return

        config = load_config()
        ch_title = config.get("unwatched_channel_title")
        cid = config.get("unwatched_channel_id")
        if ch_title and cid:
            self.unwatched_status_label.setText(
                f"✅ Connected:  {ch_title}  (ID: {cid})"
            )
            self.unwatched_connect_btn.setText("Change Channel")
            self.unwatched_disconnect_btn.show()
        else:
            self.unwatched_status_label.setText(
                "⚪ Not connected — add a dedicated Telegram wishlist channel."
            )
            self.unwatched_connect_btn.setText("+ Connect Wishlist Channel")
            self.unwatched_disconnect_btn.hide()

    def _open_connect_unwatched_channel(self) -> None:
        dlg = TelegramDestinationDialog(parent=self, is_unwatched_mode=True)
        if dlg.exec():
            ch = dlg.selected_unwatched_channel()
            if ch:
                channel_id, ch_title = ch
                config = load_config()
                config["unwatched_channel_id"] = channel_id
                config["unwatched_channel_title"] = ch_title
                save_config(config)
                self._refresh_unwatched_channel_status()
                QMessageBox.information(
                    self, "Connected",
                    f"'{ch_title}' is now your Unwatched Wishlist Channel."
                )

    def _disconnect_unwatched_channel(self) -> None:
        config = load_config()
        config["unwatched_channel_id"] = None
        config["unwatched_channel_title"] = None
        save_config(config)
        self._refresh_unwatched_channel_status()
        QMessageBox.information(
            self, "Disconnected", "Unwatched wishlist channel disconnected."
        )

    # ---------- Backup destinations ----------

    def _build_destinations_section(self) -> GlassCard:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Telegram Backup Destinations")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F3F1FF;")
        header.addWidget(title)
        
        backup_help = (
            "<b>How to add Backup Destinations:</b><br><br>"
            "1. Open your Telegram app on your phone or desktop.<br>"
            "2. Create a new <b>Private Channel</b> (e.g., 'My Movie Vault 1').<br>"
            "3. Click <b>+ Add Backup Destination</b> here in settings.<br>"
            "4. Select the channel you just created from the popup list.<br>"
            "5. That's it! When you upload a movie, VaultFather will split and encrypt the files, then safely store them in this channel with unlimited storage."
        )
        header.addWidget(self._create_help_btn("Backup Destinations", backup_help))
        header.addStretch()

        add_btn = PrimaryButton("+ Add Backup Destination")
        add_btn.clicked.connect(self._open_add_destination)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self.destinations_list_layout = QVBoxLayout()
        self.destinations_list_layout.setSpacing(12)
        layout.addLayout(self.destinations_list_layout)

        self._refresh_destinations()
        return card

    def _refresh_destinations(self) -> None:
        while self.destinations_list_layout.count():
            item = self.destinations_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        destinations = list_destinations()

        if not destinations:
            empty = QLabel(
                "No backup destinations yet. Add a Telegram channel to start "
                "sending movies somewhere real."
            )
            empty.setProperty("role", "subtitle")
            empty.setWordWrap(True)
            self.destinations_list_layout.addWidget(empty)
            return

        for dest in destinations:
            self.destinations_list_layout.addWidget(self._make_destination_row(dest))

    def _make_destination_row(self, dest) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 4, 4, 4)

        icon = QLabel("📡" if dest.type == "telegram" else "☁")
        icon.setFixedSize(36, 36)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("background-color: rgba(51,230,255,18); border-radius: 10px; font-size: 15px;")
        layout.addWidget(icon)

        info_col = QVBoxLayout()
        info_col.setSpacing(1)
        d_name = dest.name
        if os.environ.get("VAULTFATHER_DEMO_SETTINGS") == "1":
            if any(k in d_name.lower() for k in ("ikkili", "personal")):
                d_name = "VaultFather Cloud Vault [Primary]"
        name = QLabel(d_name)
        name.setStyleSheet("font-weight: 600; font-size: 13.5px;")
        kind = QLabel(f"Telegram channel · added {dest.created_at[:10]}")
        kind.setStyleSheet("color: #6E6795; font-size: 11px;")
        info_col.addWidget(name)
        info_col.addWidget(kind)
        layout.addLayout(info_col, stretch=1)

        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("GhostButton")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.clicked.connect(lambda: self._remove_destination(dest.id))
        layout.addWidget(remove_btn)

        return row

    def _remove_destination(self, destination_id: int) -> None:
        remove_destination(destination_id)
        self._refresh_destinations()

    def _open_add_destination(self) -> None:
        dialog = TelegramDestinationDialog(self)
        if dialog.exec():
            self._refresh_destinations()

    # ---------- Movie Download Destination ----------

    def _build_movie_download_destination_section(self) -> GlassCard:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Cloud Download Destination")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #33E6FF;")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        desc = QLabel(
            "Choose the local folder where movies downloaded from your Cloud Vault will be saved. "
            "If no folder is selected, you will be asked each time you start a download."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #B3ACD9;")
        layout.addWidget(desc)

        row = QHBoxLayout()
        row.setSpacing(10)

        config = load_config()
        saved_dir = config.get("telegram_movie_download_dir") or ""

        self._dl_dir_label = QLabel(saved_dir if saved_dir else "No folder selected")
        self._dl_dir_label.setStyleSheet(
            "font-size: 12px; color: #E8F4FF; background: rgba(0,240,255,7); "
            "border: 1px solid rgba(0,240,255,30); border-radius: 8px; padding: 6px 10px;"
        )
        self._dl_dir_label.setWordWrap(True)
        row.addWidget(self._dl_dir_label, stretch=1)

        browse_btn = GhostButton("Browse…")
        browse_btn.clicked.connect(self._pick_download_dir)
        row.addWidget(browse_btn)

        clear_btn = GhostButton("Clear")
        clear_btn.clicked.connect(self._clear_download_dir)
        row.addWidget(clear_btn)

        layout.addLayout(row)
        return card

    def _pick_download_dir(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        folder = QFileDialog.getExistingDirectory(self, "Select Movie Download Folder")
        if folder:
            config = load_config()
            config["telegram_movie_download_dir"] = folder
            save_config(config)
            self._dl_dir_label.setText(folder)

    def _clear_download_dir(self) -> None:
        config = load_config()
        config["telegram_movie_download_dir"] = None
        save_config(config)
        self._dl_dir_label.setText("No folder selected")

    # ---------- Danger zone ----------

    def _build_danger_zone(self) -> GlassCard:
        card = GlassCard()
        card.setStyleSheet(
            "QFrame#GlassCard { border: 1px solid rgba(255,92,122,60); }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(10)

        title = QLabel("Danger Zone")
        title.setStyleSheet("font-size: 14px; font-weight: 700; color: #FF5C7A;")
        layout.addWidget(title)

        desc = QLabel(
            "Permanently deletes every backup record — movies, series episodes, "
            "and series-name announcement memory. Your Telegram channels and "
            "uploaded files are NOT touched, only VaultFather's local record of them."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 12px; color: #B3ACD9;")
        layout.addWidget(desc)

        row = QHBoxLayout()
        row.addStretch()
        clear_btn = QPushButton("Clear Database")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setStyleSheet(
            "background-color: rgba(255,92,122,25); color: #FF5C7A; border: 1px solid #FF5C7A;"
            "border-radius: 12px; padding: 10px 18px; font-weight: 600; font-size: 13px;"
        )
        clear_btn.clicked.connect(self._confirm_clear)
        row.addWidget(clear_btn)
        layout.addLayout(row)

        return card

    def _confirm_clear(self) -> None:
        movie_count = len(list_movie_backups())
        series_count = len(list_series_backups())

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Clear Backup History?")
        box.setText(
            f"This will permanently delete {movie_count} movie record{'s' if movie_count != 1 else ''} "
            f"and {series_count} series episode record{'s' if series_count != 1 else ''} from VaultFather's database.\n\n"
            f"Your actual files on Telegram are not affected. This cannot be undone."
        )
        box.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        box.setDefaultButton(QMessageBox.Cancel)
        box.button(QMessageBox.Yes).setText("Clear Database")

        if box.exec() == QMessageBox.Yes:
            clear_all_backup_history()
            if self.on_database_cleared:
                self.on_database_cleared()
            QMessageBox.information(self, "Done", "Backup history cleared.")