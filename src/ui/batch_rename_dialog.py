import re
import sys
from pathlib import Path
from typing import List, Tuple
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QColor
from src.models.folder_item import FolderItem

INVALID_CHARS = {'<', '>', ':', '"', '/', '\\', '|', '?', '*'}

class BatchRenameDialog(QDialog):
    def __init__(self, folders: List[FolderItem], parent=None):
        super().__init__(parent)
        self.folders = folders
        self._original_names = [f.name for f in folders]
        self._new_names = [f.name for f in folders]
        self._head_trimmed = [[] for _ in folders]
        self._tail_trimmed = [[] for _ in folders]

        self.setWindowTitle(f"Batch Rename Folders ({len(folders)} folders)")
        self.setMinimumSize(780, 480)
        self.resize(850, 540)
        self._init_ui()
        self._set_icon()
        self._refresh_table()

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
            QGroupBox {
                border: 1px solid #3b4252;
                border-radius: 6px;
                margin-top: 10px;
                padding: 10px;
                font-weight: bold;
                color: #94a3b8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #38bdf8;
            }
            QLineEdit {
                background-color: #2b2d35;
                color: #ffffff;
                border: 1px solid #4c566a;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #38bdf8;
            }
            QPushButton {
                padding: 6px 14px;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
                background-color: #334155;
                color: #e2e8f0;
                border: none;
            }
            QPushButton:hover {
                background-color: #475569;
            }
            QPushButton:pressed {
                background-color: #1e293b;
            }
            QPushButton#btnArrow {
                background-color: #2b2d35;
                border: 1px solid #4c566a;
                color: #f8fafc;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 10px;
                min-width: 28px;
                max-width: 34px;
                min-height: 24px;
            }
            QPushButton#btnArrow:hover {
                background-color: #0284c7;
                border: 1px solid #0284c7;
                color: white;
            }
            QPushButton#btnQuickTool {
                background-color: #1e293b;
                border: 1px solid #475569;
                color: #38bdf8;
            }
            QPushButton#btnQuickTool:hover {
                background-color: #0284c7;
                color: white;
                border: 1px solid #0284c7;
            }
            QTableWidget {
                background-color: #26262a;
                color: #f1f5f9;
                gridline-color: #3b4252;
                border: 1px solid #3b4252;
                border-radius: 6px;
                font-size: 13px;
                selection-background-color: #0284c7;
            }
            QHeaderView::section {
                background-color: #18181b;
                color: #94a3b8;
                padding: 6px;
                border: 1px solid #3b4252;
                font-weight: bold;
            }
            QPushButton#btnOk {
                background-color: #0284c7;
                color: white;
                font-size: 13px;
                padding: 8px 22px;
                font-weight: bold;
            }
            QPushButton#btnOk:hover {
                background-color: #0369a1;
            }
            QPushButton#btnOk:disabled {
                background-color: #334155;
                color: #64748b;
            }
            QPushButton#btnCancel {
                padding: 8px 18px;
                font-size: 13px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        # Header Info Row
        header_layout = QHBoxLayout()
        header_label = QLabel(f"<b>Batch Rename {len(self.folders)} Folder(s)</b>")
        header_label.setStyleSheet("font-size: 14px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()

        self.reset_btn = QPushButton("↺ Reset All to Original")
        self.reset_btn.setToolTip("Revert all names back to original")
        self.reset_btn.clicked.connect(self.reset_original)
        header_layout.addWidget(self.reset_btn)
        layout.addLayout(header_layout)

        # Quick Transform Tools Group
        tools_group = QGroupBox("Quick Transform Tools")
        tools_layout = QVBoxLayout(tools_group)
        tools_layout.setSpacing(8)

        # Row 1: Head Controls
        head_row = QHBoxLayout()
        head_label = QLabel("<b>Head:</b>")
        head_label.setFixedWidth(42)
        head_row.addWidget(head_label)

        self.btn_head_up = QPushButton("▲")
        self.btn_head_up.setObjectName("btnArrow")
        self.btn_head_up.setToolTip("Trim 1 character from the start")
        self.btn_head_up.clicked.connect(self.trim_head_one)
        head_row.addWidget(self.btn_head_up)

        self.btn_head_down = QPushButton("▼")
        self.btn_head_down.setObjectName("btnArrow")
        self.btn_head_down.setToolTip("Restore 1 character to the start")
        self.btn_head_down.clicked.connect(self.untrim_head_one)
        head_row.addWidget(self.btn_head_down)

        self.head_input = QLineEdit()
        self.head_input.setPlaceholderText("Prefix to add...")
        self.head_input.returnPressed.connect(self.add_head)
        head_row.addWidget(self.head_input, 1)

        self.add_head_btn = QPushButton("+ Add Head")
        self.add_head_btn.clicked.connect(self.add_head)
        head_row.addWidget(self.add_head_btn)

        self.strip_id_btn = QPushButton("⚡ Strip Leading ID")
        self.strip_id_btn.setObjectName("btnQuickTool")
        self.strip_id_btn.setToolTip("Automatically remove leading tags/IDs (e.g. 'nhentai-672171 - ' or '01. ')")
        self.strip_id_btn.clicked.connect(self.strip_leading_id)
        head_row.addWidget(self.strip_id_btn)

        tools_layout.addLayout(head_row)

        # Row 2: Tail Controls
        tail_row = QHBoxLayout()
        tail_label = QLabel("<b>Tail:</b>")
        tail_label.setFixedWidth(42)
        tail_row.addWidget(tail_label)

        self.btn_tail_up = QPushButton("▲")
        self.btn_tail_up.setObjectName("btnArrow")
        self.btn_tail_up.setToolTip("Trim 1 character from the end")
        self.btn_tail_up.clicked.connect(self.trim_tail_one)
        tail_row.addWidget(self.btn_tail_up)

        self.btn_tail_down = QPushButton("▼")
        self.btn_tail_down.setObjectName("btnArrow")
        self.btn_tail_down.setToolTip("Restore 1 character to the end")
        self.btn_tail_down.clicked.connect(self.untrim_tail_one)
        tail_row.addWidget(self.btn_tail_down)

        self.tail_input = QLineEdit()
        self.tail_input.setPlaceholderText("Suffix to add...")
        self.tail_input.returnPressed.connect(self.add_tail)
        tail_row.addWidget(self.tail_input, 1)

        self.add_tail_btn = QPushButton("+ Add Tail")
        self.add_tail_btn.clicked.connect(self.add_tail)
        tail_row.addWidget(self.add_tail_btn)

        self.strip_tail_btn = QPushButton("⚡ Strip Trailing Numbers")
        self.strip_tail_btn.setObjectName("btnQuickTool")
        self.strip_tail_btn.setToolTip("Automatically remove trailing numbers/brackets (e.g. ' (01)' or ' - 02')")
        self.strip_tail_btn.clicked.connect(self.strip_trailing_numbers)
        tail_row.addWidget(self.strip_tail_btn)

        tools_layout.addLayout(tail_row)
        layout.addWidget(tools_group)

        # Live Preview Table
        self.table = QTableWidget(len(self.folders), 2)
        self.table.setHorizontalHeaderLabels(["Original Name", "New Name"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_table_item_changed)
        layout.addWidget(self.table, 1)

        # Warning / Status Row
        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #f87171; font-size: 12px; font-weight: bold;")
        layout.addWidget(self.warning_label)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("btnCancel")
        self.cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancel_btn)

        self.ok_btn = QPushButton(f"Apply Rename ({len(self.folders)})")
        self.ok_btn.setObjectName("btnOk")
        self.ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.ok_btn)

        layout.addLayout(btn_layout)

    def _refresh_table(self):
        from collections import defaultdict
        self.table.blockSignals(True)

        name_indices = defaultdict(list)
        for i, new_n in enumerate(self._new_names):
            name_indices[new_n.strip().lower()].append(i)

        duplicate_rows = set()
        for indices in name_indices.values():
            if len(indices) > 1:
                duplicate_rows.update(indices)

        for row, (orig, new_n) in enumerate(zip(self._original_names, self._new_names)):
            orig_item = QTableWidgetItem(orig)
            orig_item.setFlags(orig_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            orig_item.setForeground(QColor("#94a3b8"))
            self.table.setItem(row, 0, orig_item)

            new_item = QTableWidgetItem(new_n)
            is_empty = not new_n.strip()
            is_invalid_chars = any(c in INVALID_CHARS for c in new_n)
            is_duplicate = row in duplicate_rows

            if is_empty:
                new_item.setForeground(QColor("#f87171"))
                new_item.setToolTip("Name cannot be empty")
            elif is_invalid_chars:
                new_item.setForeground(QColor("#f87171"))
                new_item.setToolTip("Contains invalid filename characters")
            elif is_duplicate:
                new_item.setForeground(QColor("#f87171"))
                other_rows = [str(idx + 1) for idx in name_indices[new_n.strip().lower()] if idx != row]
                new_item.setToolTip(f"Duplicate name (collides with Row {', '.join(other_rows)})")
            elif new_n != orig:
                new_item.setForeground(QColor("#38bdf8"))
                new_item.setToolTip("Changed from original")
            else:
                new_item.setForeground(QColor("#ffffff"))
                new_item.setToolTip("")

            self.table.setItem(row, 1, new_item)
        self.table.blockSignals(False)
        self._validate_names()

    def _on_table_item_changed(self, item: QTableWidgetItem):
        if item.column() == 1:
            row = item.row()
            if 0 <= row < len(self._new_names):
                self._new_names[row] = item.text().strip()
                self._refresh_table()

    def _validate_names(self):
        from collections import defaultdict
        errors = []
        has_changes = False

        name_indices = defaultdict(list)
        for i, new_n in enumerate(self._new_names):
            name_indices[new_n.strip().lower()].append(i)
            if new_n != self._original_names[i]:
                has_changes = True
            if not new_n.strip():
                errors.append(f"Row {i+1}: Name cannot be empty")
            invalid_found = [c for c in new_n if c in INVALID_CHARS]
            if invalid_found:
                chars_str = " ".join(sorted(set(invalid_found)))
                errors.append(f"Row {i+1}: Invalid character(s): {chars_str}")

        # Check duplicates
        for norm_name, indices in name_indices.items():
            if len(indices) > 1:
                rows_str = ", ".join(str(idx + 1) for idx in indices)
                disp_name = self._new_names[indices[0]].strip()
                if len(disp_name) > 30:
                    disp_name = disp_name[:27] + "..."
                errors.append(f'Duplicate "{disp_name}" in Rows {rows_str}')

        if errors:
            self.warning_label.setText(errors[0])
            self.ok_btn.setEnabled(False)
        elif not has_changes:
            self.warning_label.setText("No changes made yet")
            self.ok_btn.setEnabled(False)
        else:
            self.warning_label.setText("")
            self.ok_btn.setEnabled(True)

    def trim_head_one(self):
        for i in range(len(self._new_names)):
            if self._new_names[i]:
                self._head_trimmed[i].append(self._new_names[i][0])
                self._new_names[i] = self._new_names[i][1:]
        self._refresh_table()

    def untrim_head_one(self):
        for i in range(len(self._new_names)):
            if self._head_trimmed[i]:
                c = self._head_trimmed[i].pop()
                self._new_names[i] = c + self._new_names[i]
        self._refresh_table()

    def trim_tail_one(self):
        for i in range(len(self._new_names)):
            if self._new_names[i]:
                self._tail_trimmed[i].append(self._new_names[i][-1])
                self._new_names[i] = self._new_names[i][:-1]
        self._refresh_table()

    def untrim_tail_one(self):
        for i in range(len(self._new_names)):
            if self._tail_trimmed[i]:
                c = self._tail_trimmed[i].pop()
                self._new_names[i] = self._new_names[i] + c
        self._refresh_table()

    def add_head(self, prefix: str = None):
        p = prefix if isinstance(prefix, str) else self.head_input.text()
        if p:
            self._new_names = [p + name for name in self._new_names]
            self.head_input.clear()
            self._refresh_table()

    def add_tail(self, suffix: str = None):
        s = suffix if isinstance(suffix, str) else self.tail_input.text()
        if s:
            self._new_names = [name + s for name in self._new_names]
            self.tail_input.clear()
            self._refresh_table()

    def strip_leading_id(self):
        pattern = r"^(?:[a-zA-Z0-9_.-]+-\d+|\d+)\s*[-_–—:.]*\s*"
        self._new_names = [re.sub(pattern, "", name) for name in self._new_names]
        self._refresh_table()

    def strip_trailing_numbers(self):
        pattern = r"[\s._–—:-]*(?:\(\d+\)|\[\d+\]|\d+)$"
        self._new_names = [re.sub(pattern, "", name) for name in self._new_names]
        self._refresh_table()

    def reset_original(self):
        self._new_names = list(self._original_names)
        self._head_trimmed = [[] for _ in self.folders]
        self._tail_trimmed = [[] for _ in self.folders]
        self._refresh_table()

    def get_rename_pairs(self) -> List[Tuple[FolderItem, str]]:
        return [
            (folder, new_n)
            for folder, new_n in zip(self.folders, self._new_names)
            if new_n != folder.name and new_n.strip()
        ]
