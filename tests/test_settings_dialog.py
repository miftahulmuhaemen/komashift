from unittest.mock import patch
from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QLineEdit
from src.ui.settings_dialog import SettingsDialog
from src.version import __version__

def test_settings_dialog_defaults_and_visible_api_key(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestSettingsEmpty")
    settings.clear()
    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)

    # API key must NOT be hidden / password masked
    assert dialog.api_key_input.echoMode() == QLineEdit.EchoMode.Normal
    # Defaults must point to Google Gemini OpenAI-compatible endpoint
    assert dialog.base_url_input.text() == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert dialog.model_input.text() == "gemini-2.5-flash"
    settings.clear()

def test_settings_dialog_load_and_save(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestSettings")
    settings.setValue("llm_api_key", "sk-initial")
    settings.setValue("llm_base_url", "https://api.openai.com/v1")
    settings.setValue("llm_model", "gpt-4o-mini")

    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)

    assert dialog.api_key_input.text() == "sk-initial"
    assert dialog.base_url_input.text() == "https://api.openai.com/v1"
    assert dialog.model_input.text() == "gpt-4o-mini"

    # Modify and save
    dialog.api_key_input.setText("sk-updated")
    dialog.base_url_input.setText("https://openrouter.ai/api/v1")
    dialog.model_input.setText("gpt-4o")
    dialog._on_save()

    assert settings.value("llm_api_key") == "sk-updated"
    assert settings.value("llm_base_url") == "https://openrouter.ai/api/v1"
    assert settings.value("llm_model") == "gpt-4o"

    settings.clear()

def test_settings_dialog_version_tab(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestSettings")
    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)

    assert __version__ in dialog.version_label.text()
    settings.clear()

def test_main_window_has_settings_button(qtbot):
    from src.ui.main_window import MainWindow
    window = MainWindow()
    qtbot.addWidget(window)
    assert hasattr(window, "settings_btn")
    assert "Settings" in window.settings_btn.text()

