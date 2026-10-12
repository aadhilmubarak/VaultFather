from PySide6.QtWidgets import QComboBox, QStyle, QStylePainter, QStyleOptionComboBox
from PySide6.QtGui import QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, Signal


class CheckableComboBox(QComboBox):
    """
    A dropdown where items have checkboxes instead of single-click
    selection, so more than one can be chosen at once — used for
    picking multiple Telegram channels to upload the same movie to.

    Deliberately kept NON-editable. An earlier version made it editable
    so a custom line edit could show "2 channels selected," but that
    meant fighting Qt's editable-combobox click/focus handling by hand
    (via an event filter + deferred showPopup), which turned out to
    still race open-then-immediately-close in real use even after a
    first fix. A plain, non-editable QComboBox has rock-solid native
    open/close behavior for free — so instead, this only overrides
    paintEvent to draw a custom summary string in place of the normal
    current-item text. No event filters, no timing games.
    """

    selection_changed = Signal()

    def __init__(self, items: list[str], parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self._populate_model(items)
        self.setModel(self._model)
        self.view().pressed.connect(self._on_item_pressed)

    def _populate_model(self, items: list[str]) -> None:
        self._model.clear()
        for text in items:
            item = QStandardItem(text)
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setData(Qt.Unchecked, Qt.CheckStateRole)
            self._model.appendRow(item)

    def _on_item_pressed(self, index) -> None:
        item = self._model.itemFromIndex(index)
        item.setCheckState(Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked)
        self.update()  # repaint the summary text
        self.selection_changed.emit()

    def _display_text(self) -> str:
        selected = self.checked_items()
        if not selected:
            return "Select destination…"
        if len(selected) == 1:
            return selected[0]
        return f"{len(selected)} channels selected"

    def paintEvent(self, event) -> None:
        painter = QStylePainter(self)
        painter.setPen(self.palette().text().color())
        opt = QStyleOptionComboBox()
        self.initStyleOption(opt)
        opt.currentText = self._display_text()
        painter.drawComplexControl(QStyle.CC_ComboBox, opt)
        painter.drawControl(QStyle.CE_ComboBoxLabel, opt)

    def checked_items(self) -> list[str]:
        result = []
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item.checkState() == Qt.Checked:
                result.append(item.text())
        return result

    def set_checked_items(self, names: list[str]) -> None:
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            item.setCheckState(Qt.Checked if item.text() in names else Qt.Unchecked)
        self.update()

    def check_all(self) -> None:
        for row in range(self._model.rowCount()):
            self._model.item(row).setCheckState(Qt.Checked)
        self.update()

    def set_items(self, items: list[str]) -> None:
        self._populate_model(items)
        self.update()

    # Keeps the dropdown open after clicking an item, so multiple can
    # be checked in one go without reopening the popup each time.
    def hidePopup(self) -> None:
        if self.view().underMouse():
            return
        super().hidePopup()
