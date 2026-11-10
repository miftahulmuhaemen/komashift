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
    assert "Translate" in window.translate_btn.text()
    assert hasattr(window, "queue_mgr_btn")
    assert "Queue Manager" in window.queue_mgr_btn.text()
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

def test_batch_queue_multiple_folders(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)

    f1_dir = tmp_path / "ch1"
    f2_dir = tmp_path / "ch2"
    _create_test_folder(f1_dir)
    _create_test_folder(f2_dir)

    f1 = FolderItem(f1_dir, "ch1", [f1_dir / "01.png"])
    f2 = FolderItem(f2_dir, "ch2", [f2_dir / "01.png"])
    window.folder_list.set_folders([f1, f2])

    # Select both folders
    window.folder_list.list_widget.item(0).setSelected(True)
    window.folder_list.list_widget.item(1).setSelected(True)

    with patch.object(window, "_get_api_credentials", return_value=("fake_key", "", "model", 120, 0, "hybrid", 75, 75)):
        window._on_add_to_queue(target_lang="en")

    assert len(window.queue_manager.jobs) == 2
    assert window.folder_list.get_folder_status(f1.path) == "queued"
    assert window.folder_list.get_folder_status(f2.path) == "queued"

def test_folder_context_menu_actions(qtbot, tmp_path: Path):
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QMenu
    window = MainWindow()
    qtbot.addWidget(window)

    f1_dir = tmp_path / "ch1"
    _create_test_folder(f1_dir)
    f1 = FolderItem(f1_dir, "ch1", [f1_dir / "01.png"])
    window.folder_list.set_folders([f1])

    with patch.object(QMenu, "exec") as mock_exec:
        window._show_folder_context_menu(f1, QPoint(100, 100))
        assert mock_exec.called

