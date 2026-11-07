import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QPushButton, QFileDialog, QMessageBox,
    QLabel, QStatusBar, QComboBox, QApplication,
    QProgressDialog, QFrame, QProgressBar, QMenu, QMenuBar
)
from PyQt6.QtCore import Qt, QSettings, QEvent, QTimer, QRectF, QSize
from PyQt6.QtGui import QKeyEvent, QIcon, QAction, QPixmap, QPainter, QPen, QColor, QKeySequence, QShortcut
from src.version import __version__
from src.models.folder_item import FolderItem
from src.models.translation_job import TranslationJob, JobStatus
from src.services.scanner import scan_directory
from src.services.trash_service import send_folder_to_trash
from src.services.folder_service import rename_folder
from src.services.thumbnail_cache import ThumbnailCache
from src.services.translation_worker import TranslationWorker
from src.services.translation_workspace import TranslationWorkspace
from src.services.translation_queue import TranslationQueueManager
from src.ui.folder_list import FolderListWidget
from src.ui.thumbnail_strip import ThumbnailStripWidget
from src.ui.preview_pane import PreviewPaneWidget
from src.ui.rename_dialog import RenameDialog
from src.ui.batch_rename_dialog import BatchRenameDialog
from src.ui.settings_dialog import SettingsDialog
from src.ui.log_dialog import LogDialog
from src.ui.queue_dialog import QueueDialog

