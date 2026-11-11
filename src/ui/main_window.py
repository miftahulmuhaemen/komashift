import sys
import uuid
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QPushButton, QFileDialog, QMessageBox,
    QLabel, QStatusBar, QComboBox, QApplication,
    QProgressDialog, QFrame, QProgressBar, QMenu, QMenuBar
)
from PyQt6.QtCore import Qt, QSettings, QEvent, QTimer, QRectF, QSize, QPoint
from PyQt6.QtGui import QKeyEvent, QIcon, QAction, QPixmap, QPainter, QPen, QColor, QKeySequence, QShortcut, QCursor
from src.version import __version__
from src.models.folder_item import FolderItem
from src.models.translation_item import PageTranslation, BubbleBlock
from src.models.translation_job import TranslationJob, JobStatus, JobType
from src.services.scanner import scan_directory, natural_sort_key
from src.services.trash_service import send_folder_to_trash
from src.services.folder_service import rename_folder
from src.infra.qt_threads import ThumbnailCache
from src.services.translation_worker import TranslationWorker
from src.infra.json_workspace import JsonTempWorkspace as TranslationWorkspace
from src.services.translation_queue import TranslationQueueManager
from src.ui.folder_list import FolderListWidget
from src.ui.thumbnail_strip import ThumbnailStripWidget
from src.ui.preview_pane import PreviewPaneWidget
from src.ui.rename_dialog import RenameDialog
from src.ui.batch_rename_dialog import BatchRenameDialog
from src.ui.settings_dialog import SettingsDialog
from src.ui.queue_dialog import QueueDialog
from src.viewmodels.settings_viewmodel import SettingsViewModel
from src.viewmodels.library_viewmodel import LibraryViewModel
from src.viewmodels.translation_viewmodel import TranslationViewModel


def create_sidebar_icon(color: str = "#ffffff", size: int = 16) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), 1.4)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)

    margin = 2.0
    rect_w = size - 2 * margin
    rect_h = size - 2 * margin
    painter.drawRoundedRect(QRectF(margin, margin, rect_w, rect_h), 2.5, 2.5)

    line_x = margin + rect_w * 0.38
    painter.drawLine(int(line_x), int(margin), int(line_x), int(margin + rect_h))
    painter.end()
    return QIcon(pixmap)


