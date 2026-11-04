from pathlib import Path
import sys
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTabWidget, QWidget,
    QFormLayout
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QIcon
from src.version import __version__, BUILD

class SettingsDialog(QDialog):
    def __init__(self, parent=None, settings: Optional[QSettings] = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 320)
        self.resize(540, 340)

        self.settings = settings or QSettings("FolderImagePreviewer", "FolderImagePreviewer")
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
            QLineEdit {
                background-color: #1e1e24;
                color: #f8fafc;
                border: 1.5px solid #475569;
                border-radius: 5px;
                padding: 7px 10px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1.5px solid #38bdf8;
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
            QPushButton#saveBtn {
                background-color: #0284c7;
                border: 1px solid #38bdf8;
            }
            QPushButton#saveBtn:hover {
                background-color: #0369a1;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        self.tab_widget = QTabWidget()

        # Tab 1: API & Translation Protocol
        api_tab = QWidget()
        api_layout = QFormLayout(api_tab)
        api_layout.setContentsMargins(16, 20, 16, 20)
        api_layout.setSpacing(14)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("sk-...")
        api_layout.addRow("API Key:", self.api_key_input)

        self.base_url_input = QLineEdit()
        self.base_url_input.setPlaceholderText("https://api.openai.com/v1")
        api_layout.addRow("Endpoint / Base URL:", self.base_url_input)

        self.model_input = QLineEdit()
        self.model_input.setPlaceholderText("gpt-4o-mini")
        api_layout.addRow("Model Name:", self.model_input)

        self.tab_widget.addTab(api_tab, "API & Translation")

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

        self.tab_widget.addTab(version_tab, "Version & About")
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

    def _load_settings(self):
        api_key = self.settings.value("llm_api_key", "", type=str)
        base_url = self.settings.value("llm_base_url", "https://api.openai.com/v1", type=str)
        model = self.settings.value("llm_model", "gpt-4o-mini", type=str)

        self.api_key_input.setText(api_key)
        self.base_url_input.setText(base_url)
        self.model_input.setText(model)

    def _on_save(self):
        self.settings.setValue("llm_api_key", self.api_key_input.text().strip())
        self.settings.setValue("llm_base_url", self.base_url_input.text().strip())
        self.settings.setValue("llm_model", self.model_input.text().strip())
        self.accept()