def test_settings_dialog_inputs_disabled_when_queue_running(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestSettingsDisabled")
    settings.clear()
    dialog = SettingsDialog(settings=settings, is_queue_running=True)
    qtbot.addWidget(dialog)

    assert dialog.provider_combo.isEnabled() is False
    assert dialog.model_combo.isEnabled() is False
    assert dialog.api_key_input.isEnabled() is False
    assert dialog.base_url_input.isEnabled() is False
    assert dialog.model_input.isEnabled() is False
    assert dialog.hardware_accel_combo.isEnabled() is False
    assert dialog.manga_ocr_model_input.isEnabled() is False
    assert dialog.manga_ocr_browse_btn.isEnabled() is False
    assert dialog.save_btn.isEnabled() is False
    assert not dialog.running_notice.isHidden()

    # When queue stops, it re-enables inputs
    dialog.set_queue_running(False)
    assert dialog.provider_combo.isEnabled() is True
    assert dialog.model_combo.isEnabled() is True
    assert dialog.api_key_input.isEnabled() is True
    assert dialog.base_url_input.isEnabled() is True
    assert dialog.model_input.isEnabled() is True
    assert dialog.hardware_accel_combo.isEnabled() is True
    assert dialog.manga_ocr_model_input.isEnabled() is True
    assert dialog.manga_ocr_browse_btn.isEnabled() is True
    assert dialog.save_btn.isEnabled() is True
    assert dialog.running_notice.isHidden()
    settings.clear()


def test_settings_dialog_opencode_preset(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestSettingsPreset")
    settings.clear()
    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)

    # Change provider to OpenCode
    idx = dialog.provider_combo.findText("OpenCode.ai (Free Models)")
    assert idx >= 0
    dialog.provider_combo.setCurrentIndex(idx)

    assert dialog.base_url_input.text() == "https://opencode.ai/inference/openai/v1"
    assert dialog.model_input.text() == "deepseek-v4.1-flash-free"
    assert "Paste your OpenCode token" in dialog.api_key_input.placeholderText()

    # Change model preset in dropdown
    idx_model = dialog.model_combo.findText("glm-5.3-flash-free")
    assert idx_model >= 0
    dialog.model_combo.setCurrentIndex(idx_model)
    assert dialog.model_input.text() == "glm-5.3-flash-free"

    # Save
    dialog.api_key_input.setText("test-opencode-token")
    dialog._on_save()

    assert settings.value("llm_provider") == "OpenCode.ai (Free Models)"
    assert settings.value("llm_base_url") == "https://opencode.ai/inference/openai/v1"
    assert settings.value("llm_model") == "glm-5.3-flash-free"
    assert settings.value("llm_api_key") == "test-opencode-token"

    settings.clear()


def test_settings_dialog_provider_switching_memory_and_custom_blank(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestMemory")
    settings.clear()
    settings.setValue("llm_provider", "Google Gemini (Official)")
    settings.setValue("llm_api_key", "AIzaSy_google_secret")
    settings.setValue("llm_base_url", "https://generativelanguage.googleapis.com/v1beta/openai/")
    settings.setValue("llm_model", "gemini-2.5-flash")

    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)

    # Initial state should be Google Gemini with its credentials
    assert dialog.provider_combo.currentText() == "Google Gemini (Official)"
    assert dialog.api_key_input.text() == "AIzaSy_google_secret"
    assert dialog.base_url_input.text() == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert dialog.model_input.text() == "gemini-2.5-flash"

    # Switch to OpenCode.ai - previously unvisited, so API key must be blank
    opencode_idx = dialog.provider_combo.findText("OpenCode.ai (Free Models)")
    dialog.provider_combo.setCurrentIndex(opencode_idx)
    assert dialog.api_key_input.text() == ""
    assert dialog.base_url_input.text() == "https://opencode.ai/inference/openai/v1"
    assert dialog.model_input.text() == "deepseek-v4.1-flash-free"

    # User enters an OpenCode token
    dialog.api_key_input.setText("opencode_token_12345")

    # Switch to Custom / Other - must leave API token, endpoint, and model name blank!
    custom_idx = dialog.provider_combo.findText("Custom / Other")
    dialog.provider_combo.setCurrentIndex(custom_idx)
    assert dialog.api_key_input.text() == ""
    assert dialog.base_url_input.text() == ""
    assert dialog.model_input.text() == ""
    assert dialog.model_combo.currentText() == "(Custom)"

    # Switch back to Google Gemini - previous Google values must be restored!
    google_idx = dialog.provider_combo.findText("Google Gemini (Official)")
    dialog.provider_combo.setCurrentIndex(google_idx)
    assert dialog.api_key_input.text() == "AIzaSy_google_secret"
    assert dialog.base_url_input.text() == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert dialog.model_input.text() == "gemini-2.5-flash"

    # Switch back to OpenCode.ai - previous OpenCode token must be restored!
    dialog.provider_combo.setCurrentIndex(opencode_idx)
    assert dialog.api_key_input.text() == "opencode_token_12345"
    assert dialog.base_url_input.text() == "https://opencode.ai/inference/openai/v1"

    # Save dialog and ensure settings persist
    dialog._on_save()
    assert settings.value("llm_provider") == "OpenCode.ai (Free Models)"
    assert settings.value("llm_api_key") == "opencode_token_12345"

    # Re-open dialog in a new instance and verify persistence
    dialog2 = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog2)
    assert dialog2.provider_combo.currentText() == "OpenCode.ai (Free Models)"
    assert dialog2.api_key_input.text() == "opencode_token_12345"

    # Switch to Google on new dialog instance - Google key is still remembered
    dialog2.provider_combo.setCurrentIndex(dialog2.provider_combo.findText("Google Gemini (Official)"))
    assert dialog2.api_key_input.text() == "AIzaSy_google_secret"

    settings.clear()


def test_settings_dialog_engine_mode_multimodal(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestEngineMode")
    settings.clear()

    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)

    # Defaults: hybrid mode
    assert dialog.engine_combo.currentData() == "hybrid"
    assert dialog.vision_scale_combo.isEnabled() is False
    assert dialog.vision_quality_combo.isEnabled() is False

    # Switch to multimodal mode
    multi_idx = dialog.engine_combo.findData("multimodal")
    dialog.engine_combo.setCurrentIndex(multi_idx)

    assert dialog.vision_scale_combo.isEnabled() is True
    assert dialog.vision_quality_combo.isEnabled() is True

    # Change vision scale and quality
    s_idx = dialog.vision_scale_combo.findData(50)
    dialog.vision_scale_combo.setCurrentIndex(s_idx)

    q_idx = dialog.vision_quality_combo.findData(90)
    dialog.vision_quality_combo.setCurrentIndex(q_idx)

    dialog._on_save()

    assert settings.value("llm_engine_mode") == "multimodal"
    assert settings.value("llm_vision_scale_pct", type=int) == 50
    assert settings.value("llm_vision_quality", type=int) == 90

    # Re-open and verify persistence
    dialog2 = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog2)
    assert dialog2.engine_combo.currentData() == "multimodal"
    assert dialog2.vision_scale_combo.currentData() == 50
    assert dialog2.vision_quality_combo.currentData() == 90

    settings.clear()