def _create_white_action_icon(draw_fn, size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#ffffff"), 1.4))
    draw_fn(p, size)
    p.end()
    return QIcon(pix)


def _draw_box_tool_icon(p: QPainter, s: int):
    pen = QPen(QColor("#ffffff"), 1.4, Qt.PenStyle.DashLine)
    p.setPen(pen)
    p.drawRect(2, 2, s - 5, s - 5)


def _draw_overlay_tool_icon(p: QPainter, s: int):
    p.setPen(QPen(QColor("#ffffff"), 1.4))
    p.drawRoundedRect(2, 2, s - 5, s - 7, 3, 3)
    p.drawLine(4, s - 5, 2, s - 2)
    p.drawLine(2, s - 2, 7, s - 5)


def _draw_fullscreen_tool_icon(p: QPainter, s: int):
    p.setPen(QPen(QColor("#ffffff"), 1.4))
    p.drawLine(2, 6, 2, 2)
    p.drawLine(2, 2, 6, 2)
    p.drawLine(s - 3, 6, s - 3, 2)
    p.drawLine(s - 3, 2, s - 7, 2)
    p.drawLine(2, s - 7, 2, s - 3)
    p.drawLine(2, s - 3, 6, s - 3)
    p.drawLine(s - 3, s - 7, s - 3, s - 3)
    p.drawLine(s - 3, s - 3, s - 7, s - 3)


def _draw_zoom_tool_icon(p: QPainter, s: int):
    p.setPen(QPen(QColor("#ffffff"), 1.4))
    p.drawEllipse(2, 2, 8, 8)
    p.drawLine(8, 8, s - 3, s - 3)


def _draw_add_labeling_queue_icon(p: QPainter, s: int):
    p.setPen(QPen(QColor("#ffffff"), 1.4))
    p.drawLine(3, 4, s - 6, 4)
    p.drawLine(3, 8, s - 6, 8)
    p.drawLine(3, 12, s - 8, 12)
    p.drawLine(s - 4, 10, s - 4, 14)
    p.drawLine(s - 6, 12, s - 2, 12)


def _draw_rasterize_icon(p: QPainter, s: int):
    p.setPen(QPen(QColor("#ffffff"), 1.4))
    p.drawLine(3, s - 4, s // 2, s - 2)
    p.drawLine(s // 2, s - 2, s - 3, s - 4)
    p.drawLine(3, s - 7, s // 2, s - 5)
    p.drawLine(s // 2, s - 5, s - 3, s - 7)
    p.drawLine(s // 2, 2, s - 3, 5)
    p.drawLine(s - 3, 5, s // 2, 8)
    p.drawLine(s // 2, 8, 3, 5)
    p.drawLine(3, 5, s // 2, 2)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KomaShift")
        self.resize(1200, 780)
        self._set_app_icon()
        self.settings = QSettings("KomaShift", "KomaShift")
        self.settings_vm = SettingsViewModel(self.settings, parent=self)
        self.library_vm = LibraryViewModel(parent=self)
        self.thumbnail_cache = ThumbnailCache()
        self._select_last_on_folder_load = False
        self._translation_worker = None
        self._queue_dialog = None
        self.queue_manager = TranslationQueueManager(settings_getter=self.settings_vm.get_api_credentials)
        self.translation_vm = TranslationViewModel(self.queue_manager, parent=self)
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
            QComboBox {
                background-color: #27272a;
                color: #f1f5f9;
                border: 1px solid #3f3f46;
                padding: 3px 8px;
                border-radius: 4px;
                font-size: 11px;
            }
            QComboBox:hover {
                background-color: #3f3f46;
            }
            QComboBox::drop-down {
                border: none;
                width: 16px;
            }
            QComboBox QAbstractItemView {
                background-color: #1e1e24;
                color: #f1f5f9;
                border: 1px solid #3f3f46;
                selection-background-color: #27272a;
                selection-color: #ffffff;
            }
        """)

        top_bar = QHBoxLayout(self.top_bar_widget)
        top_bar.setContentsMargins(8, 4, 8, 4)
        top_bar.setSpacing(8)

        # Modern panel/sidebar toggle icon button
        self.sidebar_toggle_btn = QPushButton()
        self.sidebar_toggle_btn.setObjectName("sidebarToggleBtn")
        self.sidebar_toggle_btn.setIcon(create_sidebar_icon("#ffffff", 16))
        self.sidebar_toggle_btn.setIconSize(QSize(16, 16))
        self.sidebar_toggle_btn.setFixedSize(30, 26)
        self.sidebar_toggle_btn.setToolTip("Toggle Sidebar (Ctrl+Shift+B)")
        self.sidebar_toggle_btn.clicked.connect(self._toggle_sidebar)
        top_bar.addWidget(self.sidebar_toggle_btn)

        # Overlay toggle button with white icon
        self.overlay_toggle_btn = QPushButton("Overlay (OFF)")
        self.overlay_toggle_btn.setIcon(_create_white_action_icon(_draw_overlay_tool_icon))
        self.overlay_toggle_btn.setToolTip("Toggle Translation Overlay [T]")
        self.overlay_toggle_btn.clicked.connect(self._toggle_translation_overlay)
        top_bar.addWidget(self.overlay_toggle_btn)

        # Manual Box Select tool button with white icon
        self.box_tool_btn = QPushButton("Box Select")
        self.box_tool_btn.setIcon(_create_white_action_icon(_draw_box_tool_icon))
        self.box_tool_btn.setCheckable(True)
        self.box_tool_btn.setToolTip("Mark untranslated text with a box to OCR & translate in context [B]")
        self.box_tool_btn.clicked.connect(self._toggle_box_select_tool)
        top_bar.addWidget(self.box_tool_btn)

        # Add labeling to Queue button with white icon and popover menu (to EN / ID)
        self.add_labeling_queue_btn = QPushButton("Add labeling to Queue")
        self.add_labeling_queue_btn.setIcon(_create_white_action_icon(_draw_add_labeling_queue_icon))
        self.add_labeling_queue_btn.setToolTip("Add manually labeled pages to Translation Queue")
        self.add_labeling_menu = QMenu(self)
        self.add_labeling_menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e24;
                color: #ffffff;
                border: 1px solid #3f3f46;
                padding: 4px;
            }
            QMenu::item {
                color: #ffffff;
                padding: 6px 20px 6px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #27272a;
                color: #ffffff;
            }
        """)
        act_lbl_en = self.add_labeling_menu.addAction("Translate to EN")
        act_lbl_en.triggered.connect(lambda: self._on_add_labeling_to_queue("en"))
        act_lbl_id = self.add_labeling_menu.addAction("Translate to ID")
        act_lbl_id.triggered.connect(lambda: self._on_add_labeling_to_queue("id"))
        self.add_labeling_queue_btn.setMenu(self.add_labeling_menu)
        top_bar.addWidget(self.add_labeling_queue_btn)

        # Rasterize button with pure white icon
        self.rasterize_btn = QPushButton("Rasterize")
        self.rasterize_btn.setIcon(_create_white_action_icon(_draw_rasterize_icon))
        self.rasterize_btn.setToolTip("Rasterize and flatten translated pages permanently into destination folder")
        self.rasterize_btn.clicked.connect(self._on_rasterize_clicked)
        top_bar.addWidget(self.rasterize_btn)

        # Zoom Controls with white icon directly on top bar
        self.zoom_label = QLabel("Zoom:")
        self.zoom_label.setStyleSheet("color: #ffffff; font-size: 11px;")
        top_bar.addWidget(self.zoom_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["Fit", "50%", "75%", "100%", "120%"])
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.currentTextChanged.connect(self._set_zoom_mode_from_preset)
        top_bar.addWidget(self.zoom_combo)

        # Fullscreen button with white icon directly on top bar
        self.fullscreen_btn = QPushButton("Fullscreen")
        self.fullscreen_btn.setIcon(_create_white_action_icon(_draw_fullscreen_tool_icon))
        self.fullscreen_btn.setToolTip("Toggle Fullscreen [F12]")
        self.fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        top_bar.addWidget(self.fullscreen_btn)

        # Translate button with dropdown options (EN / ID / Bake)
        # Visible ONLY when more than one subfolder is selected on the sidebar
        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setToolTip("Add selected folders to translation queue (EN / ID)")
        self.translate_btn.setMenu(self.translate_menu)
        self.translate_btn.setVisible(False)
        top_bar.addWidget(self.translate_btn)

        # Queue Manager button with counter
        self.queue_mgr_btn = QPushButton("Queue Manager (0)")
        self.queue_mgr_btn.setToolTip("Open Translation Queue Manager [Ctrl+J]")
        self.queue_mgr_btn.clicked.connect(self._on_open_queue_dialog)
        top_bar.addWidget(self.queue_mgr_btn)

        top_bar.addStretch()

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+Shift+B"), self, self._toggle_sidebar)
        QShortcut(QKeySequence("Ctrl+E"), self, lambda: self._on_add_to_queue("en"))
        QShortcut(QKeySequence("Ctrl+I"), self, lambda: self._on_add_to_queue("id"))
        QShortcut(QKeySequence("Ctrl+J"), self, self._on_open_queue_dialog)
        QShortcut(QKeySequence("T"), self, self._toggle_translation_overlay)
        QShortcut(QKeySequence("F12"), self, self._toggle_fullscreen)

        # Compatibility aliases for actions / tests
        self.open_btn = self.act_open
        self.batch_rename_btn = self.act_batch_rename
        self.settings_btn = self.act_settings
        self.start_queue_btn = self.queue_mgr_btn
        self.add_queue_btn = self.translate_btn
        self.queue_btn = self.queue_mgr_btn

        main_layout.addWidget(self.top_bar_widget)

        # Main Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left folder list
        self.folder_list = FolderListWidget()
        self.folder_list.folder_selected.connect(self._on_folder_selected)
        self.folder_list.rename_requested.connect(self._on_rename_folder)
        self.folder_list.selection_count_changed.connect(self._on_folder_selection_count_changed)
        self.folder_list.context_menu_requested.connect(self._show_folder_context_menu)
        self.splitter.addWidget(self.folder_list)

        # Right container
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.preview_pane = PreviewPaneWidget()
        self.preview_pane.zoom_changed.connect(self._on_zoom_changed_from_preview)
        self.preview_pane.manual_box_created.connect(self._on_manual_box_created)
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

        # Root directory path display pill in bottom footer
        self.path_label = QLabel("No root folder selected")
        self.path_label.setStyleSheet("""
            QLabel {
                background-color: #141417;
                color: #94a3b8;
                border: 1px solid #27272a;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 11px;
                font-style: italic;
            }
        """)
        self.status_bar.addPermanentWidget(self.path_label)

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

        # 1. File Menu: Open Root Folder, Exit
        file_menu = menubar.addMenu("&File")
        self.act_open = file_menu.addAction("Open Root Folder...")
        self.act_open.setShortcut("Ctrl+O")
        self.act_open.triggered.connect(self._on_open_folder)

        file_menu.addSeparator()

        self.act_exit = file_menu.addAction("Exit")
        self.act_exit.setShortcut("Ctrl+Q")
        self.act_exit.triggered.connect(self.close)

        # Standalone actions for shortcuts / queue controls / compatibility
        self.act_batch_rename = QAction("Batch Rename Folders...", self)
        self.act_batch_rename.triggered.connect(self._on_batch_rename_folders)

        self.act_settings = QAction("Settings...", self)
        self.act_settings.setShortcut("Ctrl+,")
        self.act_settings.triggered.connect(self._on_open_settings)

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
        self.translate_menu.addSeparator()
        self.act_rasterize = self.translate_menu.addAction("Bake Translated Pages to Sibling Folder...")
        self.act_rasterize.setShortcut("Ctrl+B")
        self.act_rasterize.triggered.connect(self._on_add_rasterize_to_queue)
        self.queue_sub = self.translate_menu

        # Overlay & fullscreen actions for keyboard shortcuts / testing
        self.act_overlay = QAction("Toggle Translation Overlay", self)
        self.act_overlay.setShortcut("T")
        self.act_overlay.triggered.connect(self._toggle_translation_overlay)
        self.addAction(self.act_overlay)

        self.act_box_tool = QAction("Box Select Tool", self)
        self.act_box_tool.setShortcut("B")
        self.act_box_tool.triggered.connect(self._toggle_box_select_tool)
        self.addAction(self.act_box_tool)

        self.act_fullscreen = QAction("Fullscreen", self)
        self.act_fullscreen.setShortcut("F12")
        self.act_fullscreen.triggered.connect(self._toggle_fullscreen)
        self.addAction(self.act_fullscreen)

        # 2. Help Menu: NO icons, NO dividers
        help_menu = menubar.addMenu("&Help")

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

    def _on_folder_selection_count_changed(self, count: int):
        self.translate_btn.setVisible(count > 1)

    def _show_folder_context_menu(self, folder_item: FolderItem, global_pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet("""
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

        act_en = menu.addAction("Translate to English [EN]")
        act_en.setShortcut("Ctrl+E")
        act_en.triggered.connect(lambda: self._on_add_to_queue(target_lang="en"))

        act_id = menu.addAction("Translate to Indonesian [ID]")
        act_id.setShortcut("Ctrl+I")
        act_id.triggered.connect(lambda: self._on_add_to_queue(target_lang="id"))

        act_bake = menu.addAction("Bake Translated Pages to Sibling Folder...")
        act_bake.setShortcut("Ctrl+B")
        act_bake.triggered.connect(self._on_add_rasterize_to_queue)

        menu.addSeparator()

        act_batch_rename = menu.addAction("Batch Rename Folders...")
        act_batch_rename.triggered.connect(self._on_batch_rename_folders)

        menu.exec(global_pos)

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
        folder = self.folder_list.get_current_folder()
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
            "About KomaShift",
            f"<h3>KomaShift v{__version__}</h3>"
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
        last_dir = self.settings_vm.get_last_root_folder()
        if last_dir and Path(last_dir).is_dir():
            self._load_root_folder(Path(last_dir))
        if "pytest" not in sys.modules:
            self.settings_vm.check_for_updates(
                lambda v: self.status_bar.showMessage(f"KomaShift v{v} is available!", 15000)
                if getattr(self, "status_bar", None) else None
            )

    def _load_root_folder(self, root_path: Path):
        self.path_label.setText(str(root_path))
        folders = self.library_vm.load_directory(root_path)
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
        start_dir = self.settings_vm.get_last_root_folder() or ""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Root Folder", str(start_dir))
        if dir_path:
            self.settings_vm.set_last_root_folder(dir_path)
            self._load_root_folder(Path(dir_path))

    def _on_image_selected(self, image_path: Optional[Path]):
        self.preview_pane.set_image(image_path)
        if image_path and image_path.exists():
            curr_idx = self.thumbnail_strip.get_current_index() + 1
            total_imgs = len(self.thumbnail_strip.image_paths)
            if total_imgs > 0:
                self.status_bar.showMessage(f"Page {curr_idx}/{total_imgs}: {image_path.name}")
            ws = TranslationWorkspace(image_path.parent)
            trans_map = {}
            for lang in ("id", "en"):
                translations = ws.load_translations(target_lang=lang)
                if translations:
                    ocr_results = ws.load_ocr_results()
                    page_data = ocr_results.get(image_path.name)
                    if page_data and page_data.bubbles:
                        if any(b.id in translations for b in page_data.bubbles):
                            trans_map = translations
                            self.preview_pane.set_translation_data(page_data, trans_map)
                            break
            if not trans_map:
                ocr_results = ws.load_ocr_results()
                page_data = ocr_results.get(image_path.name)
                if page_data and page_data.bubbles:
                    self.preview_pane.set_translation_data(page_data, {})

    def _toggle_translation_overlay(self):
        enabled = self.preview_pane.toggle_translation_overlay()
        state_str = "ON" if enabled else "OFF"
        self.overlay_toggle_btn.setText(f"Overlay ({state_str})")
        self.overlay_toggle_btn.setToolTip(f"Toggle Translation Overlay ({state_str}) [T]")
        self.act_overlay.setText(f"Toggle Translation Overlay ({state_str})")
        self.status_bar.showMessage(f"Translation overlay turned {state_str.lower()}")

    def _toggle_box_select_tool(self):
        new_state = not self.preview_pane.is_manual_box_mode()
        self.preview_pane.set_manual_box_mode(new_state)
        self.box_tool_btn.setChecked(new_state)
        if new_state:
            # Also ensure overlay text is displayed so the user sees results
            self.preview_pane.set_translation_overlay_enabled(True)
            self.overlay_toggle_btn.setText("Overlay (ON)")
            self.overlay_toggle_btn.setToolTip("Toggle Translation Overlay (ON) [T]")
            self.act_overlay.setText("Toggle Translation Overlay (ON)")
            self.status_bar.showMessage("Box Select Mode: Click and drag over untranslated manga text to label.")
        else:
            self.status_bar.showMessage("Box Select Mode disabled.")

    def _on_manual_box_created(self, bbox: tuple, target_lang: Optional[str] = None):
        """
        Triggered when user draws a box over untranslated speech/sound on the current page.
        Immediately prompts user with 'Translate to EN' and 'Translate to ID'.
        If chosen, records the box geometry, sets target_lang, and pushes the job into Queue Manager for this image.
        If dismissed / cancelled, discards the box.
        ZERO OCR, segmentation, or translation is performed directly in UI; strictly deferred to Queue Manager.
        """
        curr_img = self.thumbnail_strip.get_current_image()
        if not curr_img or not curr_img.exists():
            return

        bx, by, bw, bh = bbox

        if target_lang is None:
            # Immediately show pop-up menu at cursor
            popup = QMenu(self)
            popup.setStyleSheet("""
                QMenu {
                    background-color: #1e1e24;
                    color: #ffffff;
                    border: 1px solid #3f3f46;
                    padding: 4px;
                }
                QMenu::item {
                    color: #ffffff;
                    padding: 6px 20px 6px 20px;
                    border-radius: 4px;
                }
                QMenu::item:selected {
                    background-color: #27272a;
                    color: #ffffff;
                }
            """)
            act_en = popup.addAction("Translate to EN")
            act_id = popup.addAction("Translate to ID")
            chosen = popup.exec(QCursor.pos())
            if not chosen:
                # User dismissed menu / clicked outside: discard box
                return

            target_lang = "en" if chosen == act_en else "id"
        else:
            target_lang = target_lang.lower().strip()

        folder_path = curr_img.parent

        try:
            all_paths = self.thumbnail_strip.image_paths
            curr_idx = all_paths.index(curr_img) if curr_img in all_paths else 0
            pw, ph = 1000, 1000
            if hasattr(self.preview_pane, "raw_pixmap") and self.preview_pane.raw_pixmap:
                pw, ph = self.preview_pane.raw_pixmap.width(), self.preview_pane.raw_pixmap.height()

            page_data, translations, new_bubble = self.translation_vm.add_manual_bubble(
                folder_path=folder_path,
                image_path=curr_img,
                image_index=curr_idx,
                bbox=(bx, by, bw, bh),
                target_lang=target_lang,
                image_size=(pw, ph)
            )

            # Refresh preview overlay: ensure this ID has no translation residue and displays as [Manual Label]
            self.preview_pane.set_translation_data(page_data, translations)
            self.folder_list.set_folder_status(folder_path, "queued")
            self.status_bar.showMessage(
                f"Manual box ({bw}x{bh}) [Translate to {target_lang.upper()}] enqueued for {curr_img.name}."
            )
        except Exception as e:
            self.status_bar.showMessage(f"Error recording manual box: {e}")

    def _on_add_labeling_to_queue(self, target_lang: str = "en"):
        curr_img = self.thumbnail_strip.get_current_image()
        folder_path = curr_img.parent if (curr_img and curr_img.exists()) else None
        if not folder_path:
            folder = self.folder_list.get_current_folder()
            folder_path = folder.path if folder else None
        if not folder_path or not folder_path.is_dir():
            QMessageBox.warning(self, "No Chapter Selected", "Please select a chapter folder or image first.")
            return

        api_key, *_ = self._get_api_credentials()
        if not api_key:
            reply = QMessageBox.question(
                self,
                "API Key Missing",
                "An API Key is required for translation.\nWould you like to open Queue Manager Settings now to set it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_open_queue_dialog(tab="settings")
            return

        ws = TranslationWorkspace(folder_path)
        manual_fns = ws.get_manual_labeled_page_filenames(target_lang)

        all_imgs = sorted([
            p for p in folder_path.iterdir()
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        ], key=natural_sort_key)
        if not all_imgs:
            QMessageBox.warning(self, "No Images Found", f"No supported images found in '{folder_path.name}'.")
            return

        manual_selected = [p for p in all_imgs if p.name in manual_fns]
        if not manual_selected and curr_img and curr_img in all_imgs:
            manual_selected = [curr_img]

        existing_job = None
        for j in self.queue_manager.jobs:
            if j.folder_path == folder_path and j.job_type == JobType.TRANSLATION:
                existing_job = j
                break

        lang_code = target_lang.lower()
        if existing_job:
            if existing_job.target_lang.lower() != lang_code:
                existing_job.target_lang = "mix"
            if existing_job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                existing_job.status = JobStatus.PENDING
                existing_job.status_message = "Pending manual label translation"
                existing_job.error_message = None
                existing_job.progress_pct = 0
            if manual_selected:
                current_selected = set(existing_job.selected_image_paths) if existing_job.selected_image_paths else set()
                for p in manual_selected:
                    current_selected.add(p)
                existing_job.selected_image_paths = [p for p in existing_job.image_paths if p in current_selected]
            self.queue_manager.queue_updated.emit()
            self.queue_manager.notify_overall_progress()
            job = existing_job
        else:
            job = self.queue_manager.add_job(
                folder_path=folder_path,
                image_paths=all_imgs,
                target_lang=lang_code
            )
            if manual_selected:
                job.selected_image_paths = manual_selected
                self.queue_manager.queue_updated.emit()

        self.folder_list.set_folder_status(folder_path, "queued")
        self.status_bar.showMessage(
            f"Added {len(manual_selected)} page(s) with manual labels to queue ({job.lang_display})."
        )
        self._on_open_queue_dialog(tab="pages")

    def _on_rasterize_clicked(self):
        curr_img = self.thumbnail_strip.get_current_image()
        folder_path = curr_img.parent if (curr_img and curr_img.exists()) else None
        if not folder_path:
            folder = self.folder_list.get_current_folder()
            folder_path = folder.path if folder else None
        if not folder_path or not folder_path.is_dir():
            QMessageBox.warning(self, "No Chapter Selected", "Please select a chapter folder or image first.")
            return

        all_imgs = sorted([
            p for p in folder_path.iterdir()
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        ], key=natural_sort_key)
        if not all_imgs:
            QMessageBox.warning(self, "No Images Found", f"No supported images found in '{folder_path.name}'.")
            return

        ws = TranslationWorkspace(folder_path)
        translated_fns = ws.get_translated_page_filenames()
        if not translated_fns:
            reply = QMessageBox.question(
                self,
                "No Translations Found",
                f"No translated pages detected in '{folder_path.name}'.\n"
                f"Do you still want to enqueue rasterization for all {len(all_imgs)} pages?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        job = self.queue_manager.add_rasterize_job(
            folder_path=folder_path,
            image_paths=all_imgs
        )
        if translated_fns:
            job.selected_image_paths = [p for p in all_imgs if p.name in translated_fns]
            self.queue_manager.queue_updated.emit()

        self.status_bar.showMessage(f"Rasterize job for '{folder_path.name}' added to Queue.")
        self._on_open_queue_dialog(tab="pages")

    def _get_api_credentials(self):
        return self.settings_vm.get_api_credentials()

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

    def _on_open_queue_dialog(self, tab: str = "queue"):
        if self._queue_dialog is None:
            self._queue_dialog = QueueDialog(
                self.queue_manager,
                parent=self,
                settings=self.settings,
                thumbnail_cache=self.thumbnail_cache
            )
        if tab:
            self._queue_dialog.open_tab(tab)
        self._queue_dialog.show()
        self._queue_dialog.raise_()
        self._queue_dialog.activateWindow()

    def _on_add_to_queue(self, target_lang: str = "en"):
        folders = self.folder_list.get_selected_folders()
        if not folders:
            QMessageBox.warning(self, "No Folder Selected", "Please select a folder containing images to add to the queue.")
            return

        api_key, *_ = self._get_api_credentials()
        if not api_key:
            reply = QMessageBox.question(
                self,
                "API Key Missing",
                "An API Key is required for translation.\nWould you like to open Queue Manager Settings now to set it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_open_queue_dialog(tab="settings")
            return

        lang_name = "Indonesian [ID]" if target_lang.lower() == "id" else "English [EN]"

        if len(folders) == 1:
            folder = folders[0]
            if not folder.image_paths:
                QMessageBox.warning(self, "No Images Found", f"No images found in '{folder.name}'.")
                return

            self.queue_manager.add_job(
                folder_path=folder.path,
                image_paths=folder.image_paths,
                target_lang=target_lang
            )
            self.folder_list.set_folder_status(folder.path, "queued")
            self.status_bar.showMessage(f"Added '{folder.name}' to queue ({lang_name}). Click 'Start Queue' to begin.")
        else:
            added_count = 0
            for folder in folders:
                if not folder.image_paths:
                    continue
                self.queue_manager.add_job(
                    folder_path=folder.path,
                    image_paths=folder.image_paths,
                    target_lang=target_lang
                )
                self.folder_list.set_folder_status(folder.path, "queued")
                added_count += 1
            self.status_bar.showMessage(f"Added {added_count} folders to translation queue ({lang_name}). Open Queue Manager to start.")

    def _on_add_rasterize_to_queue(self):
        folders = self.folder_list.get_selected_folders()
        if not folders:
            QMessageBox.warning(self, "No Folder Selected", "Please select a folder containing images to bake.")
            return

        if len(folders) == 1:
            folder = folders[0]
            if not folder or not folder.image_paths:
                QMessageBox.warning(self, "No Folder Selected", "Please select a folder containing images to bake.")
                return

            ws = TranslationWorkspace(folder.path)
            translated_en = ws.get_translated_page_filenames("en")
            translated_id = ws.get_translated_page_filenames("id")
            if not translated_en and not translated_id:
                QMessageBox.warning(
                    self,
                    "No Translations Found",
                    f"No translation data was found for '{folder.name}'.\n\nPlease translate pages first before baking them into permanent images."
                )
                return

            target_lang = "id" if (translated_id and not translated_en) else "en"
            self.queue_manager.add_rasterize_job(
                folder_path=folder.path,
                image_paths=folder.image_paths,
                target_lang=target_lang
            )
            self.status_bar.showMessage(f"Added '{folder.name}' to queue for baking. Open Queue Manager to start.")
            self._on_open_queue_dialog()
        else:
            added_count = 0
            for folder in folders:
                if not folder.image_paths:
                    continue
                ws = TranslationWorkspace(folder.path)
                translated_en = ws.get_translated_page_filenames("en")
                translated_id = ws.get_translated_page_filenames("id")
                if not translated_en and not translated_id:
                    continue
                target_lang = "id" if (translated_id and not translated_en) else "en"
                self.queue_manager.add_rasterize_job(
                    folder_path=folder.path,
                    image_paths=folder.image_paths,
                    target_lang=target_lang
                )
                added_count += 1
            if added_count == 0:
                QMessageBox.warning(
                    self,
                    "No Translations Found",
                    "None of the selected folders have completed translations to bake."
                )
                return
            self.status_bar.showMessage(f"Added {added_count} folders to queue for baking. Open Queue Manager to start.")
            self._on_open_queue_dialog()

    def _toggle_queue(self):
        if self.queue_manager.is_running:
            self.queue_manager.pause_queue()
        else:
            api_key, *_ = self._get_api_credentials()
            if not api_key:
                reply = QMessageBox.question(
                    self,
                    "API Key Missing",
                    "An API Key is required for translation.\nWould you like to open Queue Manager Settings now to set it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._on_open_queue_dialog(tab="settings")
                return

            for job in self.queue_manager.jobs:
                if job.status == JobStatus.PENDING and job.job_type == JobType.TRANSLATION:
                    selected = job.selected_image_paths if job.selected_image_paths else job.image_paths
                    if not selected:
                        continue
                    ws = TranslationWorkspace(job.folder_path)
                    translated_fns = ws.get_translated_page_filenames(job.target_lang)
                    cached_selected = [p for p in selected if p.name in translated_fns]

                    if cached_selected:
                        if len(cached_selected) == len(selected):
                            page_desc = f"all {len(selected)} selected image(s)"
                        else:
                            page_desc = f"{len(cached_selected)} of {len(selected)} selected image(s)"

                        reply = QMessageBox.question(
                            self,
                            "Translation Cache Found",
                            f"Translation ({job.lang_display}) data already exists for {page_desc} in '{job.folder_name}'.\n\n"
                            "Would you like to re-scan and translate them again from scratch?\n\n"
                            "- Yes: Re-translate and overwrite cached pages.\n"
                            "- No: Skip already translated pages and only process untranslated ones.",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                            QMessageBox.StandardButton.No
                        )
                        if reply == QMessageBox.StandardButton.Cancel:
                            return
                        elif reply == QMessageBox.StandardButton.No:
                            untranslated = [p for p in selected if p.name not in translated_fns]
                            if not untranslated:
                                job.status = JobStatus.COMPLETED
                                job.status_message = "All selected pages already translated"
                                continue
                            job.selected_image_paths = untranslated

            self.queue_manager.start_queue()

    def _on_queue_updated(self):
        pending = self.queue_manager.pending_count
        self.queue_mgr_btn.setText(f"Queue Manager ({pending})")
        self.act_queue_mgr.setText(f"Translation Queue Manager... ({pending})")

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
            self.status_bar.showMessage(f"Translated '{job_name}' successfully.")
            curr_folder = self.folder_list.get_current_folder()
            if curr_folder and job and curr_folder.path == job.folder_path:
                curr_img = self.thumbnail_strip.get_current_image()
                if curr_img:
                    self._on_image_selected(curr_img)
        else:
            self.status_bar.showMessage(f"Translation failed for '{job_name}': {message}")

    def _on_translate_folder(self):
        """Compatibility trigger: adds current folder to queue and starts processing."""
        self._on_add_to_queue(target_lang="en")
        if self.queue_manager.pending_count > 0 and not self.queue_manager.is_running:
            self._toggle_queue()

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
            self.menuBar().show()
            self.top_bar_widget.show()
            if not getattr(self, "_sidebar_hidden", False):
                self.folder_list.show()
            self.thumbnail_strip.show()
            self.status_bar.show()
            if getattr(self, "_was_maximized", False):
                self.showMaximized()
            else:
                self.showNormal()
            if hasattr(self, "_saved_splitter_sizes") and self._saved_splitter_sizes and self._saved_splitter_sizes[0] > 0:
                self.splitter.setSizes(self._saved_splitter_sizes)
            else:
                self.splitter.setSizes([260, max(100, self.width() - 260)])
            self.folder_list.scroll_to_current()
            self.thumbnail_strip.scroll_to_current()
            self.act_fullscreen.setText("Fullscreen")
            self.fullscreen_btn.setText("Fullscreen")
        else:
            self._was_maximized = self.isMaximized()
            self._saved_splitter_sizes = self.splitter.sizes()
            self.menuBar().hide()
            self.top_bar_widget.hide()
            self.folder_list.hide()
            self.splitter.setSizes([0, max(1, self.width())])
            self.thumbnail_strip.hide()
            self.status_bar.hide()
            self.showFullScreen()
            self.act_fullscreen.setText("Exit Fullscreen")
            self.fullscreen_btn.setText("Exit Fullscreen")
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

                progress.setLabelText(f"Renaming ({i+1}/{total}):\n{folder.name}\n-> {new_name}")
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
            success_count, errors = self.library_vm.delete_folders(selected_folders)
            deleted_paths = [f.path for f in selected_folders[:success_count]]
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
        self._on_open_queue_dialog(tab="settings")

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

    def closeEvent(self, event):
        if hasattr(self, "thumbnail_cache") and self.thumbnail_cache:
            try:
                self.thumbnail_cache.shutdown(wait_ms=200)
            except Exception:
                pass
        super().closeEvent(event)




