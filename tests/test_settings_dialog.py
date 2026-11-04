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
    assert dialog.model_input.text() == "gemini-1.5-flash"
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
    assert window.settings_btn.text() == "⚙ Settings"
