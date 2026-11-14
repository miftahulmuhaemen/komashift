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
    worker.wait()

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
    worker.wait()

    success, msg = blocker.args
    assert success is True
    assert mock_detect.call_count == 1
    assert mock_detect.call_args[0][0] == img2

def test_worker_discards_stale_empty_cache(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini"
    )

    # Pre-populate empty cache (0 bubbles) from a previous broken run
    page1 = PageTranslation("01.png", 400, 600, [])
    worker.workspace.save_page_ocr(page1)

    mock_detect = MagicMock(return_value=PageTranslation("01.png", 400, 600, [BubbleBlock("p1_b1", (0, 0, 10, 10), "テスト", "Test")]))
    worker.detector.detect_page = mock_detect

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, msg = blocker.args
    assert success is True
    # Detector must have been called because empty cache was discarded
    assert mock_detect.call_count == 1


def test_worker_multimodal_pipeline(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    img2 = tmp_path / "02.png"
    _create_dummy_image(img1)
    _create_dummy_image(img2)

    detector = MagicMock()
    detector.detect_page = MagicMock(side_effect=[
        PageTranslation("01.png", 400, 600, [BubbleBlock("p1_b1", (10, 10, 50, 50), "こんにちは")]),
        PageTranslation("02.png", 400, 600, [BubbleBlock("p2_b1", (20, 20, 60, 60), "さようなら")])
    ])

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1, img2],
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gemini-2.5-flash",
        detector=detector,
        engine_mode="multimodal",
        vision_scale_pct=50,
        vision_quality=75
    )

    # In Visual Hybrid mode, detector detects exact bubble geometry
    assert worker.detector is not None

    # Mock translate_page_visual_hybrid
    mock_visual = MagicMock(side_effect=[
        {"p1_b1": "Hello"},
        {"p2_b1": "Goodbye"}
    ])
    worker.translator.translate_page_visual_hybrid = mock_visual

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, msg = blocker.args
    assert success is True
    assert detector.detect_page.call_count == 2
    assert mock_visual.call_count == 2

    # Check that OCR cache and translations are saved in workspace
    assert worker.workspace.is_translation_complete() is True
    ocr_res = worker.workspace.load_ocr_results()
    assert "01.png" in ocr_res
    assert "02.png" in ocr_res

    trans = worker.workspace.load_translations()
    assert trans["p1_b1"] == "Hello"
    assert trans["p2_b1"] == "Goodbye"


def test_worker_rasterize_job(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    img2 = tmp_path / "02.png"
    _create_dummy_image(img1)
    _create_dummy_image(img2)

    out_dir = tmp_path.parent / f"{tmp_path.name}_translated"

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="",
        job_type="rasterize",
        output_dir=out_dir
    )

    # Save mock OCR and translation in workspace
    page1 = PageTranslation("01.png", 400, 600, [BubbleBlock("p1_b1", (10, 10, 50, 50), "こんにちは")])
    worker.workspace.save_page_ocr(page1)
    worker.workspace.save_translations({"p1_b1": "Hello World"}, target_lang="en")

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, msg = blocker.args
    assert success is True
    assert (out_dir / "01.png").exists()
    assert not (out_dir / "02.png").exists()  # 02 was not selected


def test_worker_translates_manual_bubble_with_context(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    # Pre-populate page with an existing translated bubble and a raw manual box (no OCR yet)
    b1 = BubbleBlock("p1_b1", (10, 10, 40, 40), "もしもし", text_en="Hello", is_manual=False)
    b2 = BubbleBlock("p1_b2", (50, 50, 80, 80), "", text_en="", is_manual=True)
    page1 = PageTranslation("01.png", 400, 600, [b1, b2])

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gemini-2.5-flash",
        engine_mode="multimodal"
    )
    worker.workspace.save_page_ocr(page1)
    worker.workspace.save_translations({"p1_b1": "Hello"})

    # Mock detector to extract Japanese text in background
    mock_manual_region = MagicMock(return_value=("當然不行!", (50, 50, 80, 80), (90, 90), "oval"))
    worker.detector.detect_and_ocr_manual_region = mock_manual_region

    mock_context_translate = MagicMock(return_value="Of course not!")
    mock_visual_translate = MagicMock()
    worker.translator.translate_single_text_with_context = mock_context_translate
    worker.translator.translate_page_visual_hybrid = mock_visual_translate

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, msg = blocker.args
    assert success is True
    # Background worker performed local OCR on the manual box crop
    assert mock_manual_region.call_count == 1

    # Contextual single text translation was called with extracted text
    assert mock_context_translate.call_count == 1
    call_kwargs = mock_context_translate.call_args.kwargs
    assert call_kwargs["text_ja"] == "當然不行!"
    assert call_kwargs["target_lang"] == "en"

    # Full page visual re-translation was skipped because all non-manual bubbles were already translated
    assert mock_visual_translate.call_count == 0

    # Workspace now has both translations
    trans = worker.workspace.load_translations("en")
    assert trans["p1_b1"] == "Hello"
    assert trans["p1_b2"] == "Of course not!"
    assert worker.workspace.is_translation_complete("en", [img1]) is True


