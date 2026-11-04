from pathlib import Path
from src.models.translation_item import BubbleBlock, PageTranslation
from src.services.translation_workspace import TranslationWorkspace

def test_translation_workspace_lifecycle(tmp_path: Path):
    ws = TranslationWorkspace(tmp_path)
    temp_dir = ws.get_temp_dir()
    assert temp_dir.exists()
    assert temp_dir == tmp_path / "temp"

    bubble = BubbleBlock(id="p1_b1", bbox=(10, 20, 100, 200), text_ja="こんにちは")
    page = PageTranslation(page_filename="01.png", page_width=1000, page_height=1400, bubbles=[bubble])
    ws.save_page_ocr(page)

    loaded = ws.load_ocr_results()
    assert "01.png" in loaded
    assert loaded["01.png"].page_width == 1000
    assert loaded["01.png"].bubbles[0].id == "p1_b1"
    assert loaded["01.png"].bubbles[0].text_ja == "こんにちは"
    assert loaded["01.png"].bubbles[0].bbox == (10, 20, 100, 200)

    # Save translation
    ws.save_translations({"p1_b1": "Hello"})
    trans = ws.load_translations()
    assert trans["p1_b1"] == "Hello"
    assert ws.is_translation_complete() is True

def test_workspace_incremental_ocr(tmp_path: Path):
    ws = TranslationWorkspace(tmp_path)
    page1 = PageTranslation("01.png", 800, 1200, [BubbleBlock("p1_b1", (0, 0, 50, 50), "一")])
    page2 = PageTranslation("02.png", 800, 1200, [BubbleBlock("p2_b1", (0, 0, 50, 50), "二")])

    ws.save_page_ocr(page1)
    assert ws.is_ocr_complete(total_pages=2) is False

    ws.save_page_ocr(page2)
    assert ws.is_ocr_complete(total_pages=2) is True

    loaded = ws.load_ocr_results()
    assert len(loaded) == 2
    assert "01.png" in loaded and "02.png" in loaded

def test_workspace_logging(tmp_path: Path):
    ws = TranslationWorkspace(tmp_path)
    ws.append_log("Starting OCR")
    log_file = ws.get_temp_dir() / "translation.log"
    assert log_file.exists()
    assert "Starting OCR" in log_file.read_text(encoding="utf-8")
