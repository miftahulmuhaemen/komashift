from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel
)
from PyQt6.QtGui import QFont

class LogDialog(QDialog):
    def __init__(self, parent=None, log_path: Optional[Path] = None):
        super().__init__(parent)
        self.setWindowTitle("Translation Logs")
        self.setMinimumSize(680, 420)
        self.resize(720, 460)
        self.log_path = Path(log_path) if log_path else None
        self._init_ui()
        self.refresh_log()

    def _init_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e1e;
                color: #f1f5f9;
            }
            QTextEdit {
                background-color: #141418;
                color: #38bdf8;
                border: 1.5px solid #334155;
                border-radius: 6px;
                padding: 8px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
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
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.title_label = QLabel("Activity & Diagnostics Log:")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #cbd5e1;")
        layout.addWidget(self.title_label)

        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        layout.addWidget(self.log_text_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.clicked.connect(self.refresh_log)
        btn_layout.addWidget(self.refresh_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.close_btn)

        layout.addLayout(btn_layout)

    def refresh_log(self):
        if not self.log_path or not self.log_path.exists():
            self.log_text_edit.setPlainText("No log file found for the current chapter folder.\nRun translation to generate logs.")
            return

        try:
            content = self.log_path.read_text(encoding="utf-8")
            self.log_text_edit.setPlainText(content or "(Log file is empty)")
            # Auto scroll to bottom
            cursor = self.log_text_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.log_text_edit.setTextCursor(cursor)
        except Exception as e:
            self.log_text_edit.setPlainText(f"Error reading log file: {e}")
