from PyQt6.QtCore import QSize, QRect, QPoint
from PyQt6.QtGui import QFont, QFontMetrics
from src.models.translation_item import BubbleBlock, PageTranslation
from src.ui.translation_overlay import (
    calculate_scaled_rect,
    calculate_popup_rect,
    TranslationOverlayWidget
)


def test_calculate_scaled_rect_no_offset():
    orig_size = QSize(1000, 2000)
    scaled_size = QSize(500, 1000)
    bbox = (100, 200, 300, 400)
    rect = calculate_scaled_rect(bbox, orig_size, scaled_size, offset=(0, 0))
    assert rect == QRect(50, 100, 150, 200)


def test_calculate_scaled_rect_with_offset():
    orig_size = QSize(1000, 2000)
    scaled_size = QSize(500, 1000)
    bbox = (100, 200, 300, 400)
    rect = calculate_scaled_rect(bbox, orig_size, scaled_size, offset=(100, 50))
    assert rect == QRect(150, 150, 150, 200)


def test_calculate_popup_rect_centering(qapp):
    font = QFont("Sans-Serif", 11)
    fm = QFontMetrics(font)
    center = QPoint(500, 500)
    container_size = QSize(1000, 1000)

    rect = calculate_popup_rect(center, "Short text", fm, container_size)
    assert rect.isValid()
    # Should be centered around (500, 500) within 1-2px due to integer rounding
    assert abs(rect.center().x() - 500) <= 2
    assert abs(rect.center().y() - 500) <= 2


def test_calculate_popup_rect_clamping(qapp):
    font = QFont("Sans-Serif", 11)
    fm = QFontMetrics(font)
    # Point at top-left corner
    top_left_center = QPoint(10, 10)
    container_size = QSize(800, 600)

    rect = calculate_popup_rect(top_left_center, "Edge testing text", fm, container_size)
    assert rect.x() >= 8
    assert rect.y() >= 8

    # Point at bottom-right corner
    bottom_right_center = QPoint(795, 595)
    rect2 = calculate_popup_rect(bottom_right_center, "Edge testing text", fm, container_size)
    assert rect2.right() <= 800 - 8
    assert rect2.bottom() <= 600 - 8


def test_overlay_widget_data(qtbot):
    overlay = TranslationOverlayWidget()
    qtbot.addWidget(overlay)

    bubble = BubbleBlock("p1_b1", (50, 50, 100, 100), "テスト")
    page = PageTranslation("01.png", 500, 500, [bubble])
    translations = {"p1_b1": "Test Translation"}

    overlay.set_data(
        page=page,
        translations=translations,
        orig_size=QSize(500, 500),
        scaled_size=QSize(500, 500),
        offset=(0, 0)
    )

    assert overlay.is_overlay_enabled() is True
    overlay.toggle_visibility()
    assert overlay.is_overlay_enabled() is False


def test_overlay_hit_testing(qtbot):
    overlay = TranslationOverlayWidget()
    qtbot.addWidget(overlay)
    overlay.resize(600, 600)

    bubble = BubbleBlock("p1_b1", (100, 100, 80, 80), "こんにちは")
    page = PageTranslation("01.png", 600, 600, [bubble])
    translations = {"p1_b1": "Hello there"}

    overlay.set_data(
        page=page,
        translations=translations,
        orig_size=QSize(600, 600),
        scaled_size=QSize(600, 600),
        offset=(0, 0)
    )

    # Point inside the bubble
    assert overlay._hit_test(QPoint(120, 120)) == "p1_b1"

    # Point outside the bubble
    assert overlay._hit_test(QPoint(10, 10)) is None

    # Sticky popup test: simulate active popup
    overlay._hovered_bubble_id = "p1_b1"
    overlay._current_popup_rect = QRect(200, 200, 150, 60)

    # Cursor is outside original bubble bbox (100..180) but inside popup card (200..350)
    assert overlay._hit_test(QPoint(250, 220)) == "p1_b1"


