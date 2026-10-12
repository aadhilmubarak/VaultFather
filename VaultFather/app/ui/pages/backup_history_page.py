import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QStackedWidget, QPushButton, QFileDialog, QMessageBox, QMenu, QComboBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from app.ui.widgets.glass_card import GlassCard
from app.ui.widgets.buttons import PrimaryButton, GhostButton
from app.core.database import (
    list_movie_backups, list_series_backups, get_destination_by_name,
    delete_movie_backup, delete_series_backup,
)
from app.core.movie_scanner import human_size
from app.core.excel_export import export_backup_history
from app.core.telegram_links import open_telegram_message


def _resolve_channel_and_message(destination: str | None, message_ids: list[str]) -> tuple:
    """Returns (channel_id, message_id) or (None, None) if there's nothing to link to."""
    if not destination or not message_ids:
        return None, None
    dest = get_destination_by_name(destination)
    if not dest or not dest.telegram_channel_id:
        return None, None
    return dest.telegram_channel_id, message_ids[0]


class BackupHistoryPage(QWidget):
    """
    Log of successful backups — Movies and Series, each in their own view,
    sourced directly from the database. Direct one-click navigation to Telegram.
    Includes full Sort By controls (Name, Size, Date).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sort_key: str = "date"   # "date", "name", "size"
        self._sort_asc: bool = False   # False = Descending (Newest / Z-A / Largest first)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 0, 4, 0)
        root.setSpacing(12)

        # Header Row
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        h1 = QLabel("Backup History")
        h1.setProperty("role", "h1")
        h1.setFixedHeight(28)
        title_col.addWidget(h1)
        header.addLayout(title_col)
        header.addStretch()

        export_btn = PrimaryButton("Export to Excel")
        export_btn.clicked.connect(self._export)
        header.addWidget(export_btn)
        root.addLayout(header)

        # Control Dock: View Toggle (Movies / Series) + Sort Controls
        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 4, 0, 0)
        toggle_row.setSpacing(10)

        self.movies_toggle_btn = QPushButton("Movies")
        self.series_toggle_btn = QPushButton("Series")

        _toggle_style = """
            QPushButton {
                background-color: rgba(14, 11, 32, 220);
                color: #8BA8C8;
                border: 1px solid rgba(0, 240, 255, 30);
                border-radius: 10px;
                padding: 6px 18px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: rgba(0, 240, 255, 45);
                color: #FFFFFF;
                border: 1px solid rgba(0, 240, 255, 75);
            }
            QPushButton:checked {
                color: #00F0FF;
                background-color: rgba(0, 240, 255, 55);
                border: 1px solid rgba(0, 240, 255, 120);
                font-weight: 700;
            }
        """
        for btn in (self.movies_toggle_btn, self.series_toggle_btn):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_toggle_style)
        self.movies_toggle_btn.clicked.connect(lambda: self._switch_view(0))
        self.series_toggle_btn.clicked.connect(lambda: self._switch_view(1))
        toggle_row.addWidget(self.movies_toggle_btn)
        toggle_row.addWidget(self.series_toggle_btn)

        toggle_row.addStretch()

        # Sort Controls
        sort_lbl = QLabel("Sort by:")
        sort_lbl.setStyleSheet("color: #8BA8C8; font-size: 12px; font-weight: 600;")
        toggle_row.addWidget(sort_lbl)

        self.sort_combo = QComboBox()
        self.sort_combo.addItem("Date Added", "date")
        self.sort_combo.addItem("Name", "name")
        self.sort_combo.addItem("File Size", "size")
        self.sort_combo.setStyleSheet(
            "QComboBox { background: rgba(0,240,255,10); color: #00F0FF; "
            "border: 1px solid rgba(0,240,255,35); border-radius: 8px; "
            "padding: 5px 12px; font-size: 12px; font-weight: 600; } "
            "QComboBox:hover { background: rgba(0,240,255,25); color: #FFF; }"
        )
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        toggle_row.addWidget(self.sort_combo)

        self.sort_order_btn = QPushButton("▼ Desc")
        self.sort_order_btn.setCursor(Qt.PointingHandCursor)
        self.sort_order_btn.setToolTip("Toggle Ascending / Descending order")
        self.sort_order_btn.setStyleSheet(
            "QPushButton { background: rgba(0,240,255,10); color: #8BA8C8; "
            "border: 1px solid rgba(0,240,255,30); border-radius: 8px; "
            "padding: 5px 12px; font-size: 12px; font-weight: 600; } "
            "QPushButton:hover { background: rgba(0,240,255,25); color: #00F0FF; }"
        )
        self.sort_order_btn.clicked.connect(self._toggle_sort_order)
        toggle_row.addWidget(self.sort_order_btn)

        root.addLayout(toggle_row)

        self.view_stack = QStackedWidget()
        root.addWidget(self.view_stack, stretch=1)
        self.view_stack.addWidget(self._build_movies_view())
        self.view_stack.addWidget(self._build_series_view())
        self._switch_view(0)

        self.refresh()

    def _on_sort_changed(self):
        self._sort_key = self.sort_combo.currentData()
        self.refresh()

    def _toggle_sort_order(self):
        self._sort_asc = not self._sort_asc
        self.sort_order_btn.setText("▲ Asc" if self._sort_asc else "▼ Desc")
        self.refresh()

    # ---------- Views ----------

    def _build_movies_view(self) -> QWidget:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 14)
        layout.setSpacing(12)

        self.movies_count_label = QLabel("")
        self.movies_count_label.setStyleSheet("color: #B3ACD9; font-size: 12.5px;")
        layout.addWidget(self.movies_count_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self.movies_rows_container = QWidget()
        self.movies_rows_layout = QVBoxLayout(self.movies_rows_container)
        self.movies_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.movies_rows_layout.setSpacing(8)
        self.movies_rows_layout.addStretch()
        scroll.setWidget(self.movies_rows_container)
        layout.addWidget(scroll, stretch=1)
        return card

    def _build_series_view(self) -> QWidget:
        card = GlassCard()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 14)
        layout.setSpacing(12)

        self.series_count_label = QLabel("")
        self.series_count_label.setStyleSheet("color: #B3ACD9; font-size: 12.5px;")
        layout.addWidget(self.series_count_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self.series_rows_container = QWidget()
        self.series_rows_layout = QVBoxLayout(self.series_rows_container)
        self.series_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.series_rows_layout.setSpacing(16)
        self.series_rows_layout.addStretch()
        scroll.setWidget(self.series_rows_container)
        layout.addWidget(scroll, stretch=1)
        return card

    def _switch_view(self, index: int) -> None:
        self.view_stack.setCurrentIndex(index)
        for btn, active in ((self.movies_toggle_btn, index == 0), (self.series_toggle_btn, index == 1)):
            btn.setChecked(active)
            btn.setProperty("active", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ---------- Data ----------

    def refresh(self) -> None:
        self._refresh_movies()
        self._refresh_series()

    def _refresh_movies(self) -> None:
        while self.movies_rows_layout.count() > 1:
            item = self.movies_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_records = list_movie_backups()
        exclude_env = os.environ.get("VAULTFATHER_EXCLUDE_TITLES", "")
        excluded_keywords = {"ken park", "aroopi"}
        if exclude_env:
            excluded_keywords |= {k.strip().lower() for k in exclude_env.split(",") if k.strip()}

        records = [
            m for m in all_records
            if m.status == "backed_up" and not any(
                ex in (m.movie_name or "").lower() or ex in (m.movie_path or "").lower()
                for ex in excluded_keywords
            )
        ]

        # Apply sorting
        if self._sort_key == "name":
            records.sort(key=lambda m: m.movie_name.lower(), reverse=not self._sort_asc)
        elif self._sort_key == "size":
            records.sort(key=lambda m: m.total_archive_size_bytes, reverse=not self._sort_asc)
        else:  # "date"
            records.sort(key=lambda m: m.created_at, reverse=not self._sort_asc)

        self.movies_count_label.setText(f"{len(records)} successful backup{'s' if len(records) != 1 else ''}")

        if not records:
            empty = QLabel("No successful movie backups found.")
            empty.setProperty("role", "subtitle")
            self.movies_rows_layout.insertWidget(0, empty)
            return

        for m in records:
            channel_id, message_id = _resolve_channel_and_message(m.destination, m.telegram_message_ids)
            row = self._make_row(
                title=m.movie_name,
                meta=f"{human_size(m.total_archive_size_bytes)} · {m.destination or '—'} · {m.created_at[:10]}",
                status=m.status,
                channel_id=channel_id, message_id=message_id,
                record_id=m.id, record_type="movie",
            )
            self.movies_rows_layout.insertWidget(self.movies_rows_layout.count() - 1, row)

    def _refresh_series(self) -> None:
        while self.series_rows_layout.count() > 1:
            item = self.series_rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        all_records = list_series_backups()
        exclude_env = os.environ.get("VAULTFATHER_EXCLUDE_TITLES", "")
        excluded_keywords = {"ken park", "aroopi"}
        if exclude_env:
            excluded_keywords |= {k.strip().lower() for k in exclude_env.split(",") if k.strip()}

        records = [
            e for e in all_records
            if e.status == "backed_up" and not any(
                ex in (e.series_name or "").lower()
                for ex in excluded_keywords
            )
        ]

        total = len(records)
        self.series_count_label.setText(f"{total} successful episode backup{'s' if total != 1 else ''}")

        if not records:
            empty = QLabel("No successful series backups found.")
            empty.setProperty("role", "subtitle")
            self.series_rows_layout.insertWidget(0, empty)
            return

        grouped: dict[str, dict[int, list]] = {}
        for e in records:
            grouped.setdefault(e.series_name, {}).setdefault(e.season_number, []).append(e)

        series_names = list(grouped.keys())
        if self._sort_key == "name":
            series_names.sort(key=str.casefold, reverse=not self._sort_asc)

        for series_name in series_names:
            group = QWidget()
            group_layout = QVBoxLayout(group)
            group_layout.setContentsMargins(0, 0, 0, 0)
            group_layout.setSpacing(8)

            title = QLabel(series_name)
            title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F3F1FF;")
            group_layout.addWidget(title)

            for season_number in sorted(grouped[series_name].keys()):
                season_label = QLabel(f"S{season_number:02d}")
                season_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #B3ACD9; padding-left: 4px;")
                group_layout.addWidget(season_label)

                episodes = grouped[series_name][season_number]
                if self._sort_key == "size":
                    episodes.sort(key=lambda x: x.total_archive_size_bytes, reverse=not self._sort_asc)
                elif self._sort_key == "date":
                    episodes.sort(key=lambda x: x.created_at, reverse=not self._sort_asc)
                else:
                    episodes.sort(key=lambda x: x.episode_number, reverse=not self._sort_asc)

                for e in episodes:
                    channel_id, message_id = _resolve_channel_and_message(e.destination, e.telegram_message_ids)
                    row = self._make_row(
                        title=f"E{e.episode_number:02d}",
                        meta=f"{e.episode_name} · {human_size(e.total_archive_size_bytes)} · {e.destination or '—'} · {e.created_at[:10]}",
                        status=e.status,
                        channel_id=channel_id, message_id=message_id,
                        record_id=e.id, record_type="series",
                    )
                    group_layout.addWidget(row)

            self.series_rows_layout.insertWidget(self.series_rows_layout.count() - 1, group)

    def _make_row(self, title: str, meta: str, status: str, channel_id, message_id,
                  record_id: int = None, record_type: str = "movie") -> QWidget:
        row = QWidget()
        row.setObjectName("QueueRow")
        row.setStyleSheet(
            "QWidget#QueueRow { background: rgba(14, 11, 32, 180); border: 1px solid rgba(0, 240, 255, 20); border-radius: 10px; }"
            "QWidget#QueueRow:hover { background: rgba(20, 16, 46, 220); border-color: rgba(0, 240, 255, 60); }"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        has_link = channel_id is not None and message_id is not None
        if has_link:
            row.setCursor(Qt.PointingHandCursor)
            row.setToolTip("Click to open message in Telegram")

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        title_label = QLabel()
        title_label.setTextFormat(Qt.RichText)
        if has_link:
            title_label.setText(f'<a href="#" style="color:#33E6FF; text-decoration:none;">{title}</a>')
        else:
            title_label.setText(title)
        title_label.setStyleSheet("font-size: 13px; font-weight: 700; color: #E8F4FF;")

        meta_label = QLabel(meta)
        meta_label.setStyleSheet("font-size: 11px; color: #8BA8C8;")
        text_col.addWidget(title_label)
        text_col.addWidget(meta_label)
        layout.addLayout(text_col, stretch=1)

        # Entire row click handler for Telegram navigation
        if has_link:
            def _on_row_click(event, cid=channel_id, mid=message_id):
                open_telegram_message(cid, mid)
            title_label.linkActivated.connect(
                lambda _href, cid=channel_id, mid=message_id: open_telegram_message(cid, mid)
            )

        # ⋯ action menu button
        if record_id is not None:
            menu_btn = QPushButton("⋯")
            menu_btn.setFixedSize(28, 28)
            menu_btn.setCursor(Qt.PointingHandCursor)
            menu_btn.setStyleSheet(
                "QPushButton { background: rgba(0,240,255,10); color: #8BA8C8;"
                "  border: 1px solid rgba(0,240,255,25); border-radius: 6px;"
                "  font-size: 14px; font-weight: 700; }"
                "QPushButton:hover { background: rgba(0,240,255,22); color: #E8F4FF;"
                "  border: 1px solid rgba(0,240,255,55); }"
            )
            menu_btn.clicked.connect(
                lambda _, rid=record_id, rt=record_type, t=title:
                    self._show_row_menu(menu_btn, rid, rt, t)
            )
            layout.addWidget(menu_btn)

        return row

    def _show_row_menu(self, btn: QPushButton, record_id: int, record_type: str, title: str) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #0E0C1E; border: 1px solid rgba(0,240,255,40);"
            "  border-radius: 8px; padding: 4px; color: #E8F4FF; font-size: 12px; }"
            "QMenu::item { padding: 7px 18px; border-radius: 5px; }"
            "QMenu::item:selected { background: rgba(255,51,102,25); color: #FF5C7A; }"
        )
        remove_action = QAction("🗑  Remove this backup", self)
        menu.addAction(remove_action)

        action = menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
        if action != remove_action:
            return

        reply = QMessageBox.question(
            self, "Remove Backup Record",
            f"Remove the backup record for:\n\n  {title}\n\n"
            "This only removes the history entry from VaultFather.\n"
            "Files already uploaded to Telegram are not affected.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if record_type == "movie":
            delete_movie_backup(record_id)
        else:
            delete_series_backup(record_id)
        self.refresh()

    # ---------- Export ----------

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Backup History", "VaultFather Backup History.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return
        try:
            export_backup_history(path)
            QMessageBox.information(self, "Export complete", f"Saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