def test_settings_dialog_hardware_accel_and_custom_ocr_model(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestAccelOcr")
    settings.clear()

    # Initial defaults
    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)

    # Hardware acceleration defaults to auto-detect
    assert dialog.hardware_accel_combo.currentData() == "auto"
    assert dialog.manga_ocr_model_input.text() == ""
    assert "Detected ONNX providers:" in dialog.accel_info_label.text()

    # Change to CPU Only and specify a custom HuggingFace model repo
    cpu_idx = dialog.hardware_accel_combo.findData("cpu")
    dialog.hardware_accel_combo.setCurrentIndex(cpu_idx)
    dialog.manga_ocr_model_input.setText("my-custom-user/manga-ocr-finetuned")

    dialog._on_save()

    assert settings.value("onnx_force_cpu", type=bool) is True
    assert settings.value("manga_ocr_model", type=str) == "my-custom-user/manga-ocr-finetuned"

    # Re-open dialog in new instance and verify persistence
    dialog2 = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog2)
    assert dialog2.hardware_accel_combo.currentData() == "cpu"
    assert dialog2.manga_ocr_model_input.text() == "my-custom-user/manga-ocr-finetuned"

    settings.clear()


def test_settings_dialog_browse_manga_ocr_model(qtbot, tmp_path):
    settings = QSettings("FolderImagePreviewerTest", "TestBrowseOcr")
    settings.clear()

    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)

    model_dir = tmp_path / "custom_ocr_model"
    model_dir.mkdir()

    with patch("PyQt6.QtWidgets.QFileDialog.getExistingDirectory", return_value=str(model_dir)):
        dialog.manga_ocr_browse_btn.click()
        assert dialog.manga_ocr_model_input.text() == str(model_dir)

    settings.clear()


def test_settings_dialog_ocr_cache_check_and_download_flow(qtbot):
    settings = QSettings("FolderImagePreviewerTest", "TestDownloadFlow")
    settings.clear()

    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    # Mock uncached model
    with patch("src.services.ai_assets_manager.AiAssetsManager.is_ocr_model_cached", return_value=False):
        dialog.manga_ocr_model_input.setText("uncached/manga-ocr")
        dialog._check_ocr_model_cache()
        qtbot.waitUntil(lambda: not dialog.manga_ocr_download_btn.isHidden(), timeout=2000)

        assert dialog.manga_ocr_download_btn.isVisible() is True
        assert "not in local cache" in dialog.manga_ocr_status_badge.text().lower()

    # Click Download with mock download worker
    with patch("src.infra.model_download_worker.ModelDownloadWorker.start"):
        dialog.manga_ocr_download_btn.click()
        assert dialog.manga_ocr_pause_btn.isVisible() is True
        assert dialog.manga_ocr_cancel_btn.isVisible() is True
        assert dialog.manga_ocr_progress_bar.isVisible() is True

        # Click Cancel
        dialog.manga_ocr_cancel_btn.click()
        # Input should revert to empty (default)
        assert dialog.manga_ocr_model_input.text() == ""
        assert settings.value("manga_ocr_model") == ""
        assert dialog.manga_ocr_pause_btn.isVisible() is False
        assert dialog.manga_ocr_cancel_btn.isVisible() is False

    dialog.cleanup()
    settings.clear()


def test_settings_dialog_ocr_cached_local_folder(qtbot, tmp_path):
    settings = QSettings("FolderImagePreviewerTest", "TestLocalCached")
    settings.clear()

    dialog = SettingsDialog(settings=settings)
    qtbot.addWidget(dialog)
    dialog.show()

    model_dir = tmp_path / "valid_model"
    model_dir.mkdir()
    (model_dir / "encoder_model.onnx").touch()
    (model_dir / "decoder_model.onnx").touch()

    dialog.manga_ocr_model_input.setText(str(model_dir))
    dialog._check_ocr_model_cache()
    qtbot.waitUntil(lambda: "Local Model Directory" in dialog.manga_ocr_status_badge.text(), timeout=2000)

    assert "Local Model Directory" in dialog.manga_ocr_status_badge.text()
    assert dialog.manga_ocr_download_btn.isVisible() is False

    dialog.cleanup()
    settings.clear()


