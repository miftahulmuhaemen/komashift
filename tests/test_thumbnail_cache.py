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

