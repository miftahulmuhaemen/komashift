from pathlib import Path
from typing import Optional, Union
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QScrollArea
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap

ZOOM_PRESETS = [0.50, 0.75, 1.00, 1.20]

class PreviewPaneWidget(QWidget):
    zoom_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_pixmap: Optional[QPixmap] = None
        self._zoom_mode: Union[str, float] = "fit"
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setStyleSheet("background-color: #1e1e1e; border: none;")

        self.image_label = QLabel("No Image Selected")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("color: #888888; font-size: 14px;")

        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area)

    def set_zoom_mode(self, mode: Union[str, float]):
        if isinstance(mode, str):
            clean = mode.strip().lower()
            if clean in ("fit", "fit to window"):
                self._zoom_mode = "fit"
            elif clean == "50%":
                self._zoom_mode = 0.50
            elif clean == "75%":
                self._zoom_mode = 0.75
            elif clean == "100%":
                self._zoom_mode = 1.00
            elif clean == "120%":
                self._zoom_mode = 1.20
            else:
                try:
                    self._zoom_mode = float(clean.replace("%", "")) / 100.0
                except ValueError:
                    self._zoom_mode = "fit"
        else:
            self._zoom_mode = float(mode)

        self._update_scaled_pixmap()
        self.zoom_changed.emit(self.get_zoom_display_text())

    def get_zoom_mode(self) -> Union[str, float]:
        return self._zoom_mode

    def get_zoom_display_text(self) -> str:
        if self._zoom_mode == "fit":
            return "Fit"
        pct = int(round(self._zoom_mode * 100))
        return f"{pct}%"

    def zoom_in(self):
        if self._zoom_mode == "fit":
            self.set_zoom_mode(1.00)
            return

        current = float(self._zoom_mode)
        for preset in ZOOM_PRESETS:
            if preset > current + 0.01:
                self.set_zoom_mode(preset)
                return
        self.set_zoom_mode(ZOOM_PRESETS[-1])

    def zoom_out(self):
        if self._zoom_mode == "fit":
            self.set_zoom_mode(0.75)
            return

        current = float(self._zoom_mode)
        for preset in reversed(ZOOM_PRESETS):
            if preset < current - 0.01:
                self.set_zoom_mode(preset)
                return
        self.set_zoom_mode(ZOOM_PRESETS[0])

    def reset_scroll(self):
        self.scroll_area.verticalScrollBar().setValue(0)
        self.scroll_area.horizontalScrollBar().setValue(0)

    def set_image(self, image_path: Optional[Path]):
        if not image_path or not image_path.exists():
            self._current_pixmap = None
            self.image_label.setText("No Image Selected")
            self.image_label.setPixmap(QPixmap())
            self.image_label.resize(self.scroll_area.viewport().size())
            self.reset_scroll()
            return

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            self._current_pixmap = None
            self.image_label.setText("Failed to load image")
            self.image_label.setPixmap(QPixmap())
            self.image_label.resize(self.scroll_area.viewport().size())
            self.reset_scroll()
        else:
            self._current_pixmap = pixmap
            self._update_scaled_pixmap()
            self.reset_scroll()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom_mode == "fit":
            self._update_scaled_pixmap()

    def _update_scaled_pixmap(self):
        if not self._current_pixmap or self._current_pixmap.isNull():
            return

        viewport_size = self.scroll_area.viewport().size()
        if viewport_size.width() <= 0 or viewport_size.height() <= 0:
            return

        if self._zoom_mode == "fit":
            scaled = self._current_pixmap.scaled(
                viewport_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
            self.image_label.resize(viewport_size)
        else:
            factor = float(self._zoom_mode)
            orig_w = self._current_pixmap.width()
            orig_h = self._current_pixmap.height()
            target_w = max(1, int(orig_w * factor))
            target_h = max(1, int(orig_h * factor))

            scaled = self._current_pixmap.scaled(
                target_w, target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.image_label.setPixmap(scaled)
            self.image_label.resize(scaled.size())

