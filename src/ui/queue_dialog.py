import logging
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QWidget,
    QProgressBar, QSplitter, QTabWidget, QTextEdit, QFrame,
    QMenu, QLineEdit, QSpinBox, QMessageBox, QComboBox, QApplication,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSettings, QPoint, QSize, QEvent
from PyQt6.QtGui import QIcon, QPixmap, QGuiApplication
from src.models.translation_job import TranslationJob, JobStatus, JobType
from src.services.translation_queue import TranslationQueueManager
from src.infra.json_workspace import JsonTempWorkspace as TranslationWorkspace
from src.infra.file_log_sink import FileLogSink
from src.services.scanner import natural_sort_key
from src.services.thumbnail_cache import create_thumbnail_pixmap
from src.ui.settings_dialog import ApiTranslationSettingsWidget
from src.ui.page_preview_popup import PageThumbnailHoverPopup
from src.infra.qt_threads import QueuePreflightWorker

logger = logging.getLogger(__name__)


class JobListItemWidget(QWidget):
    """Custom item display for a translation job in the queue list."""
    def __init__(self, job: TranslationJob, on_remove=None, parent=None):
        super().__init__(parent)
        self.job = job
        self.on_remove = on_remove
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self._init_ui()

    def sizeHint(self) -> QSize:
        return QSize(280, 78)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        # Row 1: Full-width Folder title + compact Remove button (or close icon)
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self.title_label = QLabel(self.job.folder_name)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title_label.setMinimumWidth(50)
        self.title_label.setStyleSheet("font-weight: 600; font-size: 13px; color: #f8fafc;")
        top_row.addWidget(self.title_label, 1)

        if self.on_remove:
            self.remove_btn = QPushButton("✕")
            self.remove_btn.setToolTip("Remove from queue")
            self.remove_btn.setFixedSize(20, 20)
            self.remove_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #71717a;
                    border: none;
                    font-size: 12px;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #ef4444;
                    color: #ffffff;
                }
            """)
            self.remove_btn.clicked.connect(lambda: self.on_remove(self.job.id))
            top_row.addWidget(self.remove_btn)

        layout.addLayout(top_row)

        # Row 2: Badges (Language/Type, Status) + Status Message (pages count / step)
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        # Type / Language badge
        if self.job.job_type == JobType.RASTERIZE:
            self.badge = QLabel(" RASTERIZE ")
            self.badge.setStyleSheet(
                "background-color: #7c3aed; color: #f8fafc; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 1px 4px;"
            )
        else:
            if self.job.lang_display == "Mix-Lang":
                lang_bg = "#d97706"
            elif self.job.lang_display == "ID":
                lang_bg = "#047857"
            else:
                lang_bg = "#0369a1"
            self.badge = QLabel(f" {self.job.lang_display} ")
            self.badge.setStyleSheet(
                f"background-color: {lang_bg}; color: #f8fafc; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 1px 4px;"
            )
        meta_row.addWidget(self.badge)

        # Status badge (Pending / 50% / Done / Failed)
        self.status_badge = QLabel()
        meta_row.addWidget(self.status_badge)

        # Status message label
        self.msg_label = QLabel()
        self.msg_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.msg_label.setMinimumWidth(50)
        self.msg_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
        meta_row.addWidget(self.msg_label, 1)

        layout.addLayout(meta_row)

        # Row 3: Progress bar (bounded so it never overflows)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(5)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress_bar.setMaximumWidth(280)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e24;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #38bdf8;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.update_data()

    def update_data(self):
        folder_title = self.job.folder_name
        self.setToolTip(folder_title)
        self.title_label.setToolTip(folder_title)
        self.title_label.setText(self.job.folder_name)
        self.progress_bar.setValue(self.job.progress_pct)
        page_info = f"{self.job.selected_count}/{self.job.total_count} pages"
        self.msg_label.setText(f"{self.job.status_message} ({page_info})")
        self.msg_label.setToolTip(f"{self.job.status_message} ({page_info})")

        if self.job.status == JobStatus.COMPLETED:
            self.status_badge.setText(" Done ")
            self.status_badge.setStyleSheet("background-color: #15803d; color: #f0fdf4; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 4px;")
            self.progress_bar.setStyleSheet("QProgressBar { background-color: #1e1e24; border-radius: 3px; } QProgressBar::chunk { background-color: #22c55e; border-radius: 3px; }")
        elif self.job.status == JobStatus.RUNNING:
            self.status_badge.setText(f" {self.job.progress_pct}% ")
            self.status_badge.setStyleSheet("background-color: #0284c7; color: #f0f9ff; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 4px;")
            self.progress_bar.setStyleSheet("QProgressBar { background-color: #1e1e24; border-radius: 3px; } QProgressBar::chunk { background-color: #38bdf8; border-radius: 3px; }")
        elif self.job.status == JobStatus.PAUSED:
            self.status_badge.setText(" Paused ")
            self.status_badge.setStyleSheet("background-color: #d97706; color: #fffbeb; font-size: 10px; font-weight: bold; border-radius: 3px; padding: 2px 4px;")
            self.progress_bar.setStyleSheet("QProgressBar { background-color: #1e1e24; border-radius: 3px; } QProgressBar::chunk { background-color: #f59e0b; border-radius: 3px; }")
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
    def __init__(self, queue_manager: TranslationQueueManager, parent=None, settings: Optional[QSettings] = None, thumbnail_cache=None):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self.settings = settings or QSettings("KomaShift", "KomaShift")
        self.thumbnail_cache = thumbnail_cache
        self._is_populating_pages = False
        self._preflight_worker: Optional[QueuePreflightWorker] = None
        self._last_inspected_job_id: Optional[str] = None
        self.setWindowTitle("Translation Queue")
        self.setMinimumSize(800, 560)
        self.resize(880, 600)

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
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            assets_dir = Path(sys._MEIPASS) / "assets"
        else:
            assets_dir = Path(__file__).resolve().parent.parent.parent / "assets"

        chk_checked = str(assets_dir / "checkbox_checked.png").replace("\\", "/")
        chk_disabled = str(assets_dir / "checkbox_checked_disabled.png").replace("\\", "/")

        dialog_qss = """
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
                padding: 4px 6px;
            }
            QListWidget::item:selected {
                background-color: #27272a;
            }
            QListWidget::indicator {
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1.5px solid #64748b;
                background-color: #18181b;
                margin-right: 6px;
            }
            QListWidget::indicator:hover {
                border-color: #38bdf8;
            }
            QListWidget::indicator:checked {
                border-color: #0284c7;
                background-color: #0284c7;
                image: url("__CHK_CHECKED__");
            }
            QListWidget::indicator:checked:disabled {
                border-color: #475569;
                background-color: #334155;
                image: url("__CHK_DISABLED__");
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
        """.replace("__CHK_CHECKED__", chk_checked).replace("__CHK_DISABLED__", chk_disabled)
        self.setStyleSheet(dialog_qss)

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

        self.start_btn = QPushButton("Start Queue")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.clicked.connect(self._toggle_queue)
        top_bar.addWidget(self.start_btn)

        self.clear_btn = QPushButton("Clear Completed")
        self.clear_btn.clicked.connect(self.queue_manager.clear_completed)
        top_bar.addWidget(self.clear_btn)

        layout.addLayout(top_bar)

        # Main Splitter: Left = Job List, Right = Details Tab
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left List
        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.currentRowChanged.connect(self._on_job_selected)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_list_context_menu)
        splitter.addWidget(self.list_widget)

        # Right Tabbed Inspector
        self.tab_widget = QTabWidget()
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Tab 1: Pages
        pages_widget = QWidget()
        pages_layout = QVBoxLayout(pages_widget)
        pages_layout.setContentsMargins(12, 12, 12, 12)
        pages_layout.setSpacing(8)

        pages_toolbar = QHBoxLayout()
        pages_toolbar.setSpacing(8)
        self.pages_count_label = QLabel("0 / 0 pages selected")
        self.pages_count_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #38bdf8;")
        pages_toolbar.addWidget(self.pages_count_label)
        pages_toolbar.addStretch()

        self.pages_sort_combo = QComboBox()
        self.pages_sort_combo.addItem("Sort: 1, 2, 3... (Asc)", "natural_asc")
        self.pages_sort_combo.addItem("Sort: 100, 99... (Desc)", "natural_desc")
        self.pages_sort_combo.addItem("Sort: Name (A-Z)", "alpha_asc")
        self.pages_sort_combo.addItem("Sort: Name (Z-A)", "alpha_desc")
        self.pages_sort_combo.addItem("Sort: Untranslated First", "untranslated_first")
        self.pages_sort_combo.addItem("Sort: Translated First", "translated_first")
        self.pages_sort_combo.setStyleSheet("""
            QComboBox {
                background-color: #27272a;
                color: #f8fafc;
                border: 1px solid #3f3f46;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 500;
            }
            QComboBox:hover {
                background-color: #3f3f46;
            }
            QComboBox::drop-down {
                border: none;
                width: 18px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e24;
                color: #f1f5f9;
                selection-background-color: #38bdf8;
                selection-color: #0f172a;
                border: 1px solid #334155;
            }
        """)
        self.pages_sort_combo.currentIndexChanged.connect(self._on_pages_sort_changed)
        pages_toolbar.addWidget(self.pages_sort_combo)

        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.clicked.connect(self._select_all_pages)
        pages_toolbar.addWidget(self.btn_select_all)

        self.btn_unselect_all = QPushButton("Unselect All")
        self.btn_unselect_all.clicked.connect(self._unselect_all_pages)
        pages_toolbar.addWidget(self.btn_unselect_all)

        pages_layout.addLayout(pages_toolbar)

        self.pages_list = QListWidget()
        self.pages_list.setMouseTracking(True)
        self.pages_list.viewport().setMouseTracking(True)
        self.pages_list.viewport().installEventFilter(self)
        self.pages_list.itemChanged.connect(self._on_page_item_changed)
        pages_layout.addWidget(self.pages_list, 1)

        self.hover_popup = PageThumbnailHoverPopup(parent=self, thumbnail_cache=self.thumbnail_cache)

        self.tab_widget.addTab(pages_widget, "Pages")

        # Tab 2: Summary
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

        # Tab 3: Activity Log with Clear Logs button
        activity_widget = QWidget()
        activity_layout = QVBoxLayout(activity_widget)
        activity_layout.setContentsMargins(12, 12, 12, 12)
        activity_layout.setSpacing(6)

        activity_toolbar = QHBoxLayout()
        activity_toolbar.addStretch()
        self.clear_logs_btn = QPushButton("Clear Logs")
        self.clear_logs_btn.setStyleSheet("""
            QPushButton {
                background-color: #27272a;
                color: #cbd5e1;
                border: 1px solid #3f3f46;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                color: #f8fafc;
            }
        """)
        self.clear_logs_btn.clicked.connect(self._on_clear_logs)
        activity_toolbar.addWidget(self.clear_logs_btn)
        activity_layout.addLayout(activity_toolbar)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        activity_layout.addWidget(self.log_edit, 1)
        self.tab_widget.addTab(activity_widget, "Activity Log")

        # Tab 4: API & Translation (use && so Qt renders literal '&' without mnemonic underline)
        self.settings_widget = ApiTranslationSettingsWidget(
            parent=self,
            settings=self.settings,
            is_queue_running=self.queue_manager.is_running,
            queue_manager=self.queue_manager,
        )
        self.tab_widget.addTab(self.settings_widget, "API && Translation")

        splitter.addWidget(self.tab_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([320, 560])

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
        self.queue_manager.queue_state_changed.connect(self.settings_widget.set_queue_running)
        self.queue_manager.job_progress.connect(self._on_job_progress)
        self.queue_manager.job_finished.connect(self._on_job_finished)

    def _toggle_queue(self):
        if self.queue_manager.is_running:
            self.queue_manager.pause_queue()
            self._update_controls()
        else:
            if self._preflight_worker and self._preflight_worker.isRunning():
                return
            self.start_btn.setEnabled(False)
            self.start_btn.setText("Checking...")
            self._preflight_worker = QueuePreflightWorker(self.queue_manager.jobs, parent=self)
            self._preflight_worker.conflict_found.connect(self._on_preflight_conflict)
            self._preflight_worker.preflight_finished.connect(self._on_preflight_finished)
            self._preflight_worker.start()

    def _on_preflight_conflict(self, job_id: str, page_desc: str, selected: list, untranslated: list):
        target_job = next((j for j in self.queue_manager.jobs if j.id == job_id), None)
        if not target_job:
            return

        reply = QMessageBox.question(
            self,
            "Translation Cache Found",
            f"Translation ({target_job.lang_display}) data already exists for {page_desc} in '{target_job.folder_name}'.\n\n"
            "Would you like to re-scan and translate them again from scratch?\n\n"
            "- Yes: Re-translate and overwrite cached pages.\n"
            "- No: Skip already translated pages and only process untranslated ones.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Cancel:
            if self._preflight_worker and self._preflight_worker.isRunning():
                self._preflight_worker.requestInterruption()
                self._preflight_worker.wait(500)
                self._preflight_worker = None
            self._update_controls()
        elif reply == QMessageBox.StandardButton.No:
            if not untranslated:
                target_job.status = JobStatus.COMPLETED
                target_job.status_message = "All selected pages already translated"
            else:
                target_job.selected_image_paths = list(untranslated)

    def _on_preflight_finished(self):
        self._preflight_worker = None
        self.queue_manager.start_queue()
        self._update_controls()

    def _update_controls(self):
        is_running = self.queue_manager.is_running
        is_stopping = getattr(self.queue_manager, "is_stopping", False)
        pending = self.queue_manager.pending_count

        if is_stopping:
            self.start_btn.setText("Pausing...")
            self.start_btn.setEnabled(False)
        elif is_running:
            self.start_btn.setText("Pause Queue")
            self.start_btn.setEnabled(True)
        else:
            has_paused = any(j.status == JobStatus.PAUSED for j in self.queue_manager.jobs)
            can_start = any(
                j.status in (JobStatus.PENDING, JobStatus.PAUSED) and j.selected_count > 0 for j in self.queue_manager.jobs
            ) or any(j.status == JobStatus.FAILED for j in self.queue_manager.jobs)
            self.start_btn.setText("Resume Queue" if has_paused else "Start Queue")
            self.start_btn.setEnabled(can_start)

        self.pending_label.setText(f"{pending} jobs pending")

        active = self.queue_manager.active_job
        if is_stopping:
            self.status_label.setText("Pausing queue gracefully...")
        elif is_running and active:
            self.status_label.setText(f"Processing: {active.folder_name} ({active.progress_pct}%)")
        else:
            self.status_label.setText("Idle" if not is_running else "Finishing...")

    def _remove_selected_job(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.queue_manager.jobs):
            job = self.queue_manager.jobs[row]
            self.queue_manager.remove_job(job.id)

    def _on_list_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        row = self.list_widget.row(item)
        if 0 <= row < len(self.queue_manager.jobs):
            job = self.queue_manager.jobs[row]
            menu = QMenu(self)
            act_remove = menu.addAction("Remove from Queue")
            act_remove.triggered.connect(lambda: self.queue_manager.remove_job(job.id))
            menu.exec(self.list_widget.mapToGlobal(pos))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            focus_widget = self.focusWidget()
            if not isinstance(focus_widget, (QLineEdit, QTextEdit, QSpinBox)):
                self._remove_selected_job()
                event.accept()
                return
        super().keyPressEvent(event)

    def open_tab(self, tab_name: str):
        t = tab_name.lower()
        if t in ("settings", "api", "translation"):
            self.tab_widget.setCurrentWidget(self.settings_widget)
        elif t == "pages":
            self.tab_widget.setCurrentIndex(0)
        elif t == "summary":
            self.tab_widget.setCurrentIndex(1)
        elif t in ("log", "activity"):
            self.tab_widget.setCurrentIndex(2)

    def _refresh_list(self):
        current_row = self.list_widget.currentRow()
        self._last_inspected_job_id = None
        self.list_widget.clear()

        for job in self.queue_manager.jobs:
            item = QListWidgetItem()
            item.setToolTip(job.folder_name)
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

    def _on_clear_logs(self):
        self.log_edit.clear()
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.queue_manager.jobs):
            job = self.queue_manager.jobs[row]
            sink = FileLogSink(job.folder_path / "temp" / "translation.log")
            sink.clear()

    def _on_tab_changed(self, index: int):
        if hasattr(self, "hover_popup"):
            self.hover_popup.hide()

    def hideEvent(self, event):
        if hasattr(self, "hover_popup"):
            self.hover_popup.hide()
        super().hideEvent(event)

    def eventFilter(self, watched, event):
        if hasattr(self, "pages_list") and watched == self.pages_list.viewport():
            if event.type() == QEvent.Type.MouseMove:
                item = self.pages_list.itemAt(event.pos())
                if item:
                    path_str = item.data(Qt.ItemDataRole.UserRole)
                    if path_str and Path(path_str).exists():
                        gpos = self.pages_list.viewport().mapToGlobal(event.pos())
                        self.hover_popup.show_page(Path(path_str), item.text(), gpos)
                        return super().eventFilter(watched, event)
                if hasattr(self, "hover_popup"):
                    self.hover_popup.hide()
            elif event.type() in (QEvent.Type.Leave, QEvent.Type.Wheel, QEvent.Type.MouseButtonPress):
                if hasattr(self, "hover_popup"):
                    self.hover_popup.hide()
        return super().eventFilter(watched, event)

    def _on_job_selected(self, row: int):
        self._last_inspected_job_id = None
        self._update_inspector()

    def _update_pages_count_label(self, job: TranslationJob):
        self.pages_count_label.setText(f"Selected: {job.selected_count} / {job.total_count} pages")

    def _on_pages_sort_changed(self, index: int):
        row = self.list_widget.currentRow()
        if 0 <= row < len(self.queue_manager.jobs):
            job = self.queue_manager.jobs[row]
            self._populate_pages_list(job)

    def _populate_pages_list(self, job: TranslationJob):
        self._is_populating_pages = True
        self.pages_list.clear()

        is_editable = (job.status == JobStatus.PENDING)
        has_pages = len(job.image_paths) > 0
        if hasattr(self, "pages_sort_combo"):
            self.pages_sort_combo.setEnabled(has_pages)
        self.btn_select_all.setEnabled(is_editable and has_pages)
        self.btn_unselect_all.setEnabled(is_editable and has_pages)

        ws = TranslationWorkspace(job.folder_path)
        translated_fns = ws.get_translated_page_filenames(job.target_lang)
        manual_fns = ws.get_manual_labeled_page_filenames(job.target_lang)

        # Sort pages based on current sort combo selection
        sort_mode = self.pages_sort_combo.currentData() if hasattr(self, "pages_sort_combo") and self.pages_sort_combo else "natural_asc"
        paths = list(job.image_paths)
        if sort_mode == "natural_desc":
            paths.sort(key=natural_sort_key, reverse=True)
        elif sort_mode == "alpha_asc":
            paths.sort(key=lambda p: p.name.lower())
        elif sort_mode == "alpha_desc":
            paths.sort(key=lambda p: p.name.lower(), reverse=True)
        elif sort_mode == "untranslated_first":
            paths.sort(key=lambda p: (1 if (p.name in translated_fns or p.name in manual_fns) else 0, natural_sort_key(p)))
        elif sort_mode == "translated_first":
            paths.sort(key=lambda p: (0 if (p.name in translated_fns or p.name in manual_fns) else 1, natural_sort_key(p)))
        else:  # natural_asc (default)
            paths.sort(key=natural_sort_key)

        job.image_paths = paths

        for img in job.image_paths:
            item = QListWidgetItem()
            fn = img.name
            is_selected = job.is_image_selected(img)
            is_translated = (fn in translated_fns)
            has_manual_label = (fn in manual_fns)

            status_tag = ""
            if job.job_type == JobType.RASTERIZE:
                status_tag = " [Ready to Rasterize]" if is_translated else " [Needs Translation]"
            else:
                page_lang = ws.get_page_language(fn)
                if has_manual_label:
                    status_tag = f" [Manual Label] [to {page_lang}]"
                elif is_translated:
                    status_tag = f" [Cached to {page_lang}]"

            item.setText(f"{fn}{status_tag}")
            item.setData(Qt.ItemDataRole.UserRole, str(img))

            flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable
            if is_editable:
                if job.job_type == JobType.RASTERIZE and not is_translated:
                    item.setCheckState(Qt.CheckState.Unchecked)
                else:
                    flags |= Qt.ItemFlag.ItemIsEnabled
                    is_checked = is_selected or has_manual_label
                    item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Checked if is_selected else Qt.CheckState.Unchecked)

            item.setFlags(flags)
            self.pages_list.addItem(item)

        self._is_populating_pages = False
        self._update_pages_count_label(job)

    def _on_page_item_changed(self, item: QListWidgetItem):
        if self._is_populating_pages:
            return
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.queue_manager.jobs):
            return
        job = self.queue_manager.jobs[row]
        if job.status != JobStatus.PENDING:
            return

        img_path_str = item.data(Qt.ItemDataRole.UserRole)
        if not img_path_str:
            return
        is_checked = (item.checkState() == Qt.CheckState.Checked)
        job.toggle_image(Path(img_path_str), is_checked)

        self._update_pages_count_label(job)
        self._refresh_list_item(job.id)
        self._update_controls()

    def _select_all_pages(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.queue_manager.jobs):
            return
        job = self.queue_manager.jobs[row]
        if job.status != JobStatus.PENDING:
            return

        if job.job_type == JobType.RASTERIZE:
            ws = TranslationWorkspace(job.folder_path)
            translated_fns = ws.get_translated_page_filenames(job.target_lang)
            job.selected_image_paths = [p for p in job.image_paths if p.name in translated_fns]
        else:
            job.select_all()

        self._populate_pages_list(job)
        self._refresh_list_item(job.id)
        self._update_controls()

    def _unselect_all_pages(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.queue_manager.jobs):
            return
        job = self.queue_manager.jobs[row]
        if job.status != JobStatus.PENDING:
            return

        job.unselect_all()
        self._populate_pages_list(job)
        self._refresh_list_item(job.id)
        self._update_controls()

    def _update_inspector(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.queue_manager.jobs):
            self._last_inspected_job_id = None
            self.pages_count_label.setText("No job selected")
            self.pages_list.clear()
            if hasattr(self, "pages_sort_combo"):
                self.pages_sort_combo.setEnabled(False)
            self.btn_select_all.setEnabled(False)
            self.btn_unselect_all.setEnabled(False)
            self.summary_text.setText("Select a job from the list to view its summary.")
            self.log_edit.clear()
            return

        job = self.queue_manager.jobs[row]
        if self._last_inspected_job_id != job.id:
            self._last_inspected_job_id = job.id
            self._populate_pages_list(job)
        else:
            self._update_pages_count_label(job)

        job_type_label = "Permanent Rasterization (Rasterize)" if job.job_type == JobType.RASTERIZE else "Translation Overlay"
        if job.lang_display == "Mix-Lang":
            lang_name = "Mixed Languages (Mix-Lang)"
        elif job.lang_display == "ID":
            lang_name = "Indonesian (ID)"
        else:
            lang_name = "English (EN)"
        err_block = f"<p style='color: #ef4444;'><b>Error:</b> {job.error_message}</p>" if job.error_message else ""
        out_block = f"<b>Output Directory:</b> {job.output_dir}<br>" if job.output_dir else ""

        html = f"""
        <h3 style='margin: 0; color: #38bdf8;'>{job.folder_name}</h3>
        <p><b>Job Type:</b> {job_type_label}<br>
        <b>Target Language:</b> {lang_name}<br>
        <b>Folder Path:</b> {job.folder_path}<br>
        {out_block}
        <b>Selected Pages:</b> {job.selected_count} / {job.total_count} pages<br>
        <b>Status:</b> {job.status.value.upper()}<br>
        <b>Progress:</b> {job.progress_pct}% ({job.progress_current}/{job.progress_total})<br>
        <b>Message:</b> {job.status_message}</p>
        {err_block}
        """
        self.summary_text.setText(html)

        # Load log file if present
        sink = FileLogSink(job.folder_path / "temp" / "translation.log")
        content = sink.read()
        if content:
            self.log_edit.setPlainText(content)
            self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
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

    def closeEvent(self, event):
        if hasattr(self, "settings_widget") and hasattr(self.settings_widget, "cleanup"):
            self.settings_widget.cleanup()
        super().closeEvent(event)

    def reject(self):
        if hasattr(self, "settings_widget") and hasattr(self.settings_widget, "cleanup"):
            self.settings_widget.cleanup()
        super().reject()
