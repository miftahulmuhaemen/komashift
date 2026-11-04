from PyQt6.QtCore import QSize, QRect
from src.models.translation_item import BubbleBlock, PageTranslation
from src.ui.translation_overlay import calculate_scaled_rect, TranslationOverlayWidget

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
