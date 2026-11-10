from PyQt6.QtCore import QSize, QRect, QPoint
from PyQt6.QtGui import QFont, QFontMetrics, QPixmap, QPainter
from src.models.translation_item import BubbleBlock, PageTranslation
from src.services.comic_text import (
    get_bubble_styling,
    calculate_bubble_padding,
    calculate_scaled_rect,
    calculate_popup_rect,
    fit_comic_text,
    get_comic_font_family,
    get_hyphenator,
)
from src.infra.qt_comic_renderer import QtComicTextRenderer


def test_bubble_styling():
    inv_bg, inv_txt, inv_shape, inv_r = get_bubble_styling("inverted")
    assert inv_shape == "rounded_rect"
    assert inv_bg == (15, 15, 15, 230)
    assert inv_txt == (245, 245, 245)

    oval_bg, oval_txt, oval_shape, oval_r = get_bubble_styling("oval")
    assert oval_shape == "ellipse"
    assert oval_bg == (255, 255, 255, 245)
    assert oval_txt == (15, 15, 15)

    rect_bg, rect_txt, rect_shape, rect_r = get_bubble_styling("rectangle")
    assert rect_shape == "rounded_rect"
    assert rect_r == 4


def test_calculate_bubble_padding():
    pad_x, pad_y, inner_w, inner_h = calculate_bubble_padding("oval", 100, 100)
    assert pad_x >= 2
    assert pad_y >= 2
    assert inner_w == 100 - 2 * pad_x
    assert inner_h == 100 - 2 * pad_y

    # Rectangular bubble
    rpad_x, rpad_y, rinner_w, rinner_h = calculate_bubble_padding("rect", 100, 100)
    assert rpad_x >= 2
    assert rpad_y >= 2
    assert rinner_w == 100 - 2 * rpad_x


def test_fit_comic_text_empty(qapp):
    pt, lines, l_sp, w_sp, lh, th = fit_comic_text("", 100, 100)
    assert lines == []
    assert th == 0


def test_qt_comic_renderer_renders_bubbles(qapp):
    pixmap = QPixmap(200, 200)
    pixmap.fill()
    painter = QPainter(pixmap)

    renderer = QtComicTextRenderer()

    bubble = BubbleBlock(
        id="b1",
        bbox=(20, 20, 80, 60),
        text_ja="テスト",
        text_en="Testing",
        shape="oval"
    )
    manual_bubble = BubbleBlock(
        id="b2",
        bbox=(120, 20, 60, 60),
        text_ja="",
        is_manual=True
    )
    page = PageTranslation("p1.png", 200, 200, [bubble, manual_bubble])
    translations = {"b1": "Testing"}

    try:
        renderer.render(
            painter=painter,
            page=page,
            translations=translations,
            scale_factor=1.0,
            offset=(0, 0),
            orig_size=(200, 200),
            scaled_size=(200, 200)
        )
    finally:
        painter.end()

    assert not pixmap.isNull()
