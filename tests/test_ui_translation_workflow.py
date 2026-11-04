from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image
from PyQt6.QtCore import Qt
from src.models.folder_item import FolderItem
from src.models.translation_item import PageTranslation, BubbleBlock
from src.ui.main_window import MainWindow

def _create_test_folder(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    for name in ["01.png", "02.png"]:
        img = Image.new("RGB", (200, 300), color="white")
        img.save(path / name)

def test_main_window_has_translate_controls(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert hasattr(window, "translate_btn")
    assert "Translate to EN" in window.translate_btn.text()
    assert hasattr(window, "overlay_toggle_btn")

def test_auto_load_translation_on_image_selected(qtbot, tmp_path: Path):
    folder_path = tmp_path / "chapter1"
    _create_test_folder(folder_path)

    # Pre-populate workspace
    temp_dir = folder_path / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    from src.services.translation_workspace import TranslationWorkspace
    ws = TranslationWorkspace(folder_path)
    ws.save_page_ocr(PageTranslation("01.png", 200, 300, [BubbleBlock("b1", (10, 10, 40, 40), "こんにちは")]))
    ws.save_translations({"b1": "Hello"})

    window = MainWindow()
    qtbot.addWidget(window)

    folder_item = FolderItem(folder_path, "chapter1", [folder_path / "01.png", folder_path / "02.png"])
    window._on_folder_selected(folder_item)
    window._on_image_selected(folder_path / "01.png")

    assert window.preview_pane._page_translation is not None
    assert window.preview_pane._page_translation.page_filename == "01.png"
    assert window.preview_pane._translations.get("b1") == "Hello"

def test_toggle_overlay_shortcut(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    initial_state = window.preview_pane.is_translation_overlay_enabled()
    window._toggle_translation_overlay()
    assert window.preview_pane.is_translation_overlay_enabled() != initial_state