def test_split_word_to_fit(qapp):
    from src.ui.translation_overlay import split_word_to_fit, get_comic_font_family, get_hyphenator
    font = QFont(get_comic_font_family(), 10)
    font.setWeight(QFont.Weight.Bold)
    fm = QFontMetrics(font)
    dic = get_hyphenator()

    # Normal short word fits without splitting
    chunks = split_word_to_fit("hello", fm, 100, dic)
    assert chunks == ["hello"]

    # Long word in narrow width must be split into chunks <= max_w
    chunks = split_word_to_fit("embarrassment", fm, 45, dic)
    assert len(chunks) > 1
    for chunk in chunks:
        assert fm.horizontalAdvance(chunk) <= 45


def test_wrap_words_to_width(qapp):
    from src.ui.translation_overlay import wrap_words_to_width, get_comic_font_family, get_hyphenator
    font = QFont(get_comic_font_family(), 10)
    font.setWeight(QFont.Weight.Bold)
    fm = QFontMetrics(font)
    dic = get_hyphenator()

    text = "This is a sentence with multiple words that must wrap cleanly inside narrow bounds."
    words = text.split()
    max_w = 60
    lines = wrap_words_to_width(words, fm, max_w, dic)
    assert len(lines) > 1
    for line in lines:
        assert fm.horizontalAdvance(line) <= max_w


def test_fit_comic_text_narrow_bubble_never_returns_single_line(qapp):
    from src.ui.translation_overlay import fit_comic_text
    sentence = (
        "Personally, I think the braids in the first half gave off a completely "
        "different vibe from before, and had a lot of charm."
    )
    # Test in narrow bubble
    pt, lines, l_sp, w_sp, lh, total_h = fit_comic_text(sentence, inner_w=50, inner_h=200)
    assert len(lines) > 1
    assert pt >= 6

    # Test sentence with long words like embarrassment
    sentence2 = (
        "Compared to yellow, it is a completely different kind of embarrassment "
        "simply because I do not know how to wear it."
    )
    pt2, lines2, _, _, _, _ = fit_comic_text(sentence2, inner_w=65, inner_h=250)
    assert len(lines2) > 1
    assert pt2 >= 6


def test_fit_comic_text_severe_overflow_still_wraps(qapp):
    from src.ui.translation_overlay import fit_comic_text
    sentence = "Very long sentence that exceeds the small bubble vertical height completely."
    # Extremely small height forces fallback path
    pt, lines, _, _, _, total_h = fit_comic_text(sentence, inner_w=40, inner_h=15)
    # Must STILL wrap to inner_w and NOT return [text]
    assert len(lines) > 1
    assert pt >= 6


def test_overlay_manual_box_selection(qtbot):
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import Qt, QPointF

    overlay = TranslationOverlayWidget()
    qtbot.addWidget(overlay)
    overlay.resize(800, 1000)

    # Set coordinate mapping (scaled 800x1000 to native 1600x2000)
    overlay.set_data(
        page=None,
        translations={},
        orig_size=QSize(1600, 2000),
        scaled_size=QSize(800, 1000),
        offset=(0, 0)
    )

    boxes_created = []
    overlay.manual_box_created.connect(lambda b: boxes_created.append(b))

    # In disabled mode, dragging produces no event
    assert overlay.is_manual_box_mode() is False

    # Enable manual box mode
    overlay.set_manual_box_mode(True)
    assert overlay.is_manual_box_mode() is True

    # Simulate mouse drag from (100, 100) to (200, 300)
    press_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(100, 100),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    overlay.mousePressEvent(press_event)
    assert overlay._drag_start == QPoint(100, 100)

    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPointF(200, 300),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    overlay.mouseMoveEvent(move_event)
    assert overlay._drag_current == QPoint(200, 300)

    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPointF(200, 300),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier
    )
    overlay.mouseReleaseEvent(release_event)

    # Should map 100..200 (w=100) -> orig_x=200, orig_w=200; 100..300 (h=200) -> orig_y=200, orig_h=400
    assert len(boxes_created) == 1
    orig_x, orig_y, orig_w, orig_h = boxes_created[0]
    assert orig_x == 200
    assert orig_y == 200
    assert orig_w == 200
    assert orig_h == 400
