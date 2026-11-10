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
from PyQt6.QtCore import Qt, QRect, QSize, QPoint, pyqtSignal
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


def split_word_to_fit(word: str, fm: QFontMetrics, max_w: int, dic=None) -> List[str]:
    """
    Splits a single word into chunks that each fit within max_w.
    Prefers syllable hyphenation, falling back to character-level splitting.
    """
    if not word or fm.horizontalAdvance(word) <= max_w:
        return [word]

    chunks = []
    clean_word = re.sub(r"^[^\w]+|[^\w]+$", "", word)
    if dic and clean_word:
        try:
            hyphenated = dic.inserted(clean_word)
            if "-" in hyphenated:
                parts = hyphenated.split("-")
                prefix = word[:word.find(clean_word)]
                suffix = word[word.find(clean_word) + len(clean_word):]

                cur_chunk = prefix
                for i, p in enumerate(parts):
                    is_last = (i == len(parts) - 1)
                    test_part = cur_chunk + p + ("" if is_last else "-")
                    if is_last:
                        test_part += suffix

                    if fm.horizontalAdvance(test_part) <= max_w:
                        cur_chunk = test_part
                    else:
                        if cur_chunk:
                            chunks.append(cur_chunk if cur_chunk.endswith("-") else cur_chunk + "-")
                        cur_chunk = p + ("" if is_last else "-")
                        if is_last:
                            cur_chunk += suffix
                if cur_chunk:
                    chunks.append(cur_chunk)
        except Exception:
            pass

    to_process = chunks if chunks else [word]
    final_chunks = []
    for ch in to_process:
        if fm.horizontalAdvance(ch) <= max_w:
            final_chunks.append(ch)
        else:
            # Character-level chunking fallback
            rem = ch
            while rem:
                if fm.horizontalAdvance(rem) <= max_w:
                    final_chunks.append(rem)
                    break
                sub = ""
                for char in rem:
                    test_sub = sub + char + "-"
                    if fm.horizontalAdvance(test_sub) <= max_w or not sub:
                        sub += char
                    else:
                        break
                final_chunks.append(sub + "-")
                rem = rem[len(sub):]
    return final_chunks if final_chunks else [word]


def wrap_words_to_width(words: List[str], fm: QFontMetrics, max_w: int, dic=None) -> List[str]:
    """
    Wraps a list of words to fit inside max_w, splitting overlong words as necessary.
    Guarantees no returned line exceeds max_w.
    """
    lines = []
    cur_line = []
    cur_w = 0
    space_w = fm.horizontalAdvance(" ")

    for word in words:
        chunks = split_word_to_fit(word, fm, max_w, dic)
        for idx, chunk in enumerate(chunks):
            chunk_w = fm.horizontalAdvance(chunk)
            if not cur_line:
                cur_line.append(chunk)
                cur_w = chunk_w
            else:
                if idx == 0 and cur_w + space_w + chunk_w <= max_w:
                    cur_line.append(chunk)
                    cur_w += space_w + chunk_w
                else:
                    lines.append(" ".join(cur_line))
                    cur_line = [chunk]
                    cur_w = chunk_w
    if cur_line:
        lines.append(" ".join(cur_line))
    return lines


