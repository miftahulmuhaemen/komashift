from unittest.mock import MagicMock, patch
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


def test_manga_ocr_segment_bubble_obstacle_masking():
    # Verify that passing neighboring bubbles as obstacles prevents floodfill from spilling across bounds
    img = Image.new("L", (200, 300), color=255)
    detector = MangaOcrDetector()

    b1 = (50, 40, 80, 80)
    b2 = (50, 140, 80, 80)

    # Segmenting b1 with b2 as obstacle should not expand down into b2's region
    exp_b1, _, _ = detector.segment_bubble(img, b1, other_bboxes=[b2])
    # The bottom of b1's expanded rect should be constrained
    assert exp_b1[1] + exp_b1[3] <= b2[1] + 15


def test_manga_ocr_overlap_resolution(tmp_path: Path):
    img_path = tmp_path / "overlap_page.png"
    img = Image.new("RGB", (600, 800), color="white")
    draw = ImageDraw.Draw(img)
    # Box 1 (upper)
    draw.rectangle([110, 110, 150, 180], fill="black")
    # Box 2 (lower, vertically adjacent)
    draw.rectangle([110, 200, 150, 270], fill="black")
    img.save(img_path)

    detector = MangaOcrDetector()
    detector._onnx_detector.is_available = MagicMock(return_value=True)
    detector._onnx_detector.detect_bubbles = MagicMock(return_value=[
        (100, 100, 60, 90),
        (100, 195, 60, 90),
    ])
    mock_engine = MagicMock(side_effect=["Top text", "Bottom text"])
    detector._engine = mock_engine

    page = detector.detect_page(img_path, page_index=1)
    assert len(page.bubbles) == 2
    b1_exp = page.bubbles[0].expanded_bbox
    b2_exp = page.bubbles[1].expanded_bbox

    # Neither expanded box should significantly occlude or swallow the other
    assert b1_exp[1] + b1_exp[3] <= b2_exp[1] + 10


def test_manga_ocr_detector_custom_model_and_acceleration():
    # 1. Custom model and force_cpu = True
    detector_custom = MangaOcrDetector(
        ocr_model_path="custom/hf-repo-id",
        force_cpu=True
    )
    assert detector_custom.ocr_model_path == "custom/hf-repo-id"
    assert detector_custom.force_cpu is True
    assert detector_custom._onnx_detector.force_cpu is True

    with patch("manga_ocr.MangaOcr") as mock_mocr:
        detector_custom._init_engine()
        assert mock_mocr.call_count == 1
        _, kwargs = mock_mocr.call_args
        assert kwargs["pretrained_model_name_or_path"] == "custom/hf-repo-id"
        assert kwargs["force_cpu"] is True

    # 2. Default model with GPU auto-detect (force_cpu = False)
    detector_default = MangaOcrDetector(
        ocr_model_path="",
        force_cpu=False
    )
    assert detector_default.ocr_model_path == ""
    assert detector_default.force_cpu is False
    assert detector_default._onnx_detector.force_cpu is False

    with patch("manga_ocr.MangaOcr") as mock_mocr_def:
        detector_default._init_engine()
        assert mock_mocr_def.call_count == 1
        _, kwargs_def = mock_mocr_def.call_args
        assert "pretrained_model_name_or_path" not in kwargs_def
        assert kwargs_def["force_cpu"] is False


