import os
import sys
import re
from pathlib import Path
from typing import Optional, Tuple, List, Union, Any
try:
    import pyphen
except ImportError:
    pyphen = None

from PyQt6.QtCore import Qt, QRect, QSize, QPoint
from PyQt6.QtGui import QFont, QFontMetrics, QFontDatabase

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

    from PyQt6.QtCore import QCoreApplication
    if not QCoreApplication.instance():
        return "Comic Sans MS"

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


def _get_wh(size: Union[QSize, Tuple[int, int], List[int]]) -> Tuple[int, int]:
    if hasattr(size, "width") and hasattr(size, "height"):
        return size.width(), size.height()
    return int(size[0]), int(size[1])


def calculate_scaled_rect(
    bbox: Tuple[int, int, int, int],
    orig_size: Union[QSize, Tuple[int, int], List[int]],
    scaled_size: Union[QSize, Tuple[int, int], List[int]],
    offset: Tuple[int, int] = (0, 0)
) -> QRect:
    orig_w, orig_h = _get_wh(orig_size)
    scaled_w, scaled_h = _get_wh(scaled_size)
    if orig_w <= 0 or orig_h <= 0:
        return QRect()

    bx, by, bw, bh = bbox
    scale_x = scaled_w / orig_w
    scale_y = scaled_h / orig_h

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


def _char_level_split(word: str, fm: QFontMetrics, max_w: int) -> List[str]:
    """Fallback character-level splitting for indivisible long words in extreme narrow containers."""
    final_chunks = []
    rem = word
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


def split_word_to_fit(word: str, fm: QFontMetrics, max_w: int, dic=None, allow_char_split: bool = False) -> List[str]:
    """
    Splits a single word into chunks that each fit within max_w.
    Prefers syllable hyphenation for long words (length >= 7),
    strictly disallowing hyphenating short words (<= 6 chars) or producing tiny fragments (< 3 chars).
    """
    if not word or fm.horizontalAdvance(word) <= max_w:
        return [word]

    clean_word = re.sub(r"^\W+|\W+$", "", word)
    # Typographic rule: Never hyphenate short words (<= 6 letters) like Hello, Nice, meet, pretty, called
    if len(clean_word) <= 6:
        if allow_char_split:
            return _char_level_split(word, fm, max_w)
        return [word]

    chunks = []
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
                        clean_cur = cur_chunk.rstrip("-")
                        clean_next = p.rstrip("-")
                        # Typographic rule: Ensure at least 3 letters before hyphen and at least 2 after
                        if len(clean_cur) >= 3 and len(clean_next) >= 2:
                            chunks.append(cur_chunk if cur_chunk.endswith("-") else cur_chunk + "-")
                            cur_chunk = p + ("" if is_last else "-")
                            if is_last:
                                cur_chunk += suffix
                        else:
                            cur_chunk = test_part
                if cur_chunk:
                    chunks.append(cur_chunk)
        except Exception:
            pass

    if chunks and all(fm.horizontalAdvance(ch) <= max_w for ch in chunks):
        return chunks

    if allow_char_split:
        return _char_level_split(word, fm, max_w)

    return [word]


def _wrap_words_to_width_scored(words: List[str], fm: QFontMetrics, max_w: int, dic=None, allow_char_split: bool = False) -> Tuple[List[str], bool, int]:
    """
    Wraps a list of words to fit inside max_w.
    Returns: (lines, has_overflow, hyphen_count)
    """
    lines = []
    cur_line = []
    cur_w = 0
    space_w = fm.horizontalAdvance(" ")
    has_overflow = False
    hyphen_count = 0

    for word in words:
        chunks = split_word_to_fit(word, fm, max_w, dic, allow_char_split=allow_char_split)
        if len(chunks) > 1:
            hyphen_count += (len(chunks) - 1)
        for idx, chunk in enumerate(chunks):
            chunk_w = fm.horizontalAdvance(chunk)
            if chunk_w > max_w:
                has_overflow = True
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
    return lines, has_overflow, hyphen_count