def create_sidebar_icon(color: str = "#d4d4d8", size: int = 20) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.8)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    margin = 2.0
    rect_w = size - 2 * margin
    rect_h = size - 2 * margin
    painter.drawRoundedRect(QRectF(margin, margin, rect_w, rect_h), 3.0, 3.0)

    line_x = margin + rect_w * 0.38
    painter.drawLine(int(line_x), int(margin), int(line_x), int(margin + rect_h))
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Windows Folder Image Previewer v{__version__}")
        self.resize(1200, 780)
        self._set_app_icon()
        self.settings = QSettings("FolderImagePreviewer", "FolderImagePreviewer")
        self.thumbnail_cache = ThumbnailCache()
        self._select_last_on_folder_load = False
        self._translation_worker = None
        self._queue_dialog = None
        self.queue_manager = TranslationQueueManager(settings_getter=self._get_api_credentials)
        self._init_ui()
        self._init_queue_connections()
        self._install_global_event_filter()
        self._restore_last_folder()

    def _set_app_icon(self):
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            icon_path = Path(sys._MEIPASS) / "assets" / "icon.png"
        else:
            icon_path = Path(__file__).resolve().parent.parent.parent / "assets" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Standard Desktop Menu Bar
        self._init_menu_bar()

        # Top Bar Container: Sidebar toggle, Translate, Queue Manager & directory info
        self.top_bar_widget = QWidget()
        self.top_bar_widget.setObjectName("topBar")
        self.top_bar_widget.setStyleSheet("""
            QWidget#topBar {
                background-color: #18181b;
                border-bottom: 1px solid #27272a;
            }
            QPushButton {
                background-color: #27272a;
                color: #f1f5f9;
                border: 1px solid #3f3f46;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 11px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3f3f46;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #18181b;
            }
            QPushButton#sidebarToggleBtn {
                background-color: transparent;
                border: 1px solid #3f3f46;
                border-radius: 4px;
                padding: 2px;
            }
            QPushButton#sidebarToggleBtn:hover {
                background-color: #27272a;
                border-color: #71717a;
            }
            QPushButton#sidebarToggleBtn:pressed {
                background-color: #18181b;
            }
        """)

        top_bar = QHBoxLayout(self.top_bar_widget)
        top_bar.setContentsMargins(8, 4, 8, 4)
        top_bar.setSpacing(8)

        # Modern panel/sidebar toggle icon button
        self.sidebar_toggle_btn = QPushButton()
        self.sidebar_toggle_btn.setObjectName("sidebarToggleBtn")
        self.sidebar_toggle_btn.setIcon(create_sidebar_icon("#d4d4d8", 18))
        self.sidebar_toggle_btn.setIconSize(QSize(18, 18))
        self.sidebar_toggle_btn.setFixedSize(30, 26)
        self.sidebar_toggle_btn.setToolTip("Toggle Sidebar (Ctrl+Shift+B)")
        self.sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        top_bar.addWidget(self.sidebar_toggle_btn)

        # Translate button with dropdown options (EN / ID)
        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setToolTip("Add current folder to translation queue (EN / ID)")
        self.translate_btn.setMenu(self.translate_menu)
        top_bar.addWidget(self.translate_btn)

        # Queue Manager button
        self.queue_mgr_btn = QPushButton("Queue Manager")
        self.queue_mgr_btn.setToolTip("Open Translation Queue Manager [Ctrl+J]")
        self.queue_mgr_btn.clicked.connect(self._on_open_queue_dialog)
        top_bar.addWidget(self.queue_mgr_btn)

        # Directory information display pill
        self.path_label = QLabel("No root folder selected")
        self.path_label.setStyleSheet("""
            QLabel {
                background-color: #141417;
                color: #94a3b8;
                border: 1px solid #27272a;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-style: italic;
            }
        """)
        top_bar.addWidget(self.path_label, 1)

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+Shift+B"), self, self._toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+E"), self, lambda: self._on_add_to_queue("en"))
        QShortcut(QKeySequence("Ctrl+I"), self, lambda: self._on_add_to_queue("id"))
        QShortcut(QKeySequence("Ctrl+J"), self, self._on_open_queue_dialog)

        # Compatibility aliases for actions / tests
        self.open_btn = self.act_open
        self.batch_rename_btn = self.act_batch_rename
        self.settings_btn = self.act_settings
        self.start_queue_btn = self.queue_mgr_btn
        self.add_queue_btn = self.translate_btn
        self.queue_btn = self.queue_mgr_btn
        self.overlay_toggle_btn = self.act_overlay
        self.fullscreen_btn = self.act_fullscreen

        # In-memory zoom combo for tracking state
        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["Fit", "50%", "75%", "100%", "120%"])
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.currentTextChanged.connect(self._set_zoom_mode_from_preset)

        main_layout.addWidget(self.top_bar_widget)

        # Main Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left folder list
        self.folder_list = FolderListWidget()
        self.folder_list.folder_selected.connect(self._on_folder_selected)
        self.folder_list.rename_requested.connect(self._on_rename_folder)
        self.splitter.addWidget(self.folder_list)

        # Right container
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.preview_pane = PreviewPaneWidget()
        self.preview_pane.zoom_changed.connect(self._on_zoom_changed_from_preview)
        right_layout.addWidget(self.preview_pane, 1)

        self.thumbnail_strip = ThumbnailStripWidget(self.thumbnail_cache)
        self.thumbnail_strip.image_selected.connect(self._on_image_selected)
        right_layout.addWidget(self.thumbnail_strip)

        self.splitter.addWidget(right_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        main_layout.addWidget(self.splitter, 1)

        # Bottom Status Bar with Handbrake-style Process Tracker
        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #141417;
                color: #94a3b8;
                border-top: 1px solid #27272a;
                font-size: 12px;
            }
        """)
        self.setStatusBar(self.status_bar)

        self.status_progress_bar = QProgressBar()
        self.status_progress_bar.setFixedSize(140, 14)
        self.status_progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #1e1e24;
                border: 1px solid #334155;
                border-radius: 6px;
                text-align: center;
                font-size: 10px;
                color: #f8fafc;
            }
            QProgressBar::chunk {
                background-color: #0284c7;
                border-radius: 5px;
            }
        """)
        self.status_progress_bar.hide()
        self.status_bar.addPermanentWidget(self.status_progress_bar)

        self.status_queue_pill = QPushButton("📋 Queue: 0")
        self.status_queue_pill.setStyleSheet("""
            QPushButton {
                background-color: #1e1e24;
                color: #38bdf8;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #27272a;
                border-color: #38bdf8;
            }
        """)
        self.status_queue_pill.clicked.connect(self._on_open_queue_dialog)
        self.status_bar.addPermanentWidget(self.status_queue_pill)

    def _init_menu_bar(self):
        menubar = self.menuBar()
        menubar.setStyleSheet("""
            QMenuBar {
                background-color: #18181b;
                color: #e4e4e7;
                border-bottom: 1px solid #27272a;
                padding: 2px 4px;
                font-size: 12px;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 4px 8px;
                border-radius: 3px;
            }
            QMenuBar::item:selected {
                background-color: #27272a;
                color: #ffffff;
            }
            QMenuBar::item:pressed {
                background-color: #3f3f46;
            }
            QMenu {
                background-color: #1e1e24;
                color: #f1f5f9;
                border: 1px solid #3f3f46;
                padding: 4px 0;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
            }
            QMenu::item:selected {
                background-color: #27272a;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: #3f3f46;
                margin: 4px 6px;
            }
        """)

        # 1. File Menu: Open, Batch Rename, Settings, Exit
        file_menu = menubar.addMenu("&File")
        self.act_open = file_menu.addAction("Open Root Folder...")
        self.act_open.setShortcut("Ctrl+O")
        self.act_open.triggered.connect(self._on_open_folder)

        self.act_batch_rename = file_menu.addAction("Batch Rename Folders...")
        self.act_batch_rename.setShortcut("Ctrl+B")
        self.act_batch_rename.triggered.connect(self._on_batch_rename_folders)

        self.act_settings = file_menu.addAction("Settings...")
        self.act_settings.setShortcut("Ctrl+,")
        self.act_settings.triggered.connect(self._on_open_settings)

        file_menu.addSeparator()

        self.act_exit = file_menu.addAction("Exit")
        self.act_exit.setShortcut("Ctrl+Q")
        self.act_exit.triggered.connect(self.close)

        # Compatibility actions for shortcuts / queue controls
        self.act_start_queue = QAction("Start Queue", self)
        self.act_start_queue.setShortcut("Ctrl+R")
        self.act_start_queue.triggered.connect(self._toggle_queue)
        self.act_start_queue.setEnabled(False)
        self.addAction(self.act_start_queue)

        self.act_queue_mgr = QAction("Translation Queue Manager...", self)
        self.act_queue_mgr.setShortcut("Ctrl+J")
        self.act_queue_mgr.triggered.connect(self._on_open_queue_dialog)
        self.addAction(self.act_queue_mgr)

        self.translate_menu = QMenu(self)
        self.act_add_queue_en = self.translate_menu.addAction("Translate to English [EN]")
        self.act_add_queue_en.setShortcut("Ctrl+E")
        self.act_add_queue_en.triggered.connect(lambda: self._on_add_to_queue(target_lang="en"))
        self.act_add_queue_id = self.translate_menu.addAction("Translate to Indonesian [ID]")
        self.act_add_queue_id.setShortcut("Ctrl+I")
        self.act_add_queue_id.triggered.connect(lambda: self._on_add_to_queue(target_lang="id"))
        self.queue_sub = self.translate_menu

        # 2. View Menu: NO dividers, NO icons (NO Hide/Show Sidebar!)
        view_menu = menubar.addMenu("&View")
        self.act_overlay = view_menu.addAction("Toggle Translation Overlay")
        self.act_overlay.setShortcut("T")
        self.act_overlay.triggered.connect(self._toggle_translation_overlay)

        self.zoom_sub = view_menu.addMenu("Zoom")
        for z in ["Fit", "50%", "75%", "100%", "120%"]:
            act_z = self.zoom_sub.addAction(z)
            act_z.triggered.connect(lambda checked=False, val=z: self._set_zoom_mode_from_preset(val))

        self.act_fullscreen = view_menu.addAction("Fullscreen")
        self.act_fullscreen.setShortcut("F12")
        self.act_fullscreen.triggered.connect(self._toggle_fullscreen)

        # 3. Help Menu: NO icons, NO dividers
        help_menu = menubar.addMenu("&Help")
        self.act_logs = help_menu.addAction("View Logs...")
        self.act_logs.triggered.connect(self._on_view_logs)

        self.act_shortcuts = help_menu.addAction("Keyboard Shortcuts")
        self.act_shortcuts.setShortcut("F1")
        self.act_shortcuts.triggered.connect(self._on_show_shortcuts_info)

        self.act_about = help_menu.addAction("About")
        self.act_about.triggered.connect(self._on_show_about)

    def _toggle_sidebar(self):
        is_visible = not self.folder_list.isHidden()
        if is_visible:
            self._sidebar_last_width = self.folder_list.width()
            self._sidebar_saved_sizes = self.splitter.sizes()
            self.folder_list.save_scroll_state()
            self._sidebar_hidden = True
            self.folder_list.hide()
            self.sidebar_toggle_btn.setToolTip("Show Sidebar (Ctrl+Shift+B)")
        else:
            self._sidebar_hidden = False
            self.folder_list.show()
            if hasattr(self, "_sidebar_saved_sizes") and self._sidebar_saved_sizes and self._sidebar_saved_sizes[0] > 0:
                self.splitter.setSizes(self._sidebar_saved_sizes)
            else:
                last_w = getattr(self, "_sidebar_last_width", 260) or 260
                self.splitter.setSizes([last_w, max(100, self.width() - last_w)])
            self.folder_list.restore_scroll_state()
            QTimer.singleShot(0, self.folder_list.restore_scroll_state)
            self.sidebar_toggle_btn.setToolTip("Hide Sidebar (Ctrl+Shift+B)")

    def _set_zoom_mode_from_preset(self, val: str):
        if val == "Fit":
            self.preview_pane.set_zoom_mode("fit")
        else:
            pct = int(val.rstrip("%"))
            self.preview_pane.set_zoom_mode(pct / 100.0)
        self.zoom_combo.blockSignals(True)
        idx = self.zoom_combo.findText(val)
        if idx >= 0:
            self.zoom_combo.setCurrentIndex(idx)
        self.zoom_combo.blockSignals(False)

    def _on_clear_current_translation_cache(self):
        folder = self.folder_list.get_selected_folder()
        if not folder:
            QMessageBox.information(self, "No Folder Selected", "Please select a folder to clear its translation cache.")
            return
        ws = TranslationWorkspace(folder.path)
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            f"Are you sure you want to clear the translation cache for '{folder.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            ws.clear_cache()
            self.status_bar.showMessage(f"Cleared translation cache for {folder.name}")
            curr_img = self.thumbnail_strip.get_current_image()
            if curr_img:
                self._on_image_selected(curr_img)

    def _on_show_about(self):
        QMessageBox.about(
            self,
            "About Windows Folder Image Previewer",
            f"<h3>Windows Folder Image Previewer v{__version__}</h3>"
            "<p>Offline local comic & manga image reader with AI machine translation and Handbrake-style background queue.</p>"
        )

    def _install_global_event_filter(self):
        self.installEventFilter(self)
        self.preview_pane.installEventFilter(self)
        self.preview_pane.scroll_area.installEventFilter(self)
        self.preview_pane.image_label.installEventFilter(self)
        self.folder_list.installEventFilter(self)
        self.thumbnail_strip.installEventFilter(self)


    def _restore_last_folder(self):
        last_dir = self.settings.value("last_root_folder", type=str)
        if last_dir and Path(last_dir).is_dir():
            self._load_root_folder(Path(last_dir))

    def _load_root_folder(self, root_path: Path):
        self.path_label.setText(str(root_path))
        folders = scan_directory(root_path)
        for f in folders:
            ws = TranslationWorkspace(f.path)
            if ws.is_translation_complete("en") or ws.is_translation_complete("id"):
                self.folder_list.set_folder_status(f.path, "done")
        for j in self.queue_manager.jobs:
            if j.status == JobStatus.RUNNING:
                self.folder_list.set_folder_status(j.folder_path, "running")
            elif j.status == JobStatus.PENDING:
                self.folder_list.set_folder_status(j.folder_path, "queued")
            elif j.status == JobStatus.COMPLETED:
                self.folder_list.set_folder_status(j.folder_path, "done")
            elif j.status == JobStatus.FAILED:
                self.folder_list.set_folder_status(j.folder_path, "failed")
        self.folder_list.set_folders(folders)
        self.status_bar.showMessage(f"Found {len(folders)} folders with images.")

    def _on_open_folder(self):
        start_dir = self.settings.value("last_root_folder", "") or ""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Root Folder", str(start_dir))
        if dir_path:
            self.settings.setValue("last_root_folder", dir_path)
            self._load_root_folder(Path(dir_path))

    def _on_image_selected(self, image_path: Optional[Path]):
        self.preview_pane.set_image(image_path)
        if image_path and image_path.exists():
            ws = TranslationWorkspace(image_path.parent)
            trans_map = {}
            for lang in ("id", "en"):
                if ws.is_translation_complete(target_lang=lang):
                    trans_map = ws.load_translations(target_lang=lang)
                    break
            if trans_map:
                ocr_results = ws.load_ocr_results()
                page_data = ocr_results.get(image_path.name)
                if page_data:
                    self.preview_pane.set_translation_data(page_data, trans_map)

    def _toggle_translation_overlay(self):
        enabled = self.preview_pane.toggle_translation_overlay()
        self.act_overlay.setText("Toggle Translation Overlay (ON)" if enabled else "Toggle Translation Overlay (OFF)")

    def _get_api_credentials(self):
        api_key = self.settings.value("llm_api_key", "", type=str).strip()
        base_url = self.settings.value("llm_base_url", "https://generativelanguage.googleapis.com/v1beta/openai/", type=str)
        model = self.settings.value("llm_model", "gemini-2.5-flash", type=str)
        timeout = self.settings.value("llm_timeout_seconds", 120, type=int)
        batch_size = self.settings.value("llm_batch_size", 0, type=int)
        return api_key, base_url, model, timeout, batch_size

    def _init_queue_connections(self):
        self.queue_manager.queue_updated.connect(self._on_queue_updated)
        self.queue_manager.queue_state_changed.connect(self._on_queue_state_changed)
        self.queue_manager.job_started.connect(self._on_queue_job_started)
        self.queue_manager.job_progress.connect(self._on_queue_job_progress)
        self.queue_manager.job_finished.connect(self._on_queue_job_finished)
        self._on_queue_updated()

    def _on_queue_job_started(self, job_id: str):
        job = self.queue_manager.get_job(job_id)
        if job:
            self.folder_list.set_folder_status(job.folder_path, "running")

    def _on_open_queue_dialog(self):
        if self._queue_dialog is None:
            self._queue_dialog = QueueDialog(self.queue_manager, parent=self)
        self._queue_dialog.show()
        self._queue_dialog.raise_()
        self._queue_dialog.activateWindow()

    def _on_add_to_queue(self, target_lang: str = "en"):
        folder = self.folder_list.get_current_folder()
        if not folder or not folder.image_paths:
            QMessageBox.warning(self, "No Folder Selected", "Please select a folder containing images to add to the queue.")
            return

        api_key, *_ = self._get_api_credentials()
        if not api_key:
            reply = QMessageBox.question(
                self,
                "API Key Missing",
                "An API Key is required for translation.\nWould you like to open Settings now to set it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_open_settings()
            return

        ws = TranslationWorkspace(folder.path)
        if ws.is_translation_complete(target_lang=target_lang):
            reply = QMessageBox.question(
                self,
                "Translation Cache Found",
                f"Translation ({target_lang.upper()}) data already exists for '{folder.name}'.\n\nWould you like to re-scan and translate again from scratch?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                ws.clear_cache()
            else:
                self.status_bar.showMessage(f"Loaded existing {target_lang.upper()} translation for {folder.name}")
                curr_img = self.thumbnail_strip.get_current_image()
                if curr_img:
                    self._on_image_selected(curr_img)
                return

        job = self.queue_manager.add_job(
            folder_path=folder.path,
            image_paths=folder.image_paths,
            target_lang=target_lang
        )
        self.folder_list.set_folder_status(folder.path, "queued")
        lang_name = "Indonesian [ID]" if target_lang.lower() == "id" else "English [EN]"
        self.status_bar.showMessage(f"Added '{folder.name}' to queue ({lang_name}). Click 'Start Translate' to begin.")

    def _toggle_queue(self):
        if self.queue_manager.is_running:
            self.queue_manager.pause_queue()
        else:
            api_key, *_ = self._get_api_credentials()
            if not api_key:
                reply = QMessageBox.question(
                    self,
                    "API Key Missing",
                    "An API Key is required for translation.\nWould you like to open Settings now to set it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._on_open_settings()
                return
            self.queue_manager.start_queue()

    def _on_queue_updated(self):
        pending = self.queue_manager.pending_count
        mgr_text = f"Queue Manager ({pending})" if pending > 0 else "Queue Manager"
        self.queue_mgr_btn.setText(mgr_text)
        self.act_queue_mgr.setText(f"Translation Queue Manager... ({pending})")
        self.status_queue_pill.setText(f"📋 Queue: {pending}")

        is_running = self.queue_manager.is_running
        if is_running:
            self.act_start_queue.setText("Pause Queue")
            self.act_start_queue.setEnabled(True)
        else:
            self.act_start_queue.setText("Start Queue")
            can_start = pending > 0 or any(j.status == JobStatus.FAILED for j in self.queue_manager.jobs)
            self.act_start_queue.setEnabled(can_start)

    def _on_queue_state_changed(self, is_running: bool):
        self._on_queue_updated()
        if not is_running:
            self.status_progress_bar.hide()
            self.status_bar.showMessage("Translation queue paused or completed.")

    def _on_queue_job_progress(self, job_id: str, message: str, current: int, total: int):
        self.status_progress_bar.show()
        pct = int((current / total) * 100) if total > 0 else 0
        self.status_progress_bar.setValue(pct)
        job = self.queue_manager.get_job(job_id)
        job_name = job.folder_name if job else "Chapter"
        lang = job.lang_display if job else "EN"
        self.status_bar.showMessage(f"[{lang}] {job_name}: {message} ({pct}%)")

    def _on_queue_job_finished(self, job_id: str, success: bool, message: str):
        job = self.queue_manager.get_job(job_id)
        job_name = job.folder_name if job else "Chapter"
        if job:
            self.folder_list.set_folder_status(job.folder_path, "done" if success else "failed")
        if success:
            self.status_bar.showMessage(f"✓ Translated '{job_name}' successfully.")
            curr_folder = self.folder_list.get_current_folder()
            if curr_folder and job and curr_folder.path == job.folder_path:
                curr_img = self.thumbnail_strip.get_current_image()
                if curr_img:
                    self._on_image_selected(curr_img)
        else:
            self.status_bar.showMessage(f"✕ Translation failed for '{job_name}': {message}")

    def _on_translate_folder(self):
        """Compatibility trigger: adds current folder to queue and starts processing."""
        self._on_add_to_queue(target_lang="en")
        if self.queue_manager.pending_count > 0 and not self.queue_manager.is_running:
            self._toggle_queue()

    def _on_view_logs(self):
        folder = self.folder_list.get_current_folder()
        log_path = (folder.path / "temp" / "translation.log") if folder else None
        dialog = LogDialog(parent=self, log_path=log_path)
        dialog.exec()

    def _on_folder_selected(self, folder_item):
        if folder_item is None:
            self.thumbnail_strip.set_images([])
            self.preview_pane.set_image(None)
            self.status_bar.showMessage("No folder selected.")
            return

        select_idx = len(folder_item.image_paths) - 1 if self._select_last_on_folder_load else 0
        self._select_last_on_folder_load = False
        self.thumbnail_strip.set_images(folder_item.image_paths, select_index=select_idx)
        self.status_bar.showMessage(f"{folder_item.name} - {folder_item.image_count} images")

    def _on_zoom_combo_changed(self, text: str):
        self.preview_pane.set_zoom_mode(text)

    def _on_zoom_changed_from_preview(self, text: str):
        self.zoom_combo.blockSignals(True)
        idx = self.zoom_combo.findText(text)
        if idx >= 0:
            self.zoom_combo.setCurrentIndex(idx)
        self.zoom_combo.blockSignals(False)

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            if getattr(self, "_was_maximized", False):
                self.showMaximized()
            else:
                self.showNormal()
            self.top_bar_widget.show()
            if not getattr(self, "_sidebar_hidden", False):
                self.folder_list.show()
            self.thumbnail_strip.show()
            self.status_bar.show()
            if hasattr(self, "_saved_splitter_sizes") and self._saved_splitter_sizes:
                self.splitter.setSizes(self._saved_splitter_sizes)
            self.folder_list.scroll_to_current()
            self.thumbnail_strip.scroll_to_current()
            self.act_fullscreen.setText("Fullscreen")
        else:
            self._was_maximized = self.isMaximized()
            self._saved_splitter_sizes = self.splitter.sizes()
            self.top_bar_widget.hide()
            self.folder_list.hide()
            self.thumbnail_strip.hide()
            self.status_bar.hide()
            self.showFullScreen()
            self.act_fullscreen.setText("Exit Fullscreen")
        self.setFocus()

    def _on_rename_folder(self, folder_to_rename: Optional[FolderItem] = None):
        target = folder_to_rename if isinstance(folder_to_rename, FolderItem) else self.folder_list.get_current_folder()
        if not target:
            return

        dialog = RenameDialog(target.name, parent=self)
        if dialog.exec():
            new_name = dialog.get_new_name()
            if new_name and new_name != target.name:
                success, error, new_path = rename_folder(target.path, new_name)
                if success and new_path:
                    self.folder_list.rename_folder_item(target.path, new_path, new_name)
                    self.status_bar.showMessage(f"Renamed to '{new_name}'.")
                else:
                    QMessageBox.critical(self, "Error Renaming Folder", f"Failed to rename folder: {error}")

    def _on_batch_rename_folders(self):
        targets = self.folder_list.get_selected_folders()
        if not targets:
            targets = list(self.folder_list._filtered_items)

        if not targets:
            QMessageBox.information(self, "Batch Rename", "No folders available to rename.")
            return

        dialog = BatchRenameDialog(targets, parent=self)
        if dialog.exec():
            pairs = dialog.get_rename_pairs()
            if not pairs:
                return

            total = len(pairs)
            progress = QProgressDialog("Renaming folders...", "Cancel", 0, total, self)
            progress.setWindowTitle("Batch Rename Progress")
            progress.setWindowModality(Qt.WindowModality.ApplicationModal)
            progress.setMinimumDuration(0)
            progress.setMinimumWidth(420)
            progress.setStyleSheet("""
                QProgressDialog {
                    background-color: #1e1e1e;
                    color: #f1f5f9;
                }
                QLabel {
                    color: #f1f5f9;
                    font-size: 13px;
                    min-height: 48px;
                }
                QProgressBar {
                    background-color: #2b2d35;
                    border: 1px solid #4c566a;
                    border-radius: 4px;
                    text-align: center;
                    color: #ffffff;
                    min-height: 20px;
                }
                QProgressBar::chunk {
                    background-color: #0284c7;
                    border-radius: 3px;
                }
                QPushButton {
                    background-color: #334155;
                    color: #e2e8f0;
                    border-radius: 4px;
                    padding: 6px 18px;
                    font-weight: bold;
                    border: none;
                }
                QPushButton:hover {
                    background-color: #dc2626;
                    color: white;
                }
            """)
            progress.show()
            progress.setValue(0)

            renamed_updates = []
            errors = []

            for i, (folder, new_name) in enumerate(pairs):
                if progress.wasCanceled():
                    break

                progress.setLabelText(f"Renaming ({i+1}/{total}):\n{folder.name}\n→ {new_name}")
                progress.setValue(i)
                QApplication.processEvents()

                success, error, new_path = rename_folder(folder.path, new_name)
                if success and new_path:
                    renamed_updates.append((folder.path, new_path, new_name))
                else:
                    errors.append(f"{folder.name} -> {new_name}: {error}")

            was_cancelled = progress.wasCanceled()
            progress.setValue(total)
            progress.close()

            if renamed_updates:
                self.folder_list.rename_folder_items_batch(renamed_updates)
                if was_cancelled:
                    self.status_bar.showMessage(f"Batch rename cancelled. Renamed {len(renamed_updates)} of {total} folder(s).")
                else:
                    self.status_bar.showMessage(f"Batch renamed {len(renamed_updates)} folder(s).")
            elif was_cancelled:
                self.status_bar.showMessage("Batch rename cancelled. No folders were renamed.")

            if errors:
                QMessageBox.critical(self, "Batch Rename Errors", "\n".join(errors[:20]))

    def _on_delete_folder(self):
        selected_folders = self.folder_list.get_selected_folders()
        if not selected_folders:
            return

        if len(selected_folders) == 1:
            confirm_msg = f"Are you sure you want to move folder '{selected_folders[0].name}' to the Recycle Bin?"
        else:
            confirm_msg = f"Are you sure you want to move {len(selected_folders)} selected folders to the Recycle Bin?"

        confirm = QMessageBox.question(
            self,
            "Confirm Delete",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if confirm == QMessageBox.StandardButton.Yes:
            deleted_paths = []
            errors = []
            for folder in selected_folders:
                success, error = send_folder_to_trash(folder.path)
                if success:
                    deleted_paths.append(folder.path)
                else:
                    errors.append(f"{folder.name}: {error}")

            if deleted_paths:
                self.folder_list.remove_folder_items(deleted_paths)
                if len(deleted_paths) == 1:
                    self.status_bar.showMessage(f"Moved '{selected_folders[0].name}' to Recycle Bin.")
                else:
                    self.status_bar.showMessage(f"Moved {len(deleted_paths)} folders to Recycle Bin.")

            if errors:
                QMessageBox.critical(self, "Error Deleting Folders", "\n".join(errors))

    def _on_show_shortcuts_info(self):
        info_text = (
            "<h3>Keyboard Shortcuts & Navigation</h3>"
            "<ul>"
            "<li><b>Select & Delete:</b> Click or select one/more folders (Ctrl+Click, Shift+Click, Ctrl+A), then press <b>Delete</b>.</li>"
            "<li><b>Rename Folder:</b> <b>Double-click</b> any folder item in the list or press <b>F2</b>.</li>"
            "<li><b>Fullscreen Reader:</b> Press <b>F12</b> or click <b>Fullscreen</b> to view images in full screen with zero UI distraction. (Escape or F12 exits).</li>"
            "<li><b>Zoom Presets:</b> Press <b>Ctrl + +</b> (Zoom In) or <b>Ctrl + -</b> (Zoom Out), or use the top bar dropdown (Fit, 50%, 75%, 100%, 120%). Zoom settings persist when switching directories.</li>"
            "<li><b>Toggle Translation:</b> Press <b>T</b> to toggle the English translation overlay on/off.</li>"
            "<li><b>Image Navigation:</b> Press <b>Left</b> / <b>Right</b> arrows.<br>"
            "<i>In fullscreen mode, navigating past the last image automatically continues to the next folder; navigating before the 1st image goes to the previous folder.</i></li>"
            "<li><b>Folder Navigation:</b> Press <b>Up</b> / <b>Down</b> arrows to change folder.</li>"
            "</ul>"
        )
        QMessageBox.information(self, "Shortcuts & Information", info_text)

    def _on_open_settings(self):
        dialog = SettingsDialog(
            parent=self,
            settings=self.settings,
            is_queue_running=self.queue_manager.is_running
        )
        self.queue_manager.queue_state_changed.connect(dialog.set_queue_running)
        try:
            dialog.exec()
        finally:
            try:
                self.queue_manager.queue_state_changed.disconnect(dialog.set_queue_running)
            except (TypeError, RuntimeError):
                pass

    def _navigate_next(self):
        if not self.thumbnail_strip.select_next():
            # At last image of current folder -> move to next folder
            if self.folder_list.has_next_folder():
                self._select_last_on_folder_load = False
                self.folder_list.select_next_folder()

    def _navigate_previous(self):
        if not self.thumbnail_strip.select_previous():
            # At first image of current folder -> move to previous folder's last image
            if self.folder_list.has_previous_folder():
                self._select_last_on_folder_load = True
                self.folder_list.select_previous_folder()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            key = event.key()
            modifiers = event.modifiers()

            # Ignore navigation shortcuts if typing in filter input (unless Escape/F12)
            if self.folder_list.filter_input.hasFocus():
                if key in (Qt.Key.Key_Escape, Qt.Key.Key_F12):
                    self._toggle_fullscreen()
                    return True
                return super().eventFilter(watched, event)

            if key == Qt.Key.Key_Left:
                self._navigate_previous()
                return True
            elif key == Qt.Key.Key_Right:
                self._navigate_next()
                return True
            elif key == Qt.Key.Key_F12 or (key == Qt.Key.Key_Escape and self.isFullScreen()):
                self._toggle_fullscreen()
                return True
            elif key == Qt.Key.Key_F2:
                self._on_rename_folder()
                return True
            elif key == Qt.Key.Key_Delete:
                self._on_delete_folder()
                return True
            elif key == Qt.Key.Key_T:
                self._toggle_translation_overlay()
                return True
            elif modifiers & Qt.KeyboardModifier.ControlModifier and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.preview_pane.zoom_in()
                return True
            elif modifiers & Qt.KeyboardModifier.ControlModifier and key in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
                self.preview_pane.zoom_out()
                return True
            elif key == Qt.Key.Key_PageUp:
                if watched != self.preview_pane.scroll_area:
                    bar = self.preview_pane.scroll_area.verticalScrollBar()
                    bar.setValue(bar.value() - bar.pageStep())
                    return True
            elif key == Qt.Key.Key_PageDown:
                if watched != self.preview_pane.scroll_area:
                    bar = self.preview_pane.scroll_area.verticalScrollBar()
                    bar.setValue(bar.value() + bar.pageStep())
                    return True

        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        # Fallback if not caught by eventFilter
        self.eventFilter(self, event)




