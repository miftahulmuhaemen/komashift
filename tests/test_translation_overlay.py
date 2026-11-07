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