def wrap_words_to_width(words: List[str], fm: QFontMetrics, max_w: int, dic=None) -> List[str]:
    """
    Wraps a list of words to fit inside max_w, splitting overlong words as necessary.
    Guarantees no returned line exceeds max_w.
    """
    lines, _, _ = _wrap_words_to_width_scored(words, fm, max_w, dic, allow_char_split=True)
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
    Prioritizes word integrity over font size, preventing aggressive syllable breakdown.
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

        lines, has_overflow, hyphen_count = _wrap_words_to_width_scored(base_words, fm, inner_w, dic, allow_char_split=False)
        if not lines or has_overflow:
            continue

        line_height = int(fm.height() * 1.05)
        total_text_h = len(lines) * line_height
        all_wrapped_by_pt[pt] = (lines, line_height, total_text_h)

        if total_text_h <= inner_h:
            fill_ratio = total_text_h / float(inner_h)
            # Base score rewards legible font size, but heavily penalizes hyphenation
            score = pt * 6.0 - (hyphen_count * 45.0)

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
        # Fallback: test from min_pt down allowing emergency syllable/char splitting if unavoidable
        fallback_pt = emergency_min_pt
        for pt in range(min_pt, emergency_min_pt - 1, -1):
            font = QFont(family, pt)
            font.setWeight(QFont.Weight.Bold)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_sp)
            font.setWordSpacing(word_sp)
            fm = QFontMetrics(font)
            lines, _, hyphens = _wrap_words_to_width_scored(base_words, fm, inner_w, dic, allow_char_split=True)
            lh = int(fm.height() * 1.05)
            total_h = len(lines) * lh
            if total_h <= inner_h:
                fallback_pt = pt
                all_wrapped_by_pt[pt] = (lines, lh, total_h)
                break

        if fallback_pt in all_wrapped_by_pt:
            lines, lh, total_h = all_wrapped_by_pt[fallback_pt]
        else:
            font = QFont(family, fallback_pt)
            font.setWeight(QFont.Weight.Bold)
            font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, letter_sp)
            font.setWordSpacing(word_sp)
            fm = QFontMetrics(font)
            lines, _, _ = _wrap_words_to_width_scored(base_words, fm, inner_w, dic, allow_char_split=True)
            lh = int(fm.height() * 1.05)
            total_h = len(lines) * lh
        return (fallback_pt, lines, letter_sp, word_sp, lh, total_h)

    candidates.sort(key=lambda x: x[0], reverse=True)
    _, best_pt, best_lines, best_letter_sp, best_word_sp, line_height, total_h = candidates[0]
    return (best_pt, best_lines, best_letter_sp, best_word_sp, line_height, total_h)


def get_bubble_styling(shape: str) -> Tuple[Tuple[int, int, int, int], Tuple[int, int, int], str, int]:
    """
    Returns (bg_color_rgba, text_color_rgb, draw_shape, corner_radius) for a given bubble shape.
    draw_shape is either 'ellipse' or 'rounded_rect'.
    """
    if shape == 'inverted':
        # Semi-translucent dark background with white text for narration/sound effects over art
        return ((15, 15, 15, 230), (245, 245, 245), "rounded_rect", 4)
    elif shape == 'oval':
        return ((255, 255, 255, 245), (15, 15, 15), "ellipse", 0)
    else:
        return ((255, 255, 255, 245), (15, 15, 15), "rounded_rect", 4)


def calculate_bubble_padding(shape: str, rect_w: int, rect_h: int) -> Tuple[int, int, int, int]:
    """
    Returns (pad_x, pad_y, inner_w, inner_h) ensuring typography fits comfortably inside bubble bounds.
    """
    if shape == 'oval':
        pad_x = max(4, int(rect_w * 0.08))
        pad_y = max(4, int(rect_h * 0.07))
    else:
        pad_x = max(3, int(rect_w * 0.04))
        pad_y = max(3, int(rect_h * 0.03))

    pad_x = min(pad_x, max(2, int(rect_w * 0.12)))
    pad_y = min(pad_y, max(2, int(rect_h * 0.12)))

    inner_w = max(20, rect_w - 2 * pad_x)
    inner_h = max(20, rect_h - 2 * pad_y)

    return pad_x, pad_y, inner_w, inner_h
