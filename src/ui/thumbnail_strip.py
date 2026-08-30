from pathlib import Path
from typing import List, Optional, Dict
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QListWidget, QListWidgetItem
from PyQt6.QtCore import pyqtSignal, Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap
from src.services.thumbnail_cache import ThumbnailCache

class ThumbnailStripWidget(QWidget):
    image_selected = pyqtSignal(object)

    def __init__(self, thumbnail_cache: ThumbnailCache, parent=None):
        super().__init__(parent)
        self.thumbnail_cache = thumbnail_cache
        self.image_paths: List[Path] = []
        self._current_token: int = 0
        self._item_map: Dict[str, QListWidgetItem] = {}
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_widget.setFlow(QListWidget.Flow.LeftToRight)
        self.list_widget.setWrapping(False)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setIconSize(QSize(80, 80))
        self.list_widget.setMovement(QListWidget.Movement.Static)
        self.list_widget.setFixedHeight(120)
        self.list_widget.setSpacing(6)
        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self.list_widget)

    def set_images(self, paths: List[Path], select_index: int = 0):
        self._current_token += 1
        current_token = self._current_token
        self.image_paths = list(paths)
        self.list_widget.clear()
        self._item_map.clear()

        for p in paths:
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self.list_widget.addItem(item)
            self._item_map[str(p)] = item
            self.thumbnail_cache.load_async(p, (80, 80), self._make_callback(item, current_token))

        if paths:
            target = max(0, min(select_index, len(paths) - 1))
            self.list_widget.setCurrentRow(target)
        else:
            self.image_selected.emit(None)

    def _make_callback(self, item: QListWidgetItem, token: int):
        def on_loaded(path_str: str, pixmap: QPixmap):
            if token != self._current_token:
                return
            try:
                item.setIcon(QIcon(pixmap))
            except RuntimeError:
                pass
        return on_loaded

    def _on_selection_changed(self, row: int):
        if 0 <= row < len(self.image_paths):
            item = self.list_widget.item(row)
            if item:
                self.list_widget.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)
            self.image_selected.emit(self.image_paths[row])
        elif len(self.image_paths) == 0:
            self.image_selected.emit(None)

    def get_current_index(self) -> int:
        return self.list_widget.currentRow()

    def is_at_first(self) -> bool:
        return len(self.image_paths) == 0 or self.list_widget.currentRow() <= 0

    def is_at_last(self) -> bool:
        return len(self.image_paths) == 0 or self.list_widget.currentRow() >= len(self.image_paths) - 1

    def select_first(self):
        if self.image_paths:
            self.list_widget.setCurrentRow(0)

    def select_last(self):
        if self.image_paths:
            self.list_widget.setCurrentRow(len(self.image_paths) - 1)

    def select_next(self) -> bool:
        row = self.list_widget.currentRow()
        if row < len(self.image_paths) - 1:
            self.list_widget.setCurrentRow(row + 1)
            return True
        return False

    def select_previous(self) -> bool:
        row = self.list_widget.currentRow()
        if row > 0:
            self.list_widget.setCurrentRow(row - 1)
            return True
        return False


