from pathlib import Path
import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent, QIcon

INVALID_CHARS = {'<', '>', ':', '"', '/', '\\', '|', '?', '*'}

class RenameTextEdit(QPlainTextEdit):
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
            else:
                window = self.window()
                if isinstance(window, QDialog) and getattr(window, "ok_btn", None) and window.ok_btn.isEnabled():
                    window.accept()
                return
        elif event.key() == Qt.Key.Key_Escape:
            window = self.window()
            if isinstance(window, QDialog):
                window.reject()
            return
        super().keyPressEvent(event)

class RenameDialog(QDialog):
    def __init__(self, current_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename Folder")
        self.setMinimumSize(560, 240)
        self.resize(600, 260)
        self.current_name = current_name
        self._init_ui()
        self._set_icon()

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
            QLabel {
                color: #cbd5e1;
                font-size: 13px;
            }
            QPlainTextEdit {
                background-color: #26262a;
                color: #ffffff;
                border: 1.5px solid #475569;
                border-radius: 6px;
                padding: 12px;
                font-size: 14px;
                line-height: 1.4;
                selection-background-color: #0284c7;
            }
            QPlainTextEdit:focus {
                border: 1.5px solid #38bdf8;
                background-color: #2a2a2e;
            }
            QPushButton {
                padding: 8px 20px;
                border-radius: 5px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton#btnOk {
                background-color: #0284c7;
                color: white;
                border: none;
            }
            QPushButton#btnOk:hover {
                background-color: #0369a1;
            }
            QPushButton#btnOk:disabled {
                background-color: #334155;
                color: #64748b;
            }
            QPushButton#btnCancel {
                background-color: #334155;
                color: #e2e8f0;
                border: none;
            }
            QPushButton#btnCancel:hover {
                background-color: #475569;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header
        header_label = QLabel("<b>Enter new folder name:</b>")
        header_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(header_label)

        # Large Text Box
        self.text_edit = RenameTextEdit()
        self.text_edit.setPlainText(self.current_name)
        self.text_edit.selectAll()
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit, 1)

        # Validation & Info Row
        info_row = QHBoxLayout()
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #f87171; font-size: 12px; font-weight: bold;")
        info_row.addWidget(self.warning_label, 1)

        self.char_count_label = QLabel(f"{len(self.current_name)} chars")
        self.char_count_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        info_row.addWidget(self.char_count_label)
        layout.addLayout(info_row)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("btnCancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton("Rename (Enter)")
        self.ok_btn.setObjectName("btnOk")
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)

    def _on_text_changed(self):
        text = self.get_new_name()
        self.char_count_label.setText(f"{len(text)} chars")

        invalid_found = [c for c in text if c in INVALID_CHARS]
        if invalid_found:
            chars_str = " ".join(sorted(set(invalid_found)))
            self.warning_label.setText(f"Invalid character(s): {chars_str}")
            self.ok_btn.setEnabled(False)
        elif not text:
            self.warning_label.setText("Folder name cannot be empty")
            self.ok_btn.setEnabled(False)
        else:
            self.warning_label.setText("")
            self.ok_btn.setEnabled(True)

    def get_new_name(self) -> str:
        raw = self.text_edit.toPlainText()
        return " ".join(raw.splitlines()).strip()
