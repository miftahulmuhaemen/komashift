from pathlib import Path
from unittest.mock import MagicMock
from PyQt6.QtCore import QSettings
from src.models.folder_item import FolderItem
from src.models.translation_item import PageTranslation
from src.viewmodels.settings_viewmodel import SettingsViewModel
from src.viewmodels.library_viewmodel import LibraryViewModel
from src.viewmodels.translation_viewmodel import TranslationViewModel
from src.services.translation_queue import TranslationQueueManager


def test_settings_viewmodel(tmp_path: Path):
    ini_file = tmp_path / "settings.ini"
    settings = QSettings(str(ini_file), QSettings.Format.IniFormat)
    vm = SettingsViewModel(settings)

    assert vm.get_last_root_folder() is None
    vm.set_last_root_folder(str(tmp_path))
    assert vm.get_last_root_folder() == str(tmp_path)

    vm.set_api_key("sk-test-12345")
    creds = vm.get_api_credentials()
    assert creds[0] == "sk-test-12345"
    assert len(creds) == 12

    assert vm.get_manga_ocr_model() == ""
    vm.set_manga_ocr_model("custom-user/manga-ocr")
    assert vm.get_manga_ocr_model() == "custom-user/manga-ocr"

    assert vm.get_onnx_force_cpu() is False
    vm.set_onnx_force_cpu(True)
    assert vm.get_onnx_force_cpu() is True

    providers = vm.get_detected_providers()
    assert isinstance(providers, list)
    assert len(providers) >= 1



def test_library_viewmodel(tmp_path: Path):
    vm = LibraryViewModel()

    # Create dummy folder
    sub = tmp_path / "chapter_01"
    sub.mkdir()
    (sub / "01.png").write_bytes(b"dummy")

    folders = vm.load_directory(tmp_path)
    assert len(folders) == 1
    assert folders[0].name == "chapter_01"

    # Navigation
    assert vm.navigate_next(total_images=5) == 1
    assert vm.navigate_next(total_images=5) == 2
    assert vm.navigate_previous(total_images=5) == 1
    assert vm.navigate_previous(total_images=5) == 0
    assert vm.navigate_previous(total_images=5) == 4  # Wrap-around


def test_translation_viewmodel(tmp_path: Path):
    queue_mgr = TranslationQueueManager(settings_getter=lambda: ("", "", "", 300, 0, "hybrid", 75, 75, 3, "openai"))
    vm = TranslationViewModel(queue_mgr)

    assert vm.is_overlay_enabled is True
    assert vm.toggle_overlay() is False
    assert vm.is_overlay_enabled is False

    assert vm.is_box_tool_active is False
    assert vm.toggle_box_tool() is True
    assert vm.is_box_tool_active is True

    # Test adding manual bubble
    img_file = tmp_path / "01.png"
    img_file.write_bytes(b"dummy")

    page, translations, bubble = vm.add_manual_bubble(
        folder_path=tmp_path,
        image_path=img_file,
        image_index=0,
        bbox=(10, 20, 50, 60),
        target_lang="en",
        image_size=(500, 700)
    )

    assert bubble.bbox == (10, 20, 50, 60)
    assert bubble.is_manual is True
    assert len(page.bubbles) == 1
    assert len(queue_mgr.jobs) == 1
    assert queue_mgr.jobs[0].folder_path == tmp_path