def test_worker_translates_manual_bubble_standard_hybrid_mode(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    # Page has an existing translated bubble and an untranslated manual box
    b1 = BubbleBlock("p1_b1", (10, 10, 40, 40), "もしもし", text_en="Hello", is_manual=False)
    b2 = BubbleBlock("p1_m_12345678", (50, 50, 80, 80), "", text_en="", is_manual=True)
    page1 = PageTranslation("01.png", 400, 600, [b1, b2])

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        engine_mode="hybrid"
    )
    worker.workspace.save_page_ocr(page1)
    worker.workspace.save_translations({"p1_b1": "Hello"})

    mock_manual_region = MagicMock(return_value=("テスト", (50, 50, 80, 80), (90, 90), "oval"))
    worker.detector.detect_and_ocr_manual_region = mock_manual_region

    mock_context_translate = MagicMock(return_value="Test")
    worker.translator.translate_single_text_with_context = mock_context_translate
    mock_chapter_translate = MagicMock()
    worker.translator.translate_chapter = mock_chapter_translate

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, msg = blocker.args
    assert success is True
    # Background worker performed local OCR on the manual box crop
    assert mock_manual_region.call_count == 1
    # Translated with context
    assert mock_context_translate.call_count == 1
    # Regular chapter batch was not needed because b1 was already translated
    assert mock_chapter_translate.call_count == 0

    trans = worker.workspace.load_translations("en")
    assert trans["p1_b1"] == "Hello"
    assert trans["p1_m_12345678"] == "Test"
    assert worker.workspace.is_translation_complete("en", [img1]) is True


def test_worker_multimodal_retry_and_downscale(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    detector = MangaOcrDetector()
    detector.detect_page = MagicMock(return_value=PageTranslation(
        "01.png", 400, 600, [BubbleBlock("p1_b1", (10, 10, 50, 50), "助けて")]
    ))

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        base_url="https://api.openai.com/v1",
        model="gemini-2.5-flash",
        detector=detector,
        engine_mode="multimodal",
        vision_scale_pct=75,
        max_retries=3,
        timeout=100.0
    )

    calls = []
    def fake_translate_visual(img_path, page_data, target_lang="en", scale_pct=75, quality=75, timeout=None):
        calls.append({"scale": scale_pct, "timeout": timeout})
        if len(calls) == 1:
            raise Exception("HTTP Error 524: Cloudflare Timeout")
        return {"p1_b1": "Help!"}

    worker.translator.translate_page_visual_hybrid = fake_translate_visual

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, msg = blocker.args
    assert success is True
    # Attempt 1 failed with 524, attempt 2 succeeded
    assert len(calls) == 2
    assert calls[0]["scale"] == 75
    assert calls[0]["timeout"] == 100.0
    # Attempt 2 downscaled to reduce vision tokens and increased timeout (+60s)
    assert calls[1]["scale"] == 55
    assert calls[1]["timeout"] == 160.0

    trans = worker.workspace.load_translations("en")
    assert trans["p1_b1"] == "Help!"


def test_worker_dependency_injection(tmp_path: Path):
    dummy_detector = MagicMock()
    dummy_provider = MagicMock()
    dummy_repo = MagicMock()
    dummy_sink = MagicMock()

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[],
        detector=dummy_detector,
        provider=dummy_provider,
        repository=dummy_repo,
        log_sink=dummy_sink,
    )

    assert worker.detector is dummy_detector
    assert worker.translator is dummy_provider
    assert worker.workspace is dummy_repo


def test_worker_interruption_cancels_gracefully(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    dummy_detector = MagicMock()
    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        detector=dummy_detector,
    )

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
        worker.requestInterruption()
    worker.wait()

    success, msg = blocker.args
    assert success is False
    assert "Cancelled" in msg


