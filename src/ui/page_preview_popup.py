from pathlib import Path
from typing import Optional
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPixmap, QGuiApplication
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QFrame, QLabel

from src.services.thumbnail_cache import create_thumbnail_pixmap


class PageThumbnailHoverPopup(QWidget):
    """Floating hover preview for pages in the Queue Pages tab."""
    def __init__(self, parent=None, thumbnail_cache=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.thumbnail_cache = thumbnail_cache
        self._current_path: Optional[str] = None
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame(self)
        self.frame.setStyleSheet("""
            QFrame {
                background-color: #18181b;
                border: 1px solid #38bdf8;
                border-radius: 6px;
            }
        """)
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(6, 6, 6, 6)
        frame_layout.setSpacing(4)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setFixedSize(110, 140)
        self.img_label.setStyleSheet("background-color: #09090b; border-radius: 4px; color: #94a3b8; font-size: 11px;")
        frame_layout.addWidget(self.img_label)

        self.caption_label = QLabel()
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_label.setStyleSheet("color: #cbd5e1; font-size: 11px; font-weight: 500;")
        self.caption_label.setMaximumWidth(110)
        self.caption_label.setWordWrap(True)
        frame_layout.addWidget(self.caption_label)

        layout.addWidget(self.frame)
        self.hide()

    def show_page(self, img_path: Path, caption: str, global_pos: QPoint):
        path_str = str(img_path)
        self._current_path = path_str
        self.caption_label.setText(img_path.name)

        target_size = (110, 140)
        pix = None
        if self.thumbnail_cache:
            pix = self.thumbnail_cache.get(img_path, target_size)
            if not pix:
                self.img_label.setText("Loading...")
                self.thumbnail_cache.load_async(
                    img_path,
                    target_size,
                    lambda p, loaded_pix: self._on_thumb_loaded(p, loaded_pix)
                )
        if not pix and not self.thumbnail_cache:
            pix = create_thumbnail_pixmap(img_path, target_size)

        if pix and not pix.isNull():
            self.img_label.setPixmap(pix.scaled(
                110, 140,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

        screen = QGuiApplication.primaryScreen()
        target_x = global_pos.x() + 20
        target_y = global_pos.y() - 70
        if screen:
            screen_geom = screen.availableGeometry()
            if target_x + 130 > screen_geom.right():
                target_x = global_pos.x() - 140
            if target_y < screen_geom.top():
                target_y = screen_geom.top() + 10
            elif target_y + 175 > screen_geom.bottom():
                target_y = screen_geom.bottom() - 180

        self.move(target_x, target_y)
        self.show()
        self.raise_()

    def _on_thumb_loaded(self, path_str: str, pix: QPixmap):
        if self._current_path == path_str and self.isVisible():
            if pix and not pix.isNull():
                self.img_label.setPixmap(pix.scaled(
                    110, 140,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                ))
