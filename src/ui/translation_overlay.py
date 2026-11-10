import os
import sys
from pathlib import Path
from typing import Optional, Dict, Tuple, List

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QSize, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

from src.models.translation_item import PageTranslation
from src.ports.comic_text_renderer import ComicTextRenderer
from src.infra.qt_comic_renderer import QtComicTextRenderer
from src.services.comic_text import (
    get_hyphenator,
    get_comic_font_family,
    calculate_scaled_rect,
    calculate_popup_rect,
    split_word_to_fit,
    wrap_words_to_width,
    fit_comic_text,
    get_bubble_styling,
    calculate_bubble_padding,
)

__all__ = [
    "get_hyphenator",
    "get_comic_font_family",
    "calculate_scaled_rect",
    "calculate_popup_rect",
    "split_word_to_fit",
    "wrap_words_to_width",
    "fit_comic_text",
    "get_bubble_styling",
    "calculate_bubble_padding",
    "TranslationOverlayWidget",
]


class TranslationOverlayWidget(QWidget):
    manual_box_created = pyqtSignal(tuple)  # (orig_x, orig_y, orig_w, orig_h)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        renderer: Optional[ComicTextRenderer] = None
    ):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self._renderer: ComicTextRenderer = renderer if renderer is not None else QtComicTextRenderer()
        self._enabled = True
        self._manual_box_mode = False
        self._drag_start: Optional[QPoint] = None
        self._drag_current: Optional[QPoint] = None
        self._page: Optional[PageTranslation] = None
        self._translations: Dict[str, str] = {}
        self._orig_size = QSize(0, 0)
        self._scaled_size = QSize(0, 0)
        self._offset = (0, 0)
        self._hovered_bubble_id: Optional[str] = None
        self._current_popup_rect = QRect()

    def set_manual_box_mode(self, enabled: bool):
        self._manual_box_mode = enabled
        self._drag_start = None
        self._drag_current = None
        if enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
        self.update()

    def is_manual_box_mode(self) -> bool:
        return self._manual_box_mode

    def is_overlay_enabled(self) -> bool:
        return self._enabled

    def set_overlay_enabled(self, enabled: bool):
        if self._enabled != enabled:
            self._enabled = enabled
            if not self._manual_box_mode:
                self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not enabled)
            if not enabled:
                self._hovered_bubble_id = None
                self._current_popup_rect = QRect()
                if not self._manual_box_mode:
                    self.unsetCursor()
            self.update()

    def toggle_visibility(self):
        self.set_overlay_enabled(not self._enabled)

    def set_data(
        self,
        page: Optional[PageTranslation],
        translations: Dict[str, str],
        orig_size: QSize,
        scaled_size: QSize,
        offset: Tuple[int, int] = (0, 0),
        image_path: Optional[Path] = None
    ):
        self._page = page
        self._translations = translations or {}
        self._orig_size = orig_size
        self._scaled_size = scaled_size
        self._offset = offset
        self._hovered_bubble_id = None
        self._current_popup_rect = QRect()
        self.unsetCursor()
        self.update()

    def clear(self):
        self._page = None
        self._translations = {}
        self._hovered_bubble_id = None
        self._current_popup_rect = QRect()
        self.unsetCursor()
        self.update()

    def _hit_test(self, pos: QPoint) -> Optional[str]:
        if not self._page or not self._translations:
            return None

        # 1. Direct hit on any bubble bounding box (search in reverse for top-most)
        for bubble in reversed(self._page.bubbles):
            if bubble.id not in self._translations:
                continue
            box_to_use = bubble.expanded_bbox if bubble.expanded_bbox else bubble.bbox
            rect = calculate_scaled_rect(
                box_to_use,
                self._orig_size,
                self._scaled_size,
                self._offset
            )
            if rect.contains(pos):
                return bubble.id

        # 2. Sticky hit: cursor is hovering the active popup card
        if self._hovered_bubble_id and self._current_popup_rect.isValid():
            if self._current_popup_rect.contains(pos):
                return self._hovered_bubble_id

        return None

    def mouseMoveEvent(self, event):
        if self._manual_box_mode:
            if self._drag_start is not None:
                self._drag_current = event.position().toPoint()
                self.update()
            event.accept()
            return

        if not self._enabled or not self._page or not self._translations:
            super().mouseMoveEvent(event)
            return

        pos = event.position().toPoint()
        new_hovered_id = self._hit_test(pos)
        if new_hovered_id != self._hovered_bubble_id:
            self._hovered_bubble_id = new_hovered_id
            if new_hovered_id:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self._current_popup_rect = QRect()
                self.unsetCursor()
            self.update()
        event.ignore()

    def leaveEvent(self, event):
        if self._manual_box_mode and self._drag_start is not None:
            self._drag_start = None
            self._drag_current = None
            self.update()
        if self._hovered_bubble_id is not None:
            self._hovered_bubble_id = None
            self._current_popup_rect = QRect()
            if not self._manual_box_mode:
                self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        event.ignore()

    def mousePressEvent(self, event):
        if self._manual_box_mode and event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.position().toPoint()
            self._drag_current = self._drag_start
            self.update()
            event.accept()
            return
        event.ignore()

    def mouseReleaseEvent(self, event):
        if self._manual_box_mode and event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            end_pos = event.position().toPoint()
            x1 = min(self._drag_start.x(), end_pos.x())
            y1 = min(self._drag_start.y(), end_pos.y())
            x2 = max(self._drag_start.x(), end_pos.x())
            y2 = max(self._drag_start.y(), end_pos.y())
            self._drag_start = None
            self._drag_current = None
            self.update()

            w = x2 - x1
            h = y2 - y1
            # Minimum threshold: 10x10 px to avoid accidental click
            if w >= 10 and h >= 10 and self._scaled_size.width() > 0 and self._scaled_size.height() > 0:
                off_x, off_y = self._offset
                sx = self._orig_size.width() / float(self._scaled_size.width())
                sy = self._orig_size.height() / float(self._scaled_size.height())

                orig_x = max(0, min(self._orig_size.width() - 1, int((x1 - off_x) * sx)))
                orig_y = max(0, min(self._orig_size.height() - 1, int((y1 - off_y) * sy)))
                orig_w = max(5, min(self._orig_size.width() - orig_x, int(w * sx)))
                orig_h = max(5, min(self._orig_size.height() - orig_y, int(h * sy)))

                self.manual_box_created.emit((orig_x, orig_y, orig_w, orig_h))

            event.accept()
            return
        event.ignore()

    def paintEvent(self, event):
        has_bubbles = (
            self._enabled
            and self._page
            and (self._translations or any(getattr(b, "is_manual", False) for b in self._page.bubbles))
        )
        has_drag = (self._manual_box_mode and self._drag_start is not None and self._drag_current is not None)
        if not has_bubbles and not has_drag:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        if has_bubbles and self._page:
            scale_x = self._scaled_size.width() / float(self._orig_size.width()) if self._orig_size.width() > 0 else 1.0
            self._renderer.render(
                painter=painter,
                page=self._page,
                translations=self._translations,
                scale_factor=scale_x,
                offset=self._offset,
                orig_size=self._orig_size,
                scaled_size=self._scaled_size,
            )

        # Render rubberband drag box when user is manually labeling a speech bubble
        if self._manual_box_mode and self._drag_start is not None and self._drag_current is not None:
            x1 = min(self._drag_start.x(), self._drag_current.x())
            y1 = min(self._drag_start.y(), self._drag_current.y())
            x2 = max(self._drag_start.x(), self._drag_current.x())
            y2 = max(self._drag_start.y(), self._drag_current.y())
            drag_rect = QRect(x1, y1, x2 - x1, y2 - y1)

            painter.save()
            painter.setBrush(QBrush(QColor(255, 255, 255, 30)))
            dash_pen = QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(dash_pen)
            painter.drawRect(drag_rect)
            painter.restore()

        painter.end()
