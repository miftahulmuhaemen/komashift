from pathlib import Path
from src.models.translation_item import BubbleBlock, PageTranslation
from src.ports.page_repository import PageRepository, ChapterStatus
from src.infra.json_workspace import JsonTempWorkspace

def test_translation_workspace_lifecycle(tmp_path: Path):
    ws: PageRepository = JsonTempWorkspace(tmp_path)
    temp_dir = ws.get_temp_dir()
    assert temp_dir.exists()
    assert temp_dir == tmp_path / "temp"

    bubble = BubbleBlock(id="p1_b1", bbox=(10, 20, 100, 200), text_ja="こんにちは")
    page = PageTranslation(page_filename="01.png", page_width=1000, page_height=1400, bubbles=[bubble])
    ws.save_page(page)

    loaded = ws.load_pages()
    assert "01.png" in loaded
    assert loaded["01.png"].page_width == 1000
    assert loaded["01.png"].bubbles[0].id == "p1_b1"
    assert loaded["01.png"].bubbles[0].text_ja == "こんにちは"
    assert loaded["01.png"].bubbles[0].bbox == (10, 20, 100, 200)

    # Save translation
    ws.save_translations({"p1_b1": "Hello"})
    trans = ws.load_translations()
    assert trans["p1_b1"] == "Hello"
    
    st = ws.status("en", [tmp_path / "01.png"])
    assert st.is_translation_complete([tmp_path / "01.png"]) is True
    assert st.chapter_language == "EN"

def test_workspace_incremental_ocr(tmp_path: Path):
    ws = JsonTempWorkspace(tmp_path)
    page1 = PageTranslation("01.png", 800, 1200, [BubbleBlock("p1_b1", (0, 0, 50, 50), "一")])
    page2 = PageTranslation("02.png", 800, 1200, [BubbleBlock("p2_b1", (0, 0, 50, 50), "二")])

    ws.save_page(page1)
    assert ws.is_ocr_complete(total_pages=2) is False

    ws.save_page(page2)
    assert ws.is_ocr_complete(total_pages=2) is True

    loaded = ws.load_pages()
    assert len(loaded) == 2
    assert "01.png" in loaded and "02.png" in loaded

def test_workspace_logging(tmp_path: Path):
    ws = JsonTempWorkspace(tmp_path)
    ws.append_log("Starting OCR")
    log_file = ws.get_temp_dir() / "translation.log"
    assert log_file.exists()
    assert "Starting OCR" in log_file.read_text(encoding="utf-8")

def test_workspace_manual_labeled_pages(tmp_path: Path):
    ws = JsonTempWorkspace(tmp_path)
    bubble1 = BubbleBlock("p1_b1", (0, 0, 50, 50), "はい", text_en="Yes", is_manual=False)
    page1 = PageTranslation("01.png", 800, 1200, [bubble1])
    ws.save_page(page1)
    ws.save_translations({"p1_b1": "Yes"}, target_lang="en")

    # Page 1 is fully translated and not manual
    st = ws.status("en", [tmp_path / "01.png"])
    assert "01.png" in st.translated_filenames
    assert "01.png" not in st.manual_filenames

def test_workspace_status_contract(tmp_path: Path):
    ws = JsonTempWorkspace(tmp_path)
    img_paths = [tmp_path / "01.png", tmp_path / "02.png"]
    for img in img_paths:
        img.touch()

    # Empty status
    st = ws.status("en", img_paths)
    assert st.ocr_complete is False
    assert st.total_cached_translations == 0
    assert len(st.translated_filenames) == 0

    # Add 1 page OCR with manual bubble
    b_manual = BubbleBlock("p1_m_1", (10, 10, 50, 50), text_ja="", is_manual=True)
    ws.save_page(PageTranslation("01.png", 500, 800, [b_manual]))

    st2 = ws.status("en", img_paths)
    assert "01.png" in st2.manual_filenames
    assert st2.is_translation_complete(img_paths) is False


def test_workspace_corrupt_json_recovery(tmp_path: Path):
    ws = JsonTempWorkspace(tmp_path)
    ocr_file = ws.ocr_file
    ocr_file.write_text("{corrupt-json-truncated", encoding="utf-8")

    # Should not raise; recovers gracefully to empty dict
    loaded = ws.load_pages()
    assert loaded == {}


def test_workspace_language_file_resolution(tmp_path: Path):
    ws = JsonTempWorkspace(tmp_path)
    ws.save_translations({"b1": "Indonesian text"}, target_lang="id")
    assert (ws.temp_dir / "translation_results_id.json").exists()

    loaded_id = ws.load_translations("id")
    assert loaded_id.get("b1") == "Indonesian text"

    ws.save_translations({"b2": "English text"}, target_lang="en")
    assert (ws.temp_dir / "translation_results.json").exists()
    loaded_en = ws.load_translations("en")
    assert loaded_en.get("b2") == "English text"


def test_workspace_clear_cache_scoped_to_temp(tmp_path: Path):
    # Outside file that must NOT be deleted
    outside_file = tmp_path / "important.png"
    outside_file.write_text("keep me", encoding="utf-8")

    ws = JsonTempWorkspace(tmp_path)
    ws.save_translations({"b1": "text"}, target_lang="en")
    assert ws.translation_file.exists()

    ws.clear_cache()
    assert not ws.ocr_file.exists()
    # Outside file is preserved
    assert outside_file.exists()
    assert outside_file.read_text(encoding="utf-8") == "keep me"