def test_worker_passes_custom_ocr_and_acceleration_settings(tmp_path: Path):
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        manga_ocr_model="custom/ocr-model",
        onnx_force_cpu=True
    )

    assert worker.manga_ocr_model == "custom/ocr-model"
    assert worker.onnx_force_cpu is True
    assert worker.detector.ocr_model_path == "custom/ocr-model"
    assert worker.detector.force_cpu is True
    assert worker.detector._onnx_detector.force_cpu is True


def test_worker_handles_bubble_model_download_failure(tmp_path: Path, qtbot):
    from unittest.mock import patch
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    detector = MangaOcrDetector()
    detector.is_bubble_detector_available = MagicMock(return_value=False)

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        detector=detector,
        engine_mode="hybrid"
    )

    with patch("src.services.ai_assets_manager.AiAssetsManager.download_comic_model", side_effect=RuntimeError("Network timeout")):
        with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
            worker.start()
        worker.wait()

    success, msg = blocker.args
    assert success is False
    assert "Network timeout" in msg


def test_worker_auto_downloads_missing_bubble_model(tmp_path: Path, qtbot):
    from unittest.mock import patch
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    fake_model_file = tmp_path / "comic-text-detector.onnx"
    fake_model_file.write_text("dummy")

    detector = MangaOcrDetector()
    # Initially missing
    detector.is_bubble_detector_available = MagicMock(return_value=False)

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        detector=detector,
        engine_mode="hybrid"
    )
    # Stub workspace and translator so it completes
    worker.workspace.is_translation_complete = MagicMock(return_value=True)

    with patch("src.services.ai_assets_manager.AiAssetsManager.download_comic_model", return_value=fake_model_file) as mock_dl:
        with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
            worker.start()
        worker.wait()

    assert mock_dl.called
    success, msg = blocker.args
    assert success is True


def test_worker_multimodal_discards_stale_empty_cache(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        engine_mode="multimodal",
        vision_scale_pct=50,
        vision_quality=75
    )

    # Pre-populate empty cache (0 bubbles) from a previous broken run
    page1 = PageTranslation("01.png", 400, 600, [])
    worker.workspace.save_page_ocr(page1)
    assert len(worker.workspace.load_ocr_results()) == 1

    # Mock detector and translator
    mock_detect = MagicMock(return_value=PageTranslation("01.png", 400, 600, [BubbleBlock("p1_b1", (10, 10, 50, 50), "こんにちは")]))
    worker.detector.detect_page = mock_detect
    worker.translator.translate_page_visual_hybrid = MagicMock(return_value={"p1_b1": "Hello"})

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, msg = blocker.args
    assert success is True
    # Verify that detect_page was called because stale 0-bubble cache was purged
    assert mock_detect.call_count == 1
    assert worker.workspace.is_translation_complete() is True


def test_worker_two_pass_multimodal_perception(tmp_path: Path, qtbot):
    img1 = tmp_path / "01.png"
    _create_dummy_image(img1)

    worker = TranslationWorker(
        folder_path=tmp_path,
        image_paths=[img1],
        api_key="mock-key",
        engine_mode="multimodal"
    )

    # 1. Bubble detection returns bubble with empty text (geometry only)
    mock_detect = MagicMock(return_value=PageTranslation("01.png", 800, 1200, [BubbleBlock("p1_b1", (10, 10, 50, 50), "")]))
    worker.detector.detect_page = mock_detect

    # 2. Pass 1: Visual perception extracts text_ja + stage metadata
    mock_perceive = MagicMock(return_value={
        "p1_b1": {
            "text_ja": "待って！",
            "speaker": "Heroine",
            "expression": "Desperate",
            "speech_type": "Spoken dialogue"
        }
    })
    worker.translator.perceive_page_visual_context = mock_perceive

    # 3. Pass 2: Chapter translation receives visual context and returns translation
    mock_translate_chapter = MagicMock(return_value={"p1_b1": "Wait!"})
    worker.translator.translate_chapter = mock_translate_chapter

    with qtbot.waitSignal(worker.translation_finished, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, msg = blocker.args
    assert success is True
    assert mock_perceive.call_count == 1
    assert mock_translate_chapter.call_count == 1

    # Verify translations and enriched OCR results
    trans = worker.workspace.load_translations()
    assert trans["p1_b1"] == "Wait!"

    ocr_res = worker.workspace.load_ocr_results()
    assert ocr_res["01.png"].bubbles[0].speaker == "Heroine"
    assert ocr_res["01.png"].bubbles[0].expression == "Desperate"









