import os
import sys
import re
from pathlib import Path
from typing import Optional, Dict, Tuple, List
import numpy as np
try:
    import pyphen
except ImportError:
    pyphen = None

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRect, QSize, QPoint
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QPen, QBrush, QFontMetrics, QFontDatabase
)
from src.models.translation_item import PageTranslation, BubbleBlock

_hyphen_dic = None

def get_hyphenator():
    global _hyphen_dic
    if _hyphen_dic is None:
        try:
            _hyphen_dic = pyphen.Pyphen(lang='en_US')
        except Exception:
            _hyphen_dic = None
    return _hyphen_dic


_comic_family = None

def get_comic_font_family() -> str:
    global _comic_family
    if _comic_family is not None:
        return _comic_family

    candidates = [
        # PyInstaller bundle path
        Path(getattr(sys, "_MEIPASS", "")) / "assets" / "fonts" / "ComicNeue-Bold.ttf",
        # Source tree path
        Path(__file__).parent.parent.parent / "assets" / "fonts" / "ComicNeue-Bold.ttf",
    ]
    for c in candidates:
        if c.is_file():
            fid = QFontDatabase.addApplicationFont(str(c))
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                if families:
                    _comic_family = families[0]
                    return _comic_family

    _comic_family = "Comic Sans MS"
    return _comic_family


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


def calculate_popup_rect(
    center_point: QPoint,
    text: str,
    font_metrics: QFontMetrics,
    max_container_size: QSize,
    min_width: int = 120,
    max_width: int = 340,
    padding_x: int = 24,
    padding_y: int = 20,
) -> QRect:
    if max_container_size.width() <= 0 or max_container_size.height() <= 0 or not text:
        return QRect()

    raw_text_width = font_metrics.horizontalAdvance(text)
    target_width = min(max_width, max(min_width, raw_text_width + padding_x))
    target_width = min(target_width, max(min_width, max_container_size.width() - 16))

    inner_width = max(10, target_width - padding_x)
    text_bounds = font_metrics.boundingRect(
        0, 0, inner_width, 10000,
        int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignCenter),
        text
    )
    target_height = max(38, text_bounds.height() + padding_y)
    target_height = min(target_height, max_container_size.height() - 16)

    card_x = center_point.x() - target_width // 2
    card_y = center_point.y() - target_height // 2

    cw = max_container_size.width()
    ch = max_container_size.height()
    max_x = max(8, cw - target_width - 8)
    max_y = max(8, ch - target_height - 8)
    clamped_x = max(8, min(card_x, max_x))
    clamped_y = max(8, min(card_y, max_y))

    return QRect(clamped_x, clamped_y, target_width, target_height)


def get_hyphenation_variants(words: List[str]) -> List[List[str]]:
    sequences = [words]
    dic = get_hyphenator()
    if not dic:
        return sequences

    for i, word in enumerate(words):
        clean_word = re.sub(r'^[^\w]+|[^\w]+$', '', word)
        if len(clean_word) >= 8:
            try:
                hyphenated = dic.inserted(clean_word)
                if '-' in hyphenated:
                    parts = hyphenated.split('-')
                    prefix = word[:word.find(clean_word)]
                    suffix = word[word.find(clean_word) + len(clean_word):]
                    p1 = prefix + parts[0] + '-'
                    p2 = ''.join(parts[1:]) + suffix
                    sequences.append(words[:i] + [p1, p2] + words[i+1:])
            except Exception:
                pass
    return sequences


