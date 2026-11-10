from pathlib import Path
import re
import sys
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTabWidget, QWidget,
    QFormLayout, QComboBox, QSpinBox, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QSettings, QObject, QEvent
from PyQt6.QtGui import QIcon
from src.version import __version__, BUILD

PROVIDER_PRESETS = {
    "OpenCode.ai (Free Models)": {
        "protocol": "openai",
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
        "protocol": "openai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": [
            "gemini-2.5-flash",
            "gemini-2.0-flash-lite",
            "gemini-1.5-flash",
            "gemini-2.5-pro",
        ],
        "key_placeholder": "AIzaSy..."
    },
    "Anthropic Claude (Official)": {
        "protocol": "anthropic",
        "base_url": "https://api.anthropic.com/v1/messages",
        "models": [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ],
        "key_placeholder": "sk-ant-api03-..."
    },
    "OpenRouter (Free Models)": {
        "protocol": "openai",
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
        "protocol": "openai",
        "base_url": "",
        "models": [],
        "key_placeholder": "API Key..."
    }
}


class NoWheelEventFilter(QObject):
    """Ignores mouse wheel events on widgets so scrollable pages scroll smoothly without value jumping."""
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel:
            if isinstance(obj, QComboBox) and obj.view() and obj.view().isVisible():
                return False
            event.ignore()
            return True
        return super().eventFilter(obj, event)


def _provider_slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower()).strip("_")


