import pytest
from pathlib import Path
from PIL import Image
from PyQt6.QtGui import QPixmap, QImage
from src.services.thumbnail_cache import create_thumbnail_pixmap, create_thumbnail_image, ThumbnailCache

def test_create_thumbnail_image(tmp_path: Path):
    img_path = tmp_path / "test_img.png"
    img = Image.new("RGBA", (200, 100), color="red")
    img.save(img_path)

    qimg = create_thumbnail_image(img_path, (50, 50))
    assert qimg is not None
    assert isinstance(qimg, QImage)
    assert qimg.width() <= 50
    assert qimg.height() <= 50

def test_create_thumbnail_pixmap(tmp_path: Path, qapp):
    img_path = tmp_path / "test.png"
    img = Image.new("RGB", (200, 200), color="blue")
    img.save(img_path)

    pixmap = create_thumbnail_pixmap(img_path, (64, 64))
    assert pixmap is not None
    assert isinstance(pixmap, QPixmap)
    assert pixmap.width() <= 64
    assert pixmap.height() <= 64

def test_thumbnail_cache_load_async(tmp_path: Path, qtbot):
    img_path = tmp_path / "test_async.png"
    img = Image.new("RGB", (100, 100), color="green")
    img.save(img_path)

    cache = ThumbnailCache()
    loaded_results = []

    def on_loaded(path_str: str, pixmap: QPixmap):
        loaded_results.append((path_str, pixmap))

    cache.load_async(img_path, (64, 64), on_loaded)

    qtbot.waitUntil(lambda: len(loaded_results) == 1, timeout=2000)
    assert loaded_results[0][0] == str(img_path)
    assert isinstance(loaded_results[0][1], QPixmap)

    # Test cache hit
    hit_results = []
    cache.load_async(img_path, (64, 64), lambda p, px: hit_results.append(px))
    assert len(hit_results) == 1
    cache.thread_pool.waitForDone(2000)


def test_thumbnail_strip_widget_and_delegate(tmp_path: Path, qtbot):
    from src.ui.thumbnail_strip import ThumbnailStripWidget, ThumbnailDelegate
    from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QStyleOptionViewItem
    from PyQt6.QtCore import QSize, QRect
    from PyQt6.QtGui import QPainter, QImage

    img1 = tmp_path / "01.png"
    img2 = tmp_path / "02.png"
    Image.new("RGB", (50, 50), color="red").save(img1)
    Image.new("RGB", (50, 50), color="blue").save(img2)

    cache = ThumbnailCache()
    strip = ThumbnailStripWidget(cache)
    qtbot.addWidget(strip)

    strip.set_images([img1, img2])
    assert strip.list_widget.count() == 2
    assert strip.get_current_index() == 0
    assert strip.get_current_image() == img1

    # Check tooltip format with page position
    assert "01.png (1/2)" in strip.list_widget.item(0).toolTip()
    assert "02.png (2/2)" in strip.list_widget.item(1).toolTip()

    # Test delegate sizeHint and painting
    delegate = strip.list_widget.itemDelegate()
    assert isinstance(delegate, ThumbnailDelegate)
    opt = QStyleOptionViewItem()
    idx = strip.list_widget.model().index(0, 0)
    assert delegate.sizeHint(opt, idx) == QSize(108, 118)

    # Render widget offscreen to verify delegate paint execution
    test_img = QImage(300, 120, QImage.Format.Format_ARGB32)
    p = QPainter(test_img)
    strip.render(p)
    p.end()

    # Move selection
    strip.select_next()
    assert strip.get_current_index() == 1
    assert strip.get_current_image() == img2