def fit_comic_text(
    text: str,
    inner_w: int,
    inner_h: int,
    shape: str = "oval",
    scale_factor: float = 1.0
) -> Tuple[int, List[str], float, float, int, int]:
    """
    Computes optimal Comic font size, line wrapping, tracking and word spacing.
    Returns: (best_pt, best_lines, letter_sp, word_sp, line_height, total_h)
    """
    family = get_comic_font_family()
    base_words = text.split()
    total_words = len(base_words)

    aspect = inner_w / float(inner_h) if inner_h > 0 else 1.0

    if aspect < 0.65:
        letter_sp = -0.3
        word_sp = -0.8
    elif aspect > 1.3:
        letter_sp = 0.2
        word_sp = 0.5
    else:
        letter_sp = 0.0
        word_sp = 0.0

    # Base scale bounds scaled by view scale factor
    base_max_pt = 26 if total_words <= 2 else (22 if total_words <= 6 else 19)
    base_min_pt = 10

    max_pt = max(base_min_pt, int(round(base_max_pt * scale_factor)))
    min_pt = max(8, int(round(base_min_pt * scale_factor)))

    sequences = get_hyphenation_variants(base_words)
    candidates = []

    for seq in sequences:
        for pt in range(max_pt, min_pt - 1, -1):
            font = QFont(family, pt)
            font.setWeight(QFont.Weight.Bold)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_sp)
            font.setWordSpacing(word_sp)
            fm = QFontMetrics(font)

            lines = []
            cur_line = []
            cur_w = 0
            fits = True

            for word in seq:
                word_w = fm.horizontalAdvance(word)
                space_w = fm.horizontalAdvance(' ')
                if not cur_line:
                    if word_w > inner_w:
                        fits = False
                        break
                    cur_line.append(word)
                    cur_w = word_w
                else:
                    if cur_w + space_w + word_w <= inner_w:
                        cur_line.append(word)
                        cur_w += space_w + word_w
                    else:
                        lines.append(' '.join(cur_line))
                        if word_w > inner_w:
                            fits = False
                            break
                        cur_line = [word]
                        cur_w = word_w
            if cur_line:
                lines.append(' '.join(cur_line))

            if not fits or not lines:
                continue

            line_height = int(fm.height() * 1.05)
            total_text_h = len(lines) * line_height

            if total_text_h <= inner_h:
                fill_ratio = total_text_h / float(inner_h)
                score = pt * 4.0

                if 0.50 <= fill_ratio <= 0.85:
                    score += 25.0
                elif fill_ratio < 0.35 and aspect >= 0.7:
                    score -= (0.35 - fill_ratio) * 40.0

                if aspect >= 0.85 and len(lines) > 1:
                    orphan_count = sum(1 for line in lines if len(line.split()) == 1)
                    score -= orphan_count * 15.0

                if len(seq) > len(base_words):
                    score += 5.0

                widths = [fm.horizontalAdvance(l) for l in lines]
                score -= float(np.std(widths)) * 0.15

                candidates.append((score, pt, lines, letter_sp, word_sp, line_height, total_text_h))

    if not candidates:
        fallback_pt = min_pt
        fallback_lines = [text]
        font = QFont(family, fallback_pt)
        fm = QFontMetrics(font)
        lh = int(fm.height() * 1.05)
        return (fallback_pt, fallback_lines, 0.0, 0.0, lh, len(fallback_lines) * lh)

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, best_pt, best_lines, best_letter_sp, best_word_sp, line_height, total_h = candidates[0]
    return (best_pt, best_lines, best_letter_sp, best_word_sp, line_height, total_h)


class TranslationOverlayWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
        self._enabled = True
        self._page: Optional[PageTranslation] = None
        self._translations: Dict[str, str] = {}
        self._orig_size = QSize(0, 0)
        self._scaled_size = QSize(0, 0)
        self._offset = (0, 0)
        self._hovered_bubble_id: Optional[str] = None
        self._current_popup_rect = QRect()

    def is_overlay_enabled(self) -> bool:
        return self._enabled

    def set_overlay_enabled(self, enabled: bool):
        if self._enabled != enabled:
            self._enabled = enabled
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, not enabled)
            if not enabled:
                self._hovered_bubble_id = None
                self._current_popup_rect = QRect()
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
        if self._hovered_bubble_id is not None:
            self._hovered_bubble_id = None
            self._current_popup_rect = QRect()
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        event.ignore()

    def mousePressEvent(self, event):
        event.ignore()

    def mouseReleaseEvent(self, event):
        event.ignore()

    def paintEvent(self, event):
        if not self._enabled or not self._page or not self._translations:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        family = get_comic_font_family()
        scale_x = self._scaled_size.width() / float(self._orig_size.width()) if self._orig_size.width() > 0 else 1.0

        for bubble in self._page.bubbles:
            text_en = self._translations.get(bubble.id)
            if not text_en:
                continue

            # Target region for text rendering
            box_to_use = bubble.expanded_bbox if bubble.expanded_bbox else bubble.bbox
            rect = calculate_scaled_rect(
                box_to_use,
                self._orig_size,
                self._scaled_size,
                self._offset
            )
            if rect.isEmpty():
                continue

            shape = getattr(bubble, 'shape', 'oval')
            if shape == 'inverted':
                # Semi-translucent dark background with white text for narration/sound effects over art
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(15, 15, 15, 230)))
                painter.drawRoundedRect(rect, 4, 4)
                text_color = QColor(245, 245, 245)
            elif shape == 'oval':
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 255, 255, 245)))
                painter.drawEllipse(rect)
                text_color = QColor(15, 15, 15)
            else:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 255, 255, 245)))
                painter.drawRoundedRect(rect, 4, 4)
                text_color = QColor(15, 15, 15)

            # Calculate safe inner area
            if shape == 'oval':
                pad_x = max(6, int(rect.width() * 0.12))
                pad_y = max(6, int(rect.height() * 0.10))
            else:
                pad_x = max(4, int(rect.width() * 0.08))
                pad_y = max(4, int(rect.height() * 0.08))

            inner_w = max(10, rect.width() - 2 * pad_x)
            inner_h = max(10, rect.height() - 2 * pad_y)

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
            if bubble.centroid is not None and self._orig_size.width() > 0 and self._orig_size.height() > 0:
                cx_orig, cy_orig = bubble.centroid
                cx = self._offset[0] + int(round(cx_orig * scale_x))
                cy = self._offset[1] + int(round(cy_orig * (self._scaled_size.height() / float(self._orig_size.height()))))
            else:
                cx = rect.center().x()
                cy = rect.center().y()

            start_y = cy - total_h // 2 + fm.ascent()

            painter.setPen(text_color)
            for i, line in enumerate(best_lines):
                lw = fm.horizontalAdvance(line)
                lx = cx - lw // 2
                ly = start_y + i * lh
                painter.drawText(QPoint(lx, ly), line)

        painter.end()
