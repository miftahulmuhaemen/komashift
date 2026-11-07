from unittest.mock import MagicMock
from pathlib import Path
from PIL import Image, ImageDraw
from src.models.translation_item import PageTranslation
from src.services.manga_ocr_detector import MangaOcrDetector


def test_manga_ocr_detection_local(tmp_path: Path):
    img_path = tmp_path / "01.png"
    img = Image.new("RGB", (600, 800), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([110, 110, 140, 200], fill="black")
    draw.rectangle([310, 210, 350, 300], fill="black")
    img.save(img_path)

    detector = MangaOcrDetector()

    # Mock ONNX detector returning 2 boxes
    detector._onnx_detector.is_available = MagicMock(return_value=True)
    detector._onnx_detector.detect_bubbles = MagicMock(return_value=[
        (100, 100, 50, 150),
        (300, 200, 60, 120),
    ])

    # Mock local manga_ocr engine returning text
    mock_engine = MagicMock(side_effect=["こんにちは", "世界"])
    detector._engine = mock_engine

    page = detector.detect_page(img_path, page_index=1)
    assert isinstance(page, PageTranslation)
    assert len(page.bubbles) == 2

    assert page.bubbles[0].id == "p1_b1"
    assert page.bubbles[0].bbox == (100, 100, 50, 150)
    assert page.bubbles[0].text_ja == "こんにちは"
    assert page.bubbles[0].text_en == ""

    assert page.bubbles[1].id == "p1_b2"
    assert page.bubbles[1].bbox == (300, 200, 60, 120)
    assert page.bubbles[1].text_ja == "世界"


def test_manga_ocr_detection_skips_blank_crop(tmp_path: Path):
    img_path = tmp_path / "blank_test.png"
    img = Image.new("RGB", (600, 800), color="white")
    draw = ImageDraw.Draw(img)
    # Only box 1 has content
    draw.rectangle([110, 110, 140, 200], fill="black")
    # Box 2 remains pure blank white
    img.save(img_path)

    detector = MangaOcrDetector(min_variance=6.0)
    detector._onnx_detector.is_available = MagicMock(return_value=True)
    detector._onnx_detector.detect_bubbles = MagicMock(return_value=[
        (100, 100, 50, 150),  # has content
        (300, 200, 60, 120),  # blank white
    ])

    mock_engine = MagicMock(return_value="テスト")
    detector._engine = mock_engine

    page = detector.detect_page(img_path, page_index=1)
    # Only 1 bubble should be created; the blank box is skipped
    assert len(page.bubbles) == 1
    assert page.bubbles[0].id == "p1_b1"
    assert page.bubbles[0].text_ja == "テスト"
    # Ensure OCR engine was only called once, avoiding transformer execution on the blank box
    assert mock_engine.call_count == 1


def test_manga_ocr_detection_no_bubbles(tmp_path: Path):
    img_path = tmp_path / "02.png"
    Image.new("RGB", (500, 500), color="white").save(img_path)

    detector = MangaOcrDetector()
    detector._onnx_detector.is_available = MagicMock(return_value=True)
    detector._onnx_detector.detect_bubbles = MagicMock(return_value=[])

    page = detector.detect_page(img_path, page_index=2)
    assert len(page.bubbles) == 0


def test_manga_ocr_detection_prescaling(tmp_path: Path):
    # 2400x3200 oversized image -> max_dim > 1600 -> scale is 0.5
    img_path = tmp_path / "oversized.png"
    img = Image.new("RGB", (2400, 3200), color="white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 100, 140, 200], fill="black")
    img.save(img_path)

    detector = MangaOcrDetector()
    detector._onnx_detector.is_available = MagicMock(return_value=True)

    # Return a bounding box in scaled 0.5x space
    detector._onnx_detector.detect_bubbles = MagicMock(return_value=[
        (50, 50, 25, 75)
    ])
    mock_engine = MagicMock(return_value="テスト")
    detector._engine = mock_engine

    page = detector.detect_page(img_path, page_index=1)
    assert page.page_width == 2400
    assert page.page_height == 3200
    assert len(page.bubbles) == 1

    # Bounding box must be scaled back to native original coordinates (2x)
    bx, by, bw, bh = page.bubbles[0].bbox
    assert abs(bx - 100) <= 2
    assert abs(by - 100) <= 2
    assert abs(bw - 50) <= 2
    assert abs(bh - 150) <= 2

