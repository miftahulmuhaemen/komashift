from pathlib import Path
import re
import sys
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTabWidget, QWidget,
    QFormLayout, QComboBox, QSpinBox, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon
from src.version import __version__, BUILD

PROVIDER_PRESETS = {
    "OpenCode.ai (Free Models)": {
        "base_url": "https://opencode.ai/inference/openai/v1",
        "models": [
            "deepseek-v4.1-flash-free",
            "glm-5.3-flash-free",
            "beam-free",
            "flint-40b-free",
            "mimo-v2.6-flash-free",
            "nemotron-3.5-lightning-free",
            "pulse-alpha-free",
            "crouton-alpha-free",
        ],
        "key_placeholder": "Paste your OpenCode token..."
    },
    "Google Gemini (Official)": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-2.5-pro",
        ],
        "key_placeholder": "AIzaSy..."
    },
    "OpenRouter (Free Models)": {
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "google/gemini-2.0-flash-lite:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-r1:free",
            "qwen/qwen-2.5-72b-instruct:free",
        ],
        "key_placeholder": "sk-or-v1-..."
    },
    "Custom / Other": {
        "base_url": "",
        "models": [],
        "key_placeholder": "API Key..."
    }
}


def _provider_slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower()).strip("_")


class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings: Optional[QSettings] = None, is_queue_running: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(560, 520)
        self.resize(580, 560)

        self.settings = settings or QSettings("FolderImagePreviewer", "FolderImagePreviewer")
        self.is_queue_running = is_queue_running
        self._current_provider = None
        self._provider_cache = {}

        self._init_ui()
        self._set_icon()
        self._load_settings()

    def _set_icon(self):
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            icon_path = Path(sys._MEIPASS) / "assets" / "icon.png"
        else:
            icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #f1f5f9;
            }
            QTabWidget::pane {
                border: 1px solid #334155;
                background-color: #242428;
                border-radius: 4px;
            }
            QTabBar::tab {
                background: #18181b;
                color: #94a3b8;
                padding: 8px 18px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background: #242428;
                color: #f8fafc;
                border-bottom: 2px solid #38bdf8;
            }
            QLabel {
                color: #cbd5e1;
                font-size: 13px;
            }
            QLineEdit, QComboBox, QSpinBox {
                background-color: #1e1e24;
                color: #f8fafc;
                border: 1.5px solid #475569;
                border-radius: 5px;
                padding: 6px 10px;
                font-size: 13px;
                min-height: 22px;
            }
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
                border: 1.5px solid #38bdf8;
            }
            QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {
                background-color: #18181b;
                color: #64748b;
                border: 1px solid #334155;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e24;
                color: #f8fafc;
                selection-background-color: #0284c7;
                border: 1px solid #475569;
            }
            QPushButton {
                background-color: #334155;
                color: #f8fafc;
                border: 1px solid #475569;
                padding: 7px 16px;
                border-radius: 5px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton:disabled {
                background-color: #18181b;
                color: #64748b;
                border: 1px solid #334155;
            }
            QPushButton#saveBtn {
                background-color: #0284c7;
                border: 1px solid #38bdf8;
            }
            QPushButton#saveBtn:hover {
                background-color: #0369a1;
            }
            QPushButton#saveBtn:disabled {
                background-color: #18181b;
                color: #64748b;
                border: 1px solid #334155;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.tab_widget = QTabWidget()

        # Tab 1: API & Translation Protocol
        api_tab = QWidget()
        api_tab_layout = QVBoxLayout(api_tab)
        api_tab_layout.setContentsMargins(0, 0, 0, 0)
        api_tab_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        api_container = QWidget()
        api_container.setStyleSheet("background: transparent;")
        api_layout = QFormLayout(api_container)
        api_layout.setContentsMargins(18, 18, 18, 18)
        api_layout.setSpacing(14)

        # Queue Running Notice
        self.running_notice = QLabel("⚠️ Translation queue is currently running. Settings cannot be modified.")
        self.running_notice.setStyleSheet("""
            color: #fbbf24;
            font-size: 12px;
            padding: 8px 12px;
            background-color: #27272a;
            border: 1px solid #475569;
            border-radius: 4px;
            min-height: 18px;
        """)
        self.running_notice.setVisible(self.is_queue_running)
        api_layout.addRow(self.running_notice)

        # Provider Preset selector
        self.provider_combo = QComboBox()
        for p_name in PROVIDER_PRESETS.keys():
            self.provider_combo.addItem(p_name)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        api_layout.addRow("Service / Provider:", self.provider_combo)

        # Model Preset dropdown
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._on_model_combo_changed)
        api_layout.addRow("Model Preset:", self.model_combo)

        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("API Key...")
        api_layout.addRow("API Key / Token:", self.api_key_input)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://...")
        api_layout.addRow("Endpoint / Base URL:", self.base_url_input)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("model-name")
        api_layout.addRow("Model Name:", self.model_input)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(15, 600)
        self.timeout_spin.setValue(120)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setToolTip("Request timeout in seconds (Default: 120s)")
        api_layout.addRow("Timeout (Seconds):", self.timeout_spin)

        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(0, 300)
        self.batch_size_spin.setSpecialValueText("0 (Disabled / Full Chapter)")
        self.batch_size_spin.setValue(0)
        self.batch_size_spin.setSuffix(" bubbles")
        self.batch_size_spin.setToolTip("Maximum speech bubbles per batch. Set to 0 to disable batching and send full chapter (Default: 0)")
        api_layout.addRow("Batch Split (Size):", self.batch_size_spin)

        scroll.setWidget(api_container)
        api_tab_layout.addWidget(scroll)

        self.tab_widget.addTab(api_tab, "API && Translation")

        # Tab 2: Version & About
        version_tab = QWidget()
        version_layout = QVBoxLayout(version_tab)
        version_layout.setContentsMargins(20, 20, 20, 20)
        version_layout.setSpacing(10)

        app_title = QLabel("Windows Folder Image Previewer")
        app_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        version_layout.addWidget(app_title)

        self.version_label = QLabel(f"Version: v{__version__} (Build {BUILD})")
        self.version_label.setStyleSheet("color: #f1f5f9; font-size: 13px;")
        version_layout.addWidget(self.version_label)

        py_info = QLabel(f"Python Runtime: {sys.version.split()[0]} | PyQt6")
        py_info.setStyleSheet("color: #94a3b8; font-size: 12px;")
        version_layout.addWidget(py_info)

        desc = QLabel(
            "Manga reader and folder previewer with OCR translation overlay and batch management."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #64748b; font-size: 12px; margin-top: 8px;")
        version_layout.addWidget(desc)
        version_layout.addStretch()

        self.tab_widget.addTab(version_tab, "Version && About")
        layout.addWidget(self.tab_widget)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _on_provider_changed(self, index: int):
        new_provider = self.provider_combo.currentText()

        # Save previous provider inputs to in-memory cache
        if self._current_provider and self._current_provider != "Custom / Other":
            self._provider_cache[self._current_provider] = {
                "api_key": self.api_key_input.text().strip(),
                "base_url": self.base_url_input.text().strip(),
                "model": self.model_input.text().strip(),
            }

        self._current_provider = new_provider
        preset = PROVIDER_PRESETS.get(new_provider, {})
        placeholder = preset.get("key_placeholder", "API Key...")
        self.api_key_input.setPlaceholderText(placeholder)

        if new_provider == "Custom / Other":
            # For Custom / Other: always clear API key, endpoint, and model
            self.api_key_input.clear()
            self.base_url_input.clear()
            self.model_input.clear()
            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            self.model_combo.addItem("(Custom)")
            self.model_combo.blockSignals(False)
        else:
            cached = self._provider_cache.get(new_provider, {})
            cached_key = cached.get("api_key", "")
            cached_url = cached.get("base_url", preset.get("base_url", ""))
            models = preset.get("models", [])
            cached_model = cached.get("model", models[0] if models else "")

            # Restore cached values or blank if never inserted
            self.api_key_input.setText(cached_key)
            self.base_url_input.setText(cached_url)

            self.model_combo.blockSignals(True)
            self.model_combo.clear()
            for m in models:
                self.model_combo.addItem(m)
            m_idx = self.model_combo.findText(cached_model)
            if m_idx >= 0:
                self.model_combo.setCurrentIndex(m_idx)
            else:
                if cached_model:
                    self.model_combo.addItem(cached_model)
                    self.model_combo.setCurrentText(cached_model)
                elif models:
                    self.model_combo.setCurrentIndex(0)
            self.model_combo.blockSignals(False)

            self.model_input.setText(cached_model or (models[0] if models else ""))

    def _on_model_combo_changed(self, index: int):
        text = self.model_combo.currentText()
        if text and text != "(Custom)":
            self.model_input.setText(text)

    def _load_settings(self):
        active_provider = self.settings.value("llm_provider", "Google Gemini (Official)", type=str)
        active_api_key = self.settings.value("llm_api_key", "", type=str)
        active_base_url = self.settings.value("llm_base_url", "https://generativelanguage.googleapis.com/v1beta/openai/", type=str)
        active_model = self.settings.value("llm_model", "gemini-2.5-flash", type=str)

        # Load per-provider cache from QSettings
        self._provider_cache = {}
        for p_name in PROVIDER_PRESETS.keys():
            if p_name == "Custom / Other":
                self._provider_cache[p_name] = {"api_key": "", "base_url": "", "model": ""}
            else:
                slug = _provider_slug(p_name)
                cached_key = self.settings.value(f"provider_cache/{slug}/api_key", "", type=str)
                cached_url = self.settings.value(f"provider_cache/{slug}/base_url", PROVIDER_PRESETS[p_name]["base_url"], type=str)
                cached_model = self.settings.value(f"provider_cache/{slug}/model", "", type=str)
                self._provider_cache[p_name] = {
                    "api_key": cached_key,
                    "base_url": cached_url,
                    "model": cached_model or (PROVIDER_PRESETS[p_name]["models"][0] if PROVIDER_PRESETS[p_name]["models"] else "")
                }

        # Match active provider by name or endpoint URL
        matched_provider = active_provider
        if matched_provider not in PROVIDER_PRESETS:
            matched_provider = "Custom / Other"
            for p_name, p_data in PROVIDER_PRESETS.items():
                if p_name == "Custom / Other":
                    continue
                if p_data["base_url"].rstrip("/") == active_base_url.rstrip("/"):
                    matched_provider = p_name
                    break

        # Put currently active credentials into matched provider cache
        if matched_provider != "Custom / Other":
            self._provider_cache[matched_provider]["api_key"] = active_api_key
            self._provider_cache[matched_provider]["base_url"] = active_base_url
            self._provider_cache[matched_provider]["model"] = active_model

        self._current_provider = matched_provider

        # Set provider combo without firing trigger prematurely
        self.provider_combo.blockSignals(True)
        idx = self.provider_combo.findText(matched_provider)
        if idx >= 0:
            self.provider_combo.setCurrentIndex(idx)
        self.provider_combo.blockSignals(False)

        preset = PROVIDER_PRESETS.get(matched_provider, {})
        self.api_key_input.setPlaceholderText(preset.get("key_placeholder", "API Key..."))
        self.api_key_input.setText(active_api_key)
        self.base_url_input.setText(active_base_url)
        self.model_input.setText(active_model)

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        models = preset.get("models", [])
        if models:
            for m in models:
                self.model_combo.addItem(m)
            m_idx = self.model_combo.findText(active_model)
            if m_idx >= 0:
                self.model_combo.setCurrentIndex(m_idx)
            else:
                self.model_combo.addItem(active_model)
                self.model_combo.setCurrentText(active_model)
        else:
            self.model_combo.addItem("(Custom)")
        self.model_combo.blockSignals(False)

        timeout_val = self.settings.value("llm_timeout_seconds", 120, type=int)
        batch_size_val = self.settings.value("llm_batch_size", 0, type=int)
        self.timeout_spin.setValue(timeout_val if timeout_val >= 15 else 120)
        self.batch_size_spin.setValue(max(0, batch_size_val))

        if self.is_queue_running:
            self.set_queue_running(True)

    def set_queue_running(self, running: bool):
        self.is_queue_running = running
        self.provider_combo.setEnabled(not running)
        self.model_combo.setEnabled(not running)
        self.api_key_input.setEnabled(not running)
        self.base_url_input.setEnabled(not running)
        self.model_input.setEnabled(not running)
        self.timeout_spin.setEnabled(not running)
        self.batch_size_spin.setEnabled(not running)
        self.save_btn.setEnabled(not running)
        if hasattr(self, "running_notice"):
            self.running_notice.setVisible(running)

    def _on_save(self):
        curr_provider = self.provider_combo.currentText()
        if curr_provider != "Custom / Other":
            self._provider_cache[curr_provider] = {
                "api_key": self.api_key_input.text().strip(),
                "base_url": self.base_url_input.text().strip(),
                "model": self.model_input.text().strip(),
            }

        self.settings.setValue("llm_provider", curr_provider)
        self.settings.setValue("llm_api_key", self.api_key_input.text().strip())
        self.settings.setValue("llm_base_url", self.base_url_input.text().strip())
        self.settings.setValue("llm_model", self.model_input.text().strip())
        self.settings.setValue("llm_timeout_seconds", self.timeout_spin.value())
        self.settings.setValue("llm_batch_size", self.batch_size_spin.value())

        # Persist per-provider cache in QSettings
        for p_name, data in self._provider_cache.items():
            if p_name == "Custom / Other":
                continue
            slug = _provider_slug(p_name)
            self.settings.setValue(f"provider_cache/{slug}/api_key", data.get("api_key", ""))
            self.settings.setValue(f"provider_cache/{slug}/base_url", data.get("base_url", ""))
            self.settings.setValue(f"provider_cache/{slug}/model", data.get("model", ""))

        self.accept()
