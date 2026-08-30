from pathlib import Path
from typing import List, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QListWidget, QListWidgetItem,
    QLineEdit
)
from PyQt6.QtCore import pyqtSignal, Qt
from src.models.folder_item import FolderItem

class FolderListWidget(QWidget):
    folder_selected = pyqtSignal(object)
    rename_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[FolderItem] = []
        self._filtered_items: List[FolderItem] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter folders...")
        self.filter_input.textChanged.connect(self._on_filter_changed)
        layout.addWidget(self.filter_input)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, FolderItem):
            self.rename_requested.emit(data)


    def _on_filter_changed(self, text: str):
        self._apply_filter(text)

    def set_folders(self, folders: List[FolderItem]):
        self._items = list(folders)
        self._apply_filter(self.filter_input.text())

    def _apply_filter(self, text: str, target_row: Optional[int] = None):
        query = text.strip().lower()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        if not query:
            self._filtered_items = list(self._items)
        else:
            self._filtered_items = [f for f in self._items if query in f.name.lower()]

        for item in self._filtered_items:
            list_item = QListWidgetItem(f"{item.name} ({item.image_count})")
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.list_widget.addItem(list_item)

        self.list_widget.blockSignals(False)

        if self._filtered_items:
            if target_row is None:
                new_row = 0
            else:
                new_row = max(0, min(target_row, len(self._filtered_items) - 1))
            self.list_widget.setCurrentRow(new_row)
            self.folder_selected.emit(self._filtered_items[new_row])
        else:
            self.folder_selected.emit(None)

    def _on_row_changed(self, row: int):
        if 0 <= row < len(self._filtered_items):
            self.folder_selected.emit(self._filtered_items[row])
        elif len(self._filtered_items) == 0:
            self.folder_selected.emit(None)

    def get_current_folder(self) -> Optional[FolderItem]:
        item = self.list_widget.currentItem()
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, FolderItem):
                return data
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._filtered_items):
            return self._filtered_items[row]
        return None

    def get_selected_folders(self) -> List[FolderItem]:
        selected_items = self.list_widget.selectedItems()
        folders: List[FolderItem] = []
        for item in selected_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, FolderItem):
                folders.append(data)
        if not folders:
            current = self.get_current_folder()
            if current:
                folders.append(current)
        return folders

    def has_previous_folder(self) -> bool:
        return self.list_widget.currentRow() > 0

    def has_next_folder(self) -> bool:
        return 0 <= self.list_widget.currentRow() < len(self._filtered_items) - 1

    def select_previous_folder(self) -> bool:
        row = self.list_widget.currentRow()
        if row > 0:
            self.list_widget.setCurrentRow(row - 1)
            return True
        return False

    def select_next_folder(self) -> bool:
        row = self.list_widget.currentRow()
        if 0 <= row < len(self._filtered_items) - 1:
            self.list_widget.setCurrentRow(row + 1)
            return True
        return False

    def rename_folder_item(self, old_path: Path, new_path: Path, new_name: str):
        for item in self._items:
            if item.path == old_path:
                item.path = new_path
                item.name = new_name
                item.image_paths = [new_path / img.name for img in item.image_paths]
                break

        current_row = self.list_widget.currentRow()
        self._apply_filter(self.filter_input.text(), target_row=current_row)

    def remove_folder_items(self, folder_paths: List[Path]):
        path_set = set(folder_paths)
        deleted_indices = [
            i for i, f in enumerate(self._filtered_items)
            if f.path in path_set
        ]
        first_deleted_index = min(deleted_indices) if deleted_indices else max(0, self.list_widget.currentRow())

        self._items = [f for f in self._items if f.path not in path_set]
        self._apply_filter(self.filter_input.text(), target_row=first_deleted_index)

    def remove_folder_item(self, folder_path: Path):
        self.remove_folder_items([folder_path])


