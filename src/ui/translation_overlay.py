from typing import Optional, Dict, Tuple
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from src.models.translation_item import PageTranslation

def calculate_scaled_rect(
    bbox: Tuple[int, int, int, int],
    orig_size: QSize,
    scaled_size: QSize,
    offset: Tuple[int, int] = (0, 0)
) -> QRect:
    orig_w = orig_size.width()
    orig_h = orig_size.height()
    if orig_w <= 0 or orig_h <= 0:
        return QRect()

    bx, by, bw, bh = bbox
    scale_x = scaled_size.width() / orig_w
    scale_y = scaled_size.height() / orig_h

    final_x = offset[0] + int(round(bx * scale_x))
    final_y = offset[1] + int(round(by * scale_y))
    final_w = max(1, int(round(bw * scale_x)))
    final_h = max(1, int(round(bh * scale_y)))

    return QRect(final_x, final_y, final_w, final_h)

class TranslationOverlayWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._enabled = True
        self._page: Optional[PageTranslation] = None
        self._translations: Dict[str, str] = {}
        self._orig_size = QSize(0, 0)
        self._scaled_size = QSize(0, 0)
        self._offset = (0, 0)

    def is_overlay_enabled(self) -> bool:
        return self._enabled

    def set_overlay_enabled(self, enabled: bool):
        if self._enabled != enabled:
            self._enabled = enabled
            self.update()

    def toggle_visibility(self):
        self.set_overlay_enabled(not self._enabled)

    def set_data(
        self,
        page: Optional[PageTranslation],
        translations: Dict[str, str],
        orig_size: QSize,
        scaled_size: QSize,
        offset: Tuple[int, int] = (0, 0)
    ):
        self._page = page
        self._translations = translations or {}
        self._orig_size = orig_size
        self._scaled_size = scaled_size
        self._offset = offset
        self.update()

    def clear(self):
        self._page = None
        self._translations = {}
        self.update()

    def paintEvent(self, event):
        if not self._enabled or not self._page or not self._translations:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_brush = QBrush(QColor(255, 255, 255, 235))
        border_pen = QPen(QColor(40, 40, 40, 220), 1.5)
        text_pen = QPen(QColor(10, 10, 10))

        for bubble in self._page.bubbles:
            text_en = self._translations.get(bubble.id)
            if not text_en:
                continue

            rect = calculate_scaled_rect(
                bubble.bbox,
                self._orig_size,
                self._scaled_size,
                self._offset
            )
            if rect.isEmpty():
                continue

            # Draw speech bubble covering box
            painter.setBrush(bg_brush)
            painter.setPen(border_pen)
            painter.drawRoundedRect(rect, 6, 6)

            # Calculate adaptive font size
            font_size = max(8, min(14, int(rect.height() / (max(1, len(text_en.split())) * 1.5) + 6)))
            font = QFont("Sans-Serif", font_size)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(text_pen)

            # Draw centered text with word wrap
            inner_rect = rect.adjusted(3, 3, -3, -3)
            painter.drawText(
                inner_rect,
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                text_en
            )

        painter.end()
