import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QPushButton, QFileDialog, QMessageBox,
    QLabel, QStatusBar, QComboBox, QApplication,
    QProgressDialog
)
from PyQt6.QtCore import Qt, QSettings, QEvent
from PyQt6.QtGui import QKeyEvent, QIcon
from src.version import __version__
from src.models.folder_item import FolderItem
from src.services.scanner import scan_directory
from src.services.trash_service import send_folder_to_trash
from src.services.folder_service import rename_folder
from src.services.thumbnail_cache import ThumbnailCache
from src.ui.folder_list import FolderListWidget
from src.ui.thumbnail_strip import ThumbnailStripWidget
from src.ui.preview_pane import PreviewPaneWidget
from src.ui.rename_dialog import RenameDialog
from src.ui.batch_rename_dialog import BatchRenameDialog

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Windows Folder Image Previewer v{__version__}")
        self.resize(1150, 780)
        self._set_app_icon()
        self.settings = QSettings("FolderImagePreviewer", "FolderImagePreviewer")
        self.thumbnail_cache = ThumbnailCache()
        self._select_last_on_folder_load = False
        self._init_ui()
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

        # Top Bar
        self.top_bar_widget = QWidget()
        top_bar = QHBoxLayout(self.top_bar_widget)
        top_bar.setContentsMargins(8, 6, 8, 6)

        self.open_btn = QPushButton("Open Folder...")
        self.open_btn.setStyleSheet("padding: 6px 12px; font-weight: bold;")
        self.open_btn.clicked.connect(self._on_open_folder)
        top_bar.addWidget(self.open_btn)

        self.batch_rename_btn = QPushButton("🏷️ Batch Rename...")
        self.batch_rename_btn.setStyleSheet("padding: 6px 12px; font-weight: bold;")
        self.batch_rename_btn.setToolTip("Batch rename selected folders with quick transform tools")
        self.batch_rename_btn.clicked.connect(self._on_batch_rename_folders)
        top_bar.addWidget(self.batch_rename_btn)

        # Zoom Controls
        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet("margin-left: 8px; color: #aaa;")
        top_bar.addWidget(zoom_label)

        self.zoom_combo = QComboBox()
        self.zoom_combo.addItems(["Fit", "50%", "75%", "100%", "120%"])
        self.zoom_combo.setCurrentText("Fit")
        self.zoom_combo.currentTextChanged.connect(self._on_zoom_combo_changed)
        top_bar.addWidget(self.zoom_combo)

        self.fullscreen_btn = QPushButton("⛶ Fullscreen (F12)")
        self.fullscreen_btn.setStyleSheet("padding: 6px 12px;")
        self.fullscreen_btn.clicked.connect(self._toggle_fullscreen)
        top_bar.addWidget(self.fullscreen_btn)

        self.info_btn = QPushButton("ℹ Shortcuts & Help")
        self.info_btn.setStyleSheet("padding: 6px 12px; font-weight: bold;")
        self.info_btn.clicked.connect(self._on_show_shortcuts_info)
        top_bar.addWidget(self.info_btn)

        self.path_label = QLabel("No root folder selected")
        self.path_label.setStyleSheet("color: #888; font-style: italic; margin-left: 10px;")
        top_bar.addWidget(self.path_label, 1)

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
        self.thumbnail_strip.image_selected.connect(self.preview_pane.set_image)
        right_layout.addWidget(self.thumbnail_strip)

        self.splitter.addWidget(right_container)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        main_layout.addWidget(self.splitter, 1)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

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
        self.folder_list.set_folders(folders)
        self.status_bar.showMessage(f"Found {len(folders)} folders with images.")

    def _on_open_folder(self):
        start_dir = self.settings.value("last_root_folder", "") or ""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Root Folder", str(start_dir))
        if dir_path:
            self.settings.setValue("last_root_folder", dir_path)
            self._load_root_folder(Path(dir_path))

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
            self.folder_list.show()
            self.thumbnail_strip.show()
            self.status_bar.show()
            if hasattr(self, "_saved_splitter_sizes") and self._saved_splitter_sizes:
                self.splitter.setSizes(self._saved_splitter_sizes)
            self.folder_list.scroll_to_current()
            self.thumbnail_strip.scroll_to_current()
            self.fullscreen_btn.setText("⛶ Fullscreen (F12)")
        else:
            self._was_maximized = self.isMaximized()
            self._saved_splitter_sizes = self.splitter.sizes()
            self.top_bar_widget.hide()
            self.folder_list.hide()
            self.thumbnail_strip.hide()
            self.status_bar.hide()
            self.showFullScreen()
            self.fullscreen_btn.setText("🗗 Exit Fullscreen (F12)")
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
            "<li><b>Image Navigation:</b> Press <b>Left</b> / <b>Right</b> arrows.<br>"
            "<i>In fullscreen mode, navigating past the last image automatically continues to the next folder; navigating before the 1st image goes to the previous folder.</i></li>"
            "<li><b>Folder Navigation:</b> Press <b>Up</b> / <b>Down</b> arrows to change folder.</li>"
            "</ul>"
        )
        QMessageBox.information(self, "Shortcuts & Information", info_text)

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