class ApiTranslationSettingsWidget(QWidget):
    """Reusable widget for configuring API credentials and translation engine parameters."""
    def __init__(self, parent=None, settings: Optional[QSettings] = None, is_queue_running: bool = False):
        super().__init__(parent)
        self.settings = settings or QSettings("FolderImagePreviewer", "FolderImagePreviewer")
        self.is_queue_running = is_queue_running
        self._current_provider = None
        self._provider_cache = {}

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        self.setStyleSheet("""
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        api_container = QWidget()
        api_container.setStyleSheet("background: transparent;")
        api_layout = QFormLayout(api_container)
        api_layout.setContentsMargins(16, 16, 16, 16)
        api_layout.setSpacing(12)

        self._no_wheel_filter = NoWheelEventFilter(self)

        # Queue Running Notice
        self.running_notice = QLabel("Translation queue is currently running. Settings cannot be modified.")
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

        # Translation Engine Selector
        self.engine_combo = QComboBox()
        self.engine_combo.addItem("Fast & Token-Efficient (Local ONNX + Manga OCR + Text LLM)", "hybrid")
        self.engine_combo.addItem("Highest Quality (Local ONNX Segmentation + Multimodal LLM)", "multimodal")
        self.engine_combo.currentIndexChanged.connect(self._on_engine_mode_changed)
        self.engine_combo.installEventFilter(self._no_wheel_filter)
        api_layout.addRow("Translation Engine:", self.engine_combo)

        self.engine_note = QLabel("")
        self.engine_note.setStyleSheet("color: #94a3b8; font-size: 11px;")
        self.engine_note.setWordWrap(True)
        api_layout.addRow("", self.engine_note)

        # Provider Preset selector
        self.provider_combo = QComboBox()
        for p_name in PROVIDER_PRESETS.keys():
            self.provider_combo.addItem(p_name)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self.provider_combo.installEventFilter(self._no_wheel_filter)
        api_layout.addRow("Service / Provider:", self.provider_combo)

        # API Protocol selector
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItem("OpenAI Compatible", "openai")
        self.protocol_combo.addItem("Anthropic Claude", "anthropic")
        self.protocol_combo.installEventFilter(self._no_wheel_filter)
        api_layout.addRow("API Protocol:", self.protocol_combo)

        # Model Preset dropdown
        self.model_combo = QComboBox()
        self.model_combo.currentIndexChanged.connect(self._on_model_combo_changed)
        self.model_combo.installEventFilter(self._no_wheel_filter)
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
        self.timeout_spin.setRange(300, 1200)
        self.timeout_spin.setValue(300)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setToolTip("Request timeout in seconds (Minimum: 300s, Default: 300s)")
        self.timeout_spin.installEventFilter(self._no_wheel_filter)
        api_layout.addRow("Timeout (Seconds):", self.timeout_spin)

        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 5)
        self.retries_spin.setValue(3)
        self.retries_spin.setSuffix(" retries")
        self.retries_spin.setToolTip("Maximum retry attempts on network error or HTTP 524 (Default: 3)")
        self.retries_spin.installEventFilter(self._no_wheel_filter)
        api_layout.addRow("Max Retries:", self.retries_spin)

        # Multimodal Vision Settings
        self.vision_scale_combo = QComboBox()
        self.vision_scale_combo.addItem("50% (Recommended for Speed)", 50)
        self.vision_scale_combo.addItem("75% (Balanced Quality)", 75)
        self.vision_scale_combo.addItem("100% (Original Resolution)", 100)
        self.vision_scale_combo.installEventFilter(self._no_wheel_filter)
        api_layout.addRow("WebP Image Scale:", self.vision_scale_combo)

        self.vision_quality_combo = QComboBox()
        self.vision_quality_combo.addItem("Low (Quality 50)", 50)
        self.vision_quality_combo.addItem("Medium (Quality 75)", 75)
        self.vision_quality_combo.addItem("High (Quality 90)", 90)
        self.vision_quality_combo.installEventFilter(self._no_wheel_filter)
        api_layout.addRow("WebP Quality:", self.vision_quality_combo)

        # Bottom Actions Row inside Settings
        action_row = QHBoxLayout()
        self.save_status_label = QLabel("")
        self.save_status_label.setStyleSheet("color: #4ade80; font-size: 12px; font-weight: 500;")
        action_row.addWidget(self.save_status_label)
        action_row.addStretch()

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setObjectName("saveBtn")
        self.save_btn.clicked.connect(self._on_save)
        action_row.addWidget(self.save_btn)
        api_layout.addRow("", action_row)

        scroll.setWidget(api_container)
        layout.addWidget(scroll)

    def _on_provider_changed(self, index: int):
        new_provider = self.provider_combo.currentText()
        if not new_provider:
            return

        if self._current_provider:
            self._provider_cache[self._current_provider] = {
                "api_key": self.api_key_input.text().strip(),
                "base_url": self.base_url_input.text().strip(),
                "model": self.model_input.text().strip(),
                "protocol": self.protocol_combo.currentData() or "openai"
            }

        self._current_provider = new_provider
        preset = PROVIDER_PRESETS.get(new_provider, {})
        placeholder = preset.get("key_placeholder", "API Key...")
        self.api_key_input.setPlaceholderText(placeholder)

        cached = self._provider_cache.get(new_provider)
        if cached is None:
            slug = _provider_slug(new_provider)
            saved_key = self.settings.value(f"provider_cache/{slug}/api_key", "", type=str)
            saved_url = self.settings.value(f"provider_cache/{slug}/base_url", preset.get("base_url", ""), type=str)
            saved_model = self.settings.value(f"provider_cache/{slug}/model", "", type=str)
            saved_proto = self.settings.value(f"provider_cache/{slug}/protocol", preset.get("protocol", "openai"), type=str)
            models = preset.get("models", [])
            cached = {
                "api_key": saved_key,
                "base_url": saved_url or preset.get("base_url", ""),
                "model": saved_model or (models[0] if models else ""),
                "protocol": saved_proto
            }
            self._provider_cache[new_provider] = cached

        self.api_key_input.setText(cached.get("api_key", ""))
        self.base_url_input.setText(cached.get("base_url", ""))
        self.model_input.setText(cached.get("model", ""))

        proto = cached.get("protocol") or preset.get("protocol", "openai")
        p_idx = self.protocol_combo.findData(proto)
        if p_idx >= 0:
            self.protocol_combo.setCurrentIndex(p_idx)

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        models = preset.get("models", [])
        if models:
            for m in models:
                self.model_combo.addItem(m)
            cached_model = cached.get("model", "")
            m_idx = self.model_combo.findText(cached_model)
            if m_idx >= 0:
                self.model_combo.setCurrentIndex(m_idx)
            else:
                if cached_model:
                    self.model_combo.addItem(cached_model)
                    self.model_combo.setCurrentText(cached_model)
                else:
                    self.model_combo.setCurrentIndex(0)
        else:
            self.model_combo.addItem("(Custom)")
        self.model_combo.blockSignals(False)

    def _on_model_combo_changed(self, index: int):
        text = self.model_combo.currentText()
        if text and text != "(Custom)":
            self.model_input.setText(text)

    def _on_engine_mode_changed(self, index: int = 0):
        mode = self.engine_combo.currentData()
        is_multimodal = (mode == "multimodal")
        self.vision_scale_combo.setEnabled(is_multimodal and not self.is_queue_running)
        self.vision_quality_combo.setEnabled(is_multimodal and not self.is_queue_running)

        if is_multimodal:
            self.engine_note.setText(
                "Highest Quality mode combines exact local ONNX/OpenCV bubble contours with Multimodal LLM reading, "
                "achieving contextual character translation without coordinate drift."
            )
        else:
            self.engine_note.setText(
                "Token-Efficient mode runs text detection (ONNX) and OCR (Manga OCR) locally, sending only extracted dialogue "
                "text to the LLM to minimize token consumption."
            )

    def _load_settings(self):
        active_provider = self.settings.value("llm_provider", "Google Gemini (Official)", type=str)
        active_api_key = self.settings.value("llm_api_key", "", type=str)
        active_base_url = self.settings.value("llm_base_url", "https://generativelanguage.googleapis.com/v1beta/openai/", type=str)
        active_model = self.settings.value("llm_model", "gemini-2.5-flash", type=str)
        active_protocol = self.settings.value("llm_protocol", "openai", type=str)

        self._provider_cache = {}
        for p_name, p_data in PROVIDER_PRESETS.items():
            slug = _provider_slug(p_name)
            cached_key = self.settings.value(f"provider_cache/{slug}/api_key", "", type=str)
            cached_url = self.settings.value(f"provider_cache/{slug}/base_url", p_data["base_url"], type=str)
            cached_model = self.settings.value(f"provider_cache/{slug}/model", "", type=str)
            cached_proto = self.settings.value(f"provider_cache/{slug}/protocol", p_data.get("protocol", "openai"), type=str)
            self._provider_cache[p_name] = {
                "api_key": cached_key,
                "base_url": cached_url,
                "model": cached_model or (p_data["models"][0] if p_data["models"] else ""),
                "protocol": cached_proto
            }

        matched_provider = active_provider
        if matched_provider not in PROVIDER_PRESETS:
            matched_provider = "Custom / Other"
            for p_name, p_data in PROVIDER_PRESETS.items():
                if p_name == "Custom / Other":
                    continue
                if p_data["base_url"].rstrip("/") == active_base_url.rstrip("/"):
                    matched_provider = p_name
                    break

        self._provider_cache[matched_provider]["api_key"] = active_api_key
        self._provider_cache[matched_provider]["base_url"] = active_base_url
        self._provider_cache[matched_provider]["model"] = active_model
        self._provider_cache[matched_provider]["protocol"] = active_protocol

        self._current_provider = matched_provider

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

        proto = active_protocol or preset.get("protocol", "openai")
        p_idx = self.protocol_combo.findData(proto)
        if p_idx >= 0:
            self.protocol_combo.setCurrentIndex(p_idx)

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

        timeout_val = self.settings.value("llm_timeout_seconds", 300, type=int)
        self.timeout_spin.setValue(timeout_val if timeout_val >= 300 else 300)

        retries_val = self.settings.value("llm_max_retries", 3, type=int)
        self.retries_spin.setValue(max(1, min(5, retries_val)))

        engine_val = self.settings.value("llm_engine_mode", "hybrid", type=str)
        e_idx = self.engine_combo.findData(engine_val)
        if e_idx >= 0:
            self.engine_combo.setCurrentIndex(e_idx)
        else:
            self.engine_combo.setCurrentIndex(0)

        scale_val = self.settings.value("llm_vision_scale_pct", 75, type=int)
        s_idx = self.vision_scale_combo.findData(scale_val)
        if s_idx >= 0:
            self.vision_scale_combo.setCurrentIndex(s_idx)
        else:
            self.vision_scale_combo.setCurrentIndex(1)

        qual_val = self.settings.value("llm_vision_quality", 75, type=int)
        q_idx = self.vision_quality_combo.findData(qual_val)
        if q_idx >= 0:
            self.vision_quality_combo.setCurrentIndex(q_idx)
        else:
            self.vision_quality_combo.setCurrentIndex(1)

        self._on_engine_mode_changed(self.engine_combo.currentIndex())

        if self.is_queue_running:
            self.set_queue_running(True)

    def set_queue_running(self, running: bool):
        self.is_queue_running = running
        self.engine_combo.setEnabled(not running)
        is_multimodal = (self.engine_combo.currentData() == "multimodal")
        self.vision_scale_combo.setEnabled(not running and is_multimodal)
        self.vision_quality_combo.setEnabled(not running and is_multimodal)
        self.provider_combo.setEnabled(not running)
        self.protocol_combo.setEnabled(not running)
        self.model_combo.setEnabled(not running)
        self.api_key_input.setEnabled(not running)
        self.base_url_input.setEnabled(not running)
        self.model_input.setEnabled(not running)
        self.timeout_spin.setEnabled(not running)
        self.retries_spin.setEnabled(not running)
        self.save_btn.setEnabled(not running)
        if hasattr(self, "running_notice"):
            self.running_notice.setVisible(running)

    def _on_save(self):
        curr_provider = self.provider_combo.currentText()
        self._provider_cache[curr_provider] = {
            "api_key": self.api_key_input.text().strip(),
            "base_url": self.base_url_input.text().strip(),
            "model": self.model_input.text().strip(),
            "protocol": self.protocol_combo.currentData() or "openai"
        }

        self.settings.setValue("llm_engine_mode", self.engine_combo.currentData())
        self.settings.setValue("llm_vision_scale_pct", self.vision_scale_combo.currentData())
        self.settings.setValue("llm_vision_quality", self.vision_quality_combo.currentData())
        self.settings.setValue("llm_provider", curr_provider)
        self.settings.setValue("llm_protocol", self.protocol_combo.currentData() or "openai")
        self.settings.setValue("llm_api_key", self.api_key_input.text().strip())
        self.settings.setValue("llm_base_url", self.base_url_input.text().strip())
        self.settings.setValue("llm_model", self.model_input.text().strip())
        self.settings.setValue("llm_timeout_seconds", self.timeout_spin.value())
        self.settings.setValue("llm_max_retries", self.retries_spin.value())
        self.settings.setValue("llm_batch_size", 0)

        for p_name, data in self._provider_cache.items():
            slug = _provider_slug(p_name)
            self.settings.setValue(f"provider_cache/{slug}/api_key", data.get("api_key", ""))
            self.settings.setValue(f"provider_cache/{slug}/base_url", data.get("base_url", ""))
            self.settings.setValue(f"provider_cache/{slug}/model", data.get("model", ""))
            self.settings.setValue(f"provider_cache/{slug}/protocol", data.get("protocol", "openai"))

        self.save_status_label.setText("Settings saved successfully.")


class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings: Optional[QSettings] = None, is_queue_running: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(560, 520)
        self.resize(580, 560)

        self.settings = settings or QSettings("FolderImagePreviewer", "FolderImagePreviewer")
        self.is_queue_running = is_queue_running

        self._init_ui()
        self._set_icon()
        if self.is_queue_running:
            self.set_queue_running(True)

    def __getattr__(self, name):
        if hasattr(self, "settings_widget") and hasattr(self.settings_widget, name):
            return getattr(self.settings_widget, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

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
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.tab_widget = QTabWidget()

        # Tab 1: API & Translation
        self.settings_widget = ApiTranslationSettingsWidget(
            parent=self, settings=self.settings, is_queue_running=self.is_queue_running
        )
        self.tab_widget.addTab(self.settings_widget, "API && Translation")

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

    def set_queue_running(self, running: bool):
        self.is_queue_running = running
        self.settings_widget.set_queue_running(running)
        if hasattr(self, "save_btn"):
            self.save_btn.setEnabled(not running)

    def _on_save(self):
        self.settings_widget._on_save()
        self.accept()