def fit_comic_text(
    text: str,
    inner_w: int,
    inner_h: int,
    shape: str = "oval",
    scale_factor: float = 1.0
) -> Tuple[int, List[str], float, float, int, int]:
    """
    Computes optimal Comic font size, line wrapping, tracking and word spacing.
    Guarantees text is wrapped within inner_w and never returns an unwrapped single line.
    Returns: (best_pt, best_lines, letter_sp, word_sp, line_height, total_h)
    """
    family = get_comic_font_family()
    base_words = text.split()
    total_words = len(base_words)

    if not base_words:
        return (10, [], 0.0, 0.0, 10, 0)

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
    base_max_pt = 32 if total_words <= 2 else (28 if total_words <= 6 else 24)
    base_min_pt = 10
    emergency_min_pt = max(6, int(round(6 * scale_factor)))

    max_pt = max(base_min_pt, int(round(base_max_pt * scale_factor)))
    min_pt = max(8, int(round(base_min_pt * scale_factor)))

    dic = get_hyphenator()
    candidates = []
    all_wrapped_by_pt = {}

    for pt in range(max_pt, emergency_min_pt - 1, -1):
        font = QFont(family, pt)
        font.setWeight(QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_sp)
        font.setWordSpacing(word_sp)
        fm = QFontMetrics(font)

        lines = wrap_words_to_width(base_words, fm, inner_w, dic)
        if not lines:
            continue

        line_height = int(fm.height() * 1.05)
        total_text_h = len(lines) * line_height
        all_wrapped_by_pt[pt] = (lines, line_height, total_text_h)

        if total_text_h <= inner_h:
            fill_ratio = total_text_h / float(inner_h)
            score = pt * 6.0

            if 0.40 <= fill_ratio <= 0.90:
                score += 30.0
            elif fill_ratio < 0.35 and aspect >= 0.7:
                score -= (0.35 - fill_ratio) * 40.0

            if aspect >= 0.85 and len(lines) > 1:
                orphan_count = sum(1 for line in lines if len(line.split()) == 1)
                score -= orphan_count * 15.0

            # Diamond shape bonus for ovals: wider middle lines
            if shape == "oval" and len(lines) >= 3:
                mid = len(lines) // 2
                widths = [fm.horizontalAdvance(l) for l in lines]
                if widths[mid] >= widths[0] and widths[mid] >= widths[-1]:
                    score += 15.0

            candidates.append((score, pt, lines, letter_sp, word_sp, line_height, total_text_h))

    if not candidates:
        fallback_pt = emergency_min_pt
        if fallback_pt in all_wrapped_by_pt:
            lines, lh, total_h = all_wrapped_by_pt[fallback_pt]
        else:
            font = QFont(family, fallback_pt)
            font.setWeight(QFont.Weight.Bold)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_sp)
            font.setWordSpacing(word_sp)
            fm = QFontMetrics(font)
            lines = wrap_words_to_width(base_words, fm, inner_w, dic)
            lh = int(fm.height() * 1.05)
            total_h = len(lines) * lh
        return (fallback_pt, lines, letter_sp, word_sp, lh, total_h)

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, best_pt, best_lines, best_letter_sp, best_word_sp, line_height, total_h = candidates[0]
    return (best_pt, best_lines, best_letter_sp, best_word_sp, line_height, total_h)


class TranslationOverlayWidget(QWidget):
    manual_box_created = pyqtSignal(tuple)  # (orig_x, orig_y, orig_w, orig_h)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setMouseTracking(True)
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
        has_bubbles = (self._enabled and self._page and (self._translations or any(getattr(b, "is_manual", False) for b in self._page.bubbles)))
        has_drag = (self._manual_box_mode and self._drag_start is not None and self._drag_current is not None)
        if not has_bubbles and not has_drag:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        if has_bubbles and self._page:
            family = get_comic_font_family()
            scale_x = self._scaled_size.width() / float(self._orig_size.width()) if self._orig_size.width() > 0 else 1.0

            for bubble in self._page.bubbles:
                # If this is a manual bubble that hasn't undergone OCR/queue processing yet, force untranslated display
                if getattr(bubble, "is_manual", False) and not bubble.text_ja:
                    text_en = None
                else:
                    text_en = self._translations.get(bubble.id)
                if not text_en:
                    if getattr(bubble, "is_manual", False):
                        box_to_use = bubble.expanded_bbox if bubble.expanded_bbox else bubble.bbox
                        rect = calculate_scaled_rect(
                            box_to_use,
                            self._orig_size,
                            self._scaled_size,
                            self._offset
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
                            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap), display_text)
                            painter.restore()
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

                # Calculate safe inner area with narrowed padding for maximum readable typography
                if shape == 'oval':
                    pad_x = max(4, int(rect.width() * 0.08))
                    pad_y = max(4, int(rect.height() * 0.07))
                else:
                    pad_x = max(3, int(rect.width() * 0.04))
                    pad_y = max(3, int(rect.height() * 0.03))

                # Prevent padding from choking narrow bubbles
                pad_x = min(pad_x, max(2, int(rect.width() * 0.12)))
                pad_y = min(pad_y, max(2, int(rect.height() * 0.12)))

                inner_w = max(20, rect.width() - 2 * pad_x)
                inner_h = max(20, rect.height() - 2 * pad_y)

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

                # Clamp centroid so it remains well inside rect
                cx = max(rect.left() + pad_x + 2, min(rect.right() - pad_x - 2, cx))
                cy = max(rect.top() + pad_y + 2, min(rect.bottom() - pad_y - 2, cy))

                start_y = cy - total_h // 2 + fm.ascent()

                painter.save()
                painter.setClipRect(rect.adjusted(-2, -2, 2, 2))

                painter.setPen(text_color)
                for i, line in enumerate(best_lines):
                    lw = fm.horizontalAdvance(line)
                    lx = cx - lw // 2
                    ly = start_y + i * lh
                    painter.drawText(QPoint(lx, ly), line)

                painter.restore()

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
