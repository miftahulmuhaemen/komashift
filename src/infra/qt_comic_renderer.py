from typing import Dict, Tuple, Optional, Union
from PyQt6.QtCore import Qt, QRect, QPoint, QSize
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QFontMetrics

from src.models.translation_item import PageTranslation
from src.ports.comic_text_renderer import ComicTextRenderer
from src.services.comic_text import (
    calculate_scaled_rect,
    fit_comic_text,
    get_comic_font_family,
    get_bubble_styling,
    calculate_bubble_padding,
)


class QtComicTextRenderer(ComicTextRenderer):
    """QPainter adapter implementing ComicTextRenderer port."""

    def render(
        self,
        painter: QPainter,
        page: PageTranslation,
        translations: Dict[str, str],
        scale_factor: float = 1.0,
        offset: Tuple[int, int] = (0, 0),
        orig_size: Optional[Union[QSize, Tuple[int, int]]] = None,
        scaled_size: Optional[Union[QSize, Tuple[int, int]]] = None,
    ) -> None:
        if not page or not page.bubbles:
            return

        if orig_size is not None:
            orig_w = orig_size.width() if hasattr(orig_size, "width") else orig_size[0]
            orig_h = orig_size.height() if hasattr(orig_size, "height") else orig_size[1]
        else:
            orig_w = page.page_width
            orig_h = page.page_height

        if scaled_size is not None:
            scaled_w = scaled_size.width() if hasattr(scaled_size, "width") else scaled_size[0]
            scaled_h = scaled_size.height() if hasattr(scaled_size, "height") else scaled_size[1]
        else:
            scaled_w = int(round(orig_w * scale_factor))
            scaled_h = int(round(orig_h * scale_factor))

        scale_x = scaled_w / float(orig_w) if orig_w > 0 else 1.0
        scale_y = scaled_h / float(orig_h) if orig_h > 0 else 1.0

        family = get_comic_font_family()

        for bubble in page.bubbles:
            # Check if this is an untranslated manual bubble
            if getattr(bubble, "is_manual", False) and not bubble.text_ja:
                text_en = None
            else:
                text_en = translations.get(bubble.id)

            if not text_en:
                if getattr(bubble, "is_manual", False):
                    box_to_use = bubble.expanded_bbox if bubble.expanded_bbox else bubble.bbox
                    rect = calculate_scaled_rect(
                        box_to_use,
                        (orig_w, orig_h),
                        (scaled_w, scaled_h),
                        offset
                    )
                    if not rect.isEmpty():
                        painter.save()
                        painter.setBrush(QBrush(QColor(0, 0, 0, 110)))
                        painter.setPen(QPen(QColor("#ffffff"), 1.4, Qt.PenStyle.DashLine))
                        painter.drawRoundedRect(rect, 3, 3)
                        painter.setPen(QColor("#ffffff"))
                        font = QFont("Arial", max(8, int(10 * scale_x)), QFont.Weight.Bold)
                        painter.setFont(font)
                        display_text = bubble.text_ja if bubble.text_ja else "[Manual Label]"
                        painter.drawText(
                            rect,
                            int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                            display_text
                        )
                        painter.restore()
                continue

            # Target region for text rendering
            box_to_use = bubble.expanded_bbox if bubble.expanded_bbox else bubble.bbox
            rect = calculate_scaled_rect(
                box_to_use,
                (orig_w, orig_h),
                (scaled_w, scaled_h),
                offset
            )
            if rect.isEmpty():
                continue

            shape = getattr(bubble, "shape", "oval")
            bg_rgba, text_rgb, draw_shape, corner_radius = get_bubble_styling(shape)
            pad_x, pad_y, inner_w, inner_h = calculate_bubble_padding(shape, rect.width(), rect.height())

            # Draw speech bubble background
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(*bg_rgba)))
            if draw_shape == "ellipse":
                painter.drawEllipse(rect)
            else:
                painter.drawRoundedRect(rect, corner_radius, corner_radius)

            # Fit text dynamically
            best_pt, best_lines, l_sp, w_sp, lh, total_h = fit_comic_text(
                text_en, inner_w, inner_h, shape=shape, scale_factor=scale_x
            )

            font = QFont(family, best_pt)
            font.setWeight(QFont.Weight.Bold)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, l_sp)
            font.setWordSpacing(w_sp)
            painter.setFont(font)
            fm = QFontMetrics(font)

            # Scaled centroid or rect center
            if bubble.centroid is not None and orig_w > 0 and orig_h > 0:
                cx_orig, cy_orig = bubble.centroid
                cx = offset[0] + int(round(cx_orig * scale_x))
                cy = offset[1] + int(round(cy_orig * scale_y))
            else:
                cx = rect.center().x()
                cy = rect.center().y()

            # Clamp centroid so it remains well inside rect
            cx = max(rect.left() + pad_x + 2, min(rect.right() - pad_x - 2, cx))
            cy = max(rect.top() + pad_y + 2, min(rect.bottom() - pad_y - 2, cy))

            start_y = cy - total_h // 2 + fm.ascent()

            painter.save()
            painter.setClipRect(rect.adjusted(-2, -2, 2, 2))
            painter.setPen(QColor(*text_rgb))
            for i, line in enumerate(best_lines):
                lw = fm.horizontalAdvance(line)
                lx = cx - lw // 2
                ly = start_y + i * lh
                painter.drawText(QPoint(lx, ly), line)
            painter.restore()
