from pathlib import Path
from unittest.mock import MagicMock
from PIL import Image
from PyQt6.QtCore import QThread
from src.models.translation_item import PageTranslation, BubbleBlock
from src.services.translation_worker import TranslationWorker
from src.services.manga_ocr_detector import MangaOcrDetector

def _create_dummy_image(path: Path):
    img = Image.new("RGB", (400, 600), color="white")
    img.save(path)

def test_worker_full_pipeline(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    img2 = tmp_path / "02.png"
    _create_dummy_image(img1)
    _create_dummy_image(img2)

    detector = MangaOcrDetector()
    # Mock detector to return 1 bubble per page
    detector.detect_page = MagicMock(side_effect=[
        PageTranslation("01.png", 400, 600, [BubbleBlock("p1_b1", (10, 10, 50, 50), "こんにちは")]),
        PageTranslation("02.png", 400, 600, [BubbleBlock("p2_b1", (10, 10, 50, 50), "さようなら")])
    ])

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1, img2],
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        detector=detector
    )

    # Mock translator
    worker.translator.translate_chapter = MagicMock(return_value={
        "p1_b1": "Hello",
        "p2_b1": "Goodbye"
    })

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()

    success, msg = blocker.args
    assert success is True
    assert worker.workspace.is_translation_complete() is True
    trans = worker.workspace.load_translations()
    assert trans["p1_b1"] == "Hello"
    assert trans["p2_b1"] == "Goodbye"

def test_worker_resumes_from_existing_ocr(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    img2 = tmp_path / "02.png"
    _create_dummy_image(img1)
    _create_dummy_image(img2)

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1, img2],
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini"
    )

    # Pre-populate page 1 in workspace
    page1 = PageTranslation("01.png", 400, 600, [BubbleBlock("p1_b1", (10, 10, 50, 50), "既にスキャン済み")])
    worker.workspace.save_page_ocr(page1)

    # Detector mock should only be called once (for page 2)
    mock_detect = MagicMock(return_value=PageTranslation("02.png", 400, 600, [BubbleBlock("p2_b1", (20, 20, 50, 50), "新しい")]))
    worker.detector.detect_page = mock_detect
    worker.translator.translate_chapter = MagicMock(return_value={"p1_b1": "Already scanned", "p2_b1": "New"})

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()

    success, msg = blocker.args
    assert success is True
    assert mock_detect.call_count == 1
    assert mock_detect.call_args[0][0] == img2
