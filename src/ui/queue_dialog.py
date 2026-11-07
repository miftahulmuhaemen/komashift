import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QWidget,
    QProgressBar, QSplitter, QTabWidget, QTextEdit, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from src.models.translation_job import TranslationJob, JobStatus
from src.services.translation_queue import TranslationQueueManager


class JobListItemWidget(QWidget):
    """Custom item display for a translation job in the queue list."""
    def __init__(self, job: TranslationJob, on_remove=None, parent=None):
        super().__init__(parent)
        self.job = job
        self.on_remove = on_remove
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # Top row: Folder title + Lang Badge + Remove button
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.title_label = QLabel(self.job.folder_name)
        self.title_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #f8fafc;")
        top_row.addWidget(self.title_label, 1)

        # Language badge
        lang_bg = "#0369a1" if self.job.lang_display == "EN" else "#047857"
        self.lang_badge = QLabel(f" {self.job.lang_display} ")
        self.lang_badge.setStyleSheet(
            f"background-color: {lang_bg}; color: #f8fafc; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 5px;"
        )
        top_row.addWidget(self.lang_badge)

        # Status badge
        self.status_badge = QLabel()
        top_row.addWidget(self.status_badge)

        if self.on_remove:
            self.remove_btn = QPushButton("✕")
            self.remove_btn.setFixedSize(22, 22)
            self.remove_btn.setToolTip("Remove from queue")
            self.remove_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #94a3b8;
                    border: none;
                    font-size: 12px;
                    font-weight: bold;
                    border-radius: 11px;
                }
                QPushButton:hover {
                    background-color: #ef4444;
                    color: #ffffff;
                }
            """)
            self.remove_btn.clicked.connect(lambda: self.on_remove(self.job.id))
            top_row.addWidget(self.remove_btn)

        layout.addLayout(top_row)

        # Middle: Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e24;
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #38bdf8;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # Bottom row: Status message
        self.msg_label = QLabel()
        self.msg_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
        layout.addWidget(self.msg_label)

        self.update_data()

    def update_data(self):
        self.title_label.setText(self.job.folder_name)
        self.progress_bar.setValue(self.job.progress_pct)
        self.msg_label.setText(self.job.status_message)

        if self.job.status == JobStatus.COMPLETED:
            self.status_badge.setText(" Done ")
            self.status_badge.setStyleSheet("background-color: #15803d; color: #f0fdf4; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 4px;")
            self.progress_bar.setStyleSheet("QProgressBar { background-color: #1e1e24; border-radius: 3px; } QProgressBar::chunk { background-color: #22c55e; border-radius: 3px; }")
        elif self.job.status == JobStatus.RUNNING:
            self.status_badge.setText(f" {self.job.progress_pct}% ")
            self.status_badge.setStyleSheet("background-color: #0284c7; color: #f0f9ff; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 4px;")
            self.progress_bar.setStyleSheet("QProgressBar { background-color: #1e1e24; border-radius: 3px; } QProgressBar::chunk { background-color: #38bdf8; border-radius: 3px; }")
        elif self.job.status == JobStatus.FAILED:
            self.status_badge.setText(" Failed ")
            self.status_badge.setStyleSheet("background-color: #b91c1c; color: #fef2f2; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 4px;")
            self.progress_bar.setStyleSheet("QProgressBar { background-color: #1e1e24; border-radius: 3px; } QProgressBar::chunk { background-color: #ef4444; border-radius: 3px; }")
        else:
            self.status_badge.setText(" Pending ")
            self.status_badge.setStyleSheet("background-color: #334155; color: #cbd5e1; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 4px;")
            self.progress_bar.setStyleSheet("QProgressBar { background-color: #1e1e24; border-radius: 3px; } QProgressBar::chunk { background-color: #64748b; border-radius: 3px; }")


class QueueDialog(QDialog):
    """Handbrake-style Queue Management Dialog."""
    def __init__(self, queue_manager: TranslationQueueManager, parent=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self.setWindowTitle("Translation Queue")
        self.setMinimumSize(780, 520)
        self.resize(860, 560)

        self._set_icon()
        self._init_ui()
        self._connect_signals()
        self._refresh_list()
        self._update_controls()

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
                background-color: #18181b;
                color: #f1f5f9;
            }
            QListWidget {
                background-color: #1e1e24;
                border: 1px solid #334155;
                border-radius: 6px;
                outline: none;
            }
            QListWidget::item {
                border-bottom: 1px solid #27272a;
            }
            QListWidget::item:selected {
                background-color: #27272a;
            }
            QTabWidget::pane {
                border: 1px solid #334155;
                background-color: #1e1e24;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #18181b;
                color: #94a3b8;
                padding: 6px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-weight: 500;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: #1e1e24;
                color: #38bdf8;
                border-bottom: 2px solid #38bdf8;
            }
            QTextEdit {
                background-color: #141417;
                color: #e2e8f0;
                border: none;
                font-family: Consolas, monospace;
                font-size: 12px;
                padding: 8px;
            }
            QPushButton {
                background-color: #27272a;
                color: #f8fafc;
                border: 1px solid #3f3f46;
                padding: 6px 14px;
                border-radius: 5px;
                font-size: 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3f3f46;
            }
            QPushButton:disabled {
                background-color: #18181b;
                color: #52525b;
                border: 1px solid #27272a;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Top Bar: Title + Controls
        top_bar = QHBoxLayout()

        header_layout = QVBoxLayout()
        header_title = QLabel("Queue")
        header_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #f8fafc;")
        header_layout.addWidget(header_title)

        self.pending_label = QLabel("0 jobs pending")
        self.pending_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        header_layout.addWidget(self.pending_label)
        top_bar.addLayout(header_layout)

        top_bar.addStretch()

        self.start_btn = QPushButton("▶ Start Queue")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self._toggle_queue)
        top_bar.addWidget(self.start_btn)

        self.clear_btn = QPushButton("🗑 Clear Completed")
        self.clear_btn.clicked.connect(self.queue_manager.clear_completed)
        top_bar.addWidget(self.clear_btn)

        layout.addLayout(top_bar)

        # Main Splitter: Left = Job List, Right = Details Tab
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left List
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_job_selected)
        splitter.addWidget(self.list_widget)

        # Right Tabbed Inspector
        self.tab_widget = QTabWidget()

        # Tab 1: Summary
        summary_widget = QWidget()
        summary_layout = QVBoxLayout(summary_widget)
        summary_layout.setContentsMargins(14, 14, 14, 14)
        summary_layout.setSpacing(10)

        self.summary_text = QLabel("Select a job from the list to view its summary.")
        self.summary_text.setWordWrap(True)
        self.summary_text.setStyleSheet("color: #cbd5e1; font-size: 13px; line-height: 1.5;")
        summary_layout.addWidget(self.summary_text)
        summary_layout.addStretch()
        self.tab_widget.addTab(summary_widget, "Summary")

        # Tab 2: Activity Log
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.tab_widget.addTab(self.log_edit, "Activity Log")

        splitter.addWidget(self.tab_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter, 1)

        # Bottom row
        bottom_bar = QHBoxLayout()
        self.status_label = QLabel("Idle")
        self.status_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        bottom_bar.addWidget(self.status_label)

        bottom_bar.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        bottom_bar.addWidget(self.close_btn)

        layout.addLayout(bottom_bar)

    def _connect_signals(self):
        self.queue_manager.queue_updated.connect(self._refresh_list)
        self.queue_manager.queue_state_changed.connect(self._update_controls)
        self.queue_manager.job_progress.connect(self._on_job_progress)
        self.queue_manager.job_finished.connect(self._on_job_finished)

    def _toggle_queue(self):
        if self.queue_manager.is_running:
            self.queue_manager.pause_queue()
        else:
            self.queue_manager.start_queue()
        self._update_controls()

    def _update_controls(self):
        is_running = self.queue_manager.is_running
        pending = self.queue_manager.pending_count

        if is_running:
            self.start_btn.setText("⏸ Pause Queue")
            self.start_btn.setEnabled(True)
        else:
            self.start_btn.setText("▶ Start Queue")
            self.start_btn.setEnabled(pending > 0 or any(j.status == JobStatus.FAILED for j in self.queue_manager.jobs))
        self.pending_label.setText(f"{pending} jobs pending")

        active = self.queue_manager.active_job
        if is_running and active:
            self.status_label.setText(f"Processing: {active.folder_name} ({active.progress_pct}%)")
        else:
            self.status_label.setText("Idle" if not is_running else "Finishing...")

    def _refresh_list(self):
        current_row = self.list_widget.currentRow()
        self.list_widget.clear()

        for job in self.queue_manager.jobs:
            item = QListWidgetItem(self.list_widget)
            widget = JobListItemWidget(job, on_remove=self.queue_manager.remove_job)
            item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, widget)

        if 0 <= current_row < self.list_widget.count():
            self.list_widget.setCurrentRow(current_row)
        elif self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        self._update_controls()
        self._update_inspector()

    def _on_job_selected(self, row: int):
        self._update_inspector()

    def _update_inspector(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.queue_manager.jobs):
            self.summary_text.setText("Select a job from the list to view its summary.")
            self.log_edit.clear()
            return

        job = self.queue_manager.jobs[row]
        lang_name = "Indonesian (ID)" if job.lang_display == "ID" else "English (EN)"
        err_block = f"<p style='color: #ef4444;'><b>Error:</b> {job.error_message}</p>" if job.error_message else ""

        html = f"""
        <h3 style='margin: 0; color: #38bdf8;'>{job.folder_name}</h3>
        <p><b>Target Language:</b> {lang_name}<br>
        <b>Folder Path:</b> {job.folder_path}<br>
        <b>Total Pages:</b> {len(job.image_paths)} pages<br>
        <b>Status:</b> {job.status.value.upper()}<br>
        <b>Progress:</b> {job.progress_pct}% ({job.progress_current}/{job.progress_total})<br>
        <b>Message:</b> {job.status_message}</p>
        {err_block}
        """
        self.summary_text.setText(html)

        # Load log file if present
        log_file = job.folder_path / "temp" / "translation.log"
        if log_file.exists():
            try:
                self.log_edit.setPlainText(log_file.read_text(encoding="utf-8", errors="replace"))
                self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
            except Exception:
                self.log_edit.setPlainText("(Could not read log file)")
        else:
            self.log_edit.setPlainText("(No logs available yet for this job)")

    def _on_job_progress(self, job_id: str, message: str, current: int, total: int):
        self._refresh_list_item(job_id)
        self._update_controls()
        # If currently selected job is active, update log/summary
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.queue_manager.jobs) and self.queue_manager.jobs[row].id == job_id:
            self._update_inspector()

    def _on_job_finished(self, job_id: str, success: bool, message: str):
        self._refresh_list_item(job_id)
        self._update_controls()
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.queue_manager.jobs) and self.queue_manager.jobs[row].id == job_id:
            self._update_inspector()

    def _refresh_list_item(self, job_id: str):
        for idx in range(self.list_widget.count()):
            item = self.list_widget.item(idx)
            widget = self.list_widget.itemWidget(item)
            if isinstance(widget, JobListItemWidget) and widget.job.id == job_id:
                widget.update_data()
                break
