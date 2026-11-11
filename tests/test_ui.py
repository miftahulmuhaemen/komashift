import pytest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox
from src.models.folder_item import FolderItem
from src.infra.qt_threads import ThumbnailCache
from src.infra.json_workspace import JsonTempWorkspace as TranslationWorkspace
from src.ui.folder_list import FolderListWidget
from src.ui.thumbnail_strip import ThumbnailStripWidget
from src.ui.preview_pane import PreviewPaneWidget
from src.ui.main_window import MainWindow

def test_folder_list_widget(qtbot, tmp_path: Path):
    widget = FolderListWidget()
    qtbot.addWidget(widget)

    f1 = FolderItem(path=tmp_path / "f1", name="f1", image_paths=[tmp_path / "f1" / "1.jpg"])
    f2 = FolderItem(path=tmp_path / "f2", name="f2", image_paths=[tmp_path / "f2" / "2.jpg"])
    widget.set_folders([f1, f2])

    assert widget.list_widget.count() == 2
    assert widget.get_current_folder().name == "f1"

    # Filter
    widget.filter_input.setText("f2")
    assert widget.list_widget.count() == 1
    assert widget.get_current_folder().name == "f2"

    # Remove item
    widget.remove_folder_item(f2.path)
    assert widget.list_widget.count() == 0
    assert widget.get_current_folder() is None

def test_folder_list_auto_selection_on_delete(qtbot, tmp_path: Path):
    widget = FolderListWidget()
    qtbot.addWidget(widget)

    f1 = FolderItem(path=tmp_path / "f1", name="f1", image_paths=[tmp_path / "f1" / "1.jpg"])
    f2 = FolderItem(path=tmp_path / "f2", name="f2", image_paths=[tmp_path / "f2" / "2.jpg"])
    f3 = FolderItem(path=tmp_path / "f3", name="f3", image_paths=[tmp_path / "f3" / "3.jpg"])
    widget.set_folders([f1, f2, f3])

    emitted_folders = []
    widget.folder_selected.connect(lambda f: emitted_folders.append(f))

    # Deleting f1 (index 0) should automatically select f2 (which becomes index 0)
    widget.remove_folder_item(f1.path)
    assert widget.list_widget.count() == 2
    assert widget.get_current_folder().name == "f2"
    assert emitted_folders[-1].name == "f2"

    # Deleting f3 (last item) should select f2 (new last item)
    widget.remove_folder_item(f3.path)
    assert widget.list_widget.count() == 1
    assert widget.get_current_folder().name == "f2"
    assert emitted_folders[-1].name == "f2"

    # Deleting the last remaining item should emit None
    widget.remove_folder_item(f2.path)
    assert widget.list_widget.count() == 0
    assert widget.get_current_folder() is None
    assert emitted_folders[-1] is None

def test_folder_list_batch_rename(qtbot, tmp_path: Path):
    widget = FolderListWidget()
    qtbot.addWidget(widget)

    f1 = FolderItem(path=tmp_path / "10 - Old", name="10 - Old")
    f2 = FolderItem(path=tmp_path / "02 - Old", name="02 - Old")
    widget.set_folders([f1, f2])

    updates = [
        (f1.path, tmp_path / "Chapter 10", "Chapter 10"),
        (f2.path, tmp_path / "Chapter 2", "Chapter 2")
    ]
    widget.rename_folder_items_batch(updates)

    # Should naturally sort Chapter 2 before Chapter 10
    assert widget._items[0].name == "Chapter 2"
    assert widget._items[1].name == "Chapter 10"

def test_folder_list_batch_selection_and_deletion(qtbot, tmp_path: Path):
    widget = FolderListWidget()
    qtbot.addWidget(widget)

    f1 = FolderItem(path=tmp_path / "f1", name="f1")
    f2 = FolderItem(path=tmp_path / "f2", name="f2")
    f3 = FolderItem(path=tmp_path / "f3", name="f3")
    f4 = FolderItem(path=tmp_path / "f4", name="f4")
    widget.set_folders([f1, f2, f3, f4])

    # Select f2 and f3
    widget.list_widget.item(1).setSelected(True)
    widget.list_widget.item(2).setSelected(True)

    selected = widget.get_selected_folders()
    selected_names = [f.name for f in selected]
    assert "f2" in selected_names
    assert "f3" in selected_names

    # Delete batch [f2, f3] -> f4 should now be selected at index 1
    widget.remove_folder_items([f2.path, f3.path])
    assert widget.list_widget.count() == 2
    assert widget.get_current_folder().name == "f4"

def test_preview_pane_widget(qtbot, tmp_path: Path):
    pane = PreviewPaneWidget()
    qtbot.addWidget(pane)

    img_path = tmp_path / "test.png"
    img = Image.new("RGB", (200, 100), color="red")
    img.save(img_path)

    pane.set_image(img_path)
    assert pane._current_pixmap is not None
    assert not pane._current_pixmap.isNull()

    # Test zoom presets
    pane.set_zoom_mode("50%")
    assert pane.get_zoom_mode() == 0.50
    assert pane.get_zoom_display_text() == "50%"

    pane.set_zoom_mode("75%")
    assert pane.get_zoom_mode() == 0.75

    pane.set_zoom_mode("100%")
    assert pane.get_zoom_mode() == 1.00

    pane.set_zoom_mode("120%")
    assert pane.get_zoom_mode() == 1.20

    pane.set_zoom_mode("Fit")
    assert pane.get_zoom_mode() == "fit"

    # Test zoom_in and zoom_out
    pane.zoom_in()
    assert pane.get_zoom_mode() == 1.00

    pane.zoom_in()
    assert pane.get_zoom_mode() == 1.20

    pane.zoom_out()
    assert pane.get_zoom_mode() == 1.00

    pane.set_image(None)
    assert pane._current_pixmap is None

def test_thumbnail_strip_horizontal_scroll(qtbot, tmp_path: Path):
    cache = ThumbnailCache()
    strip = ThumbnailStripWidget(cache)
    qtbot.addWidget(strip)

    assert strip.list_widget.flow() == strip.list_widget.Flow.LeftToRight
    assert strip.list_widget.isWrapping() is False

    p1 = tmp_path / "1.png"
    p2 = tmp_path / "2.png"
    Image.new("RGB", (50, 50), color="red").save(p1)
    Image.new("RGB", (50, 50), color="blue").save(p2)

    strip.set_images([p1, p2], select_index=0)
    assert strip.get_current_index() == 0
    assert strip.is_at_first() is True
    assert strip.is_at_last() is False

    strip.select_next()
    assert strip.get_current_index() == 1
    assert strip.is_at_last() is True

def test_continuous_cross_folder_navigation(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)

    f1_dir = tmp_path / "folder1"
    f2_dir = tmp_path / "folder2"
    f1_dir.mkdir()
    f2_dir.mkdir()

    img1_1 = f1_dir / "1.jpg"
    img1_2 = f1_dir / "2.jpg"
    img2_1 = f2_dir / "3.jpg"
    img2_2 = f2_dir / "4.jpg"

    for img in (img1_1, img1_2, img2_1, img2_2):
        Image.new("RGB", (50, 50), color="black").save(img)

    f1 = FolderItem(path=f1_dir, name="folder1", image_paths=[img1_1, img1_2])
    f2 = FolderItem(path=f2_dir, name="folder2", image_paths=[img2_1, img2_2])
    window.folder_list.set_folders([f1, f2])

    assert window.folder_list.get_current_folder().name == "folder1"
    assert window.thumbnail_strip.get_current_index() == 0

    # Advance within folder 1
    window._navigate_next()
    assert window.thumbnail_strip.get_current_index() == 1

    # Advance past end of folder 1 -> should rollover to folder 2, first image (index 0)
    window._navigate_next()
    assert window.folder_list.get_current_folder().name == "folder2"
    assert window.thumbnail_strip.get_current_index() == 0

    # Retreat before start of folder 2 -> should rollover to folder 1, last image (index 1)
    window._navigate_previous()
    assert window.folder_list.get_current_folder().name == "folder1"
    assert window.thumbnail_strip.get_current_index() == 1

def test_main_window_rename(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)

    f1_dir = tmp_path / "orig_folder"
    f1_dir.mkdir()
    img1 = f1_dir / "1.jpg"
    Image.new("RGB", (50, 50), color="red").save(img1)

    f1 = FolderItem(path=f1_dir, name="orig_folder", image_paths=[img1])
    window.folder_list.set_folders([f1])

    with patch("src.ui.main_window.RenameDialog.exec", return_value=True), \
         patch("src.ui.main_window.RenameDialog.get_new_name", return_value="renamed_folder"):
        window._on_rename_folder()
        assert window.folder_list.get_current_folder().name == "renamed_folder"
        assert window.folder_list.get_current_folder().path == tmp_path / "renamed_folder"
        assert (tmp_path / "renamed_folder").exists()
        assert not f1_dir.exists()
    window.thumbnail_cache.thread_pool.waitForDone(2000)

def test_rename_dialog_widget(qtbot):
    from src.ui.rename_dialog import RenameDialog

    sample_name = "nhentai-672171 - [Chinjao Girl. (Special G, Yamagiri)]"
    dialog = RenameDialog(sample_name)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.text_edit.toPlainText() == sample_name
    assert dialog.ok_btn.isEnabled() is True
    assert dialog.get_new_name() == sample_name

    # Test invalid character handling
    dialog.text_edit.setPlainText('Invalid: Name?')
    assert dialog.ok_btn.isEnabled() is False
    assert "Invalid character" in dialog.warning_label.text()

    dialog.text_edit.setPlainText("Valid New Name")
    assert dialog.ok_btn.isEnabled() is True
    assert dialog.get_new_name() == "Valid New Name"

def test_batch_rename_dialog_widget(qtbot, tmp_path: Path):
    from src.ui.batch_rename_dialog import BatchRenameDialog

    f1 = FolderItem(path=tmp_path / "f1", name="nhentai-672171 - [Chinjao Girl.] (01)")
    f2 = FolderItem(path=tmp_path / "f2", name="nhentai-123456 - [Another Title] (02)")
    dialog = BatchRenameDialog([f1, f2])
    qtbot.addWidget(dialog)
    dialog.show()

    # Initial state
    assert dialog.ok_btn.isEnabled() is False  # No changes made yet

    # Test Strip Leading ID
    dialog.strip_leading_id()
    assert dialog._new_names[0] == "[Chinjao Girl.] (01)"
    assert dialog._new_names[1] == "[Another Title] (02)"
    assert dialog.ok_btn.isEnabled() is True

    # Test Strip Trailing Numbers
    dialog.strip_trailing_numbers()
    assert dialog._new_names[0] == "[Chinjao Girl.]"
    assert dialog._new_names[1] == "[Another Title]"

    # Test Trim Head One & Untrim Head One
    dialog.trim_head_one()
    assert dialog._new_names[0].startswith("Chinjao")
    dialog.untrim_head_one()
    assert dialog._new_names[0].startswith("[Chinjao")

    # Test Trim Tail One & Untrim Tail One
    dialog.trim_tail_one()
    assert dialog._new_names[0].endswith("Girl.")
    dialog.untrim_tail_one()
    assert dialog._new_names[0].endswith("Girl.]")

    # Test Add Prefix & Suffix
    dialog.head_input.setText("Prefix_")
    dialog.add_head()
    assert dialog._new_names[0].startswith("Prefix_")

    dialog.tail_input.setText("_Suffix")
    dialog.add_tail()
    assert dialog._new_names[0].endswith("_Suffix")

    # Test Reset
    dialog.reset_original()
    assert dialog._new_names[0] == f1.name
    assert dialog._new_names[1] == f2.name

    # Test Duplicate Name Detection
    dialog._new_names[0] = "Same Name"
    dialog._new_names[1] = "Same Name"
    dialog._refresh_table()
    assert dialog.ok_btn.isEnabled() is False
    assert 'Duplicate "Same Name" in Rows 1, 2' in dialog.warning_label.text()

def test_main_window_batch_rename(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)

    f1_dir = tmp_path / "nhentai-1 - Album A"
    f2_dir = tmp_path / "nhentai-2 - Album B"
    f1_dir.mkdir()
    f2_dir.mkdir()

    f1 = FolderItem(path=f1_dir, name="nhentai-1 - Album A")
    f2 = FolderItem(path=f2_dir, name="nhentai-2 - Album B")
    window.folder_list.set_folders([f1, f2])

    with patch("src.ui.main_window.BatchRenameDialog.exec", return_value=True), \
         patch("src.ui.main_window.BatchRenameDialog.get_rename_pairs", return_value=[(f1, "Album A"), (f2, "Album B")]):
        window._on_batch_rename_folders()
        assert window.folder_list._items[0].name == "Album A"
        assert window.folder_list._items[1].name == "Album B"
    window.thumbnail_cache.thread_pool.waitForDone(2000)

def test_double_click_rename_trigger(qtbot, tmp_path: Path):
    widget = FolderListWidget()
    qtbot.addWidget(widget)

    f1 = FolderItem(path=tmp_path / "f1", name="f1")
    widget.set_folders([f1])

    requested = []
    widget.rename_requested.connect(lambda f: requested.append(f))

    item = widget.list_widget.item(0)
    widget.list_widget.itemDoubleClicked.emit(item)

    assert len(requested) == 1
    assert requested[0].name == "f1"

def test_persistent_folder_restore(qtbot, tmp_path: Path):
    root = tmp_path / "root_dir"
    root.mkdir()
    f1 = root / "sub1"
    f1.mkdir()
    Image.new("RGB", (50, 50), color="blue").save(f1 / "img.jpg")

    # Set setting
    from PyQt6.QtCore import QSettings
    settings = QSettings("KomaShift", "KomaShift")
    settings.setValue("last_root_folder", str(root))

    window = MainWindow()
    qtbot.addWidget(window)

    # Window should automatically load root_dir on start
    assert window.folder_list.list_widget.count() == 1
    assert window.folder_list.get_current_folder().name == "sub1"

def test_event_filter_arrow_navigation_in_fullscreen(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    f1_dir = tmp_path / "f1"
    f1_dir.mkdir()
    img1 = f1_dir / "1.jpg"
    img2 = f1_dir / "2.jpg"
    Image.new("RGB", (50, 50), color="red").save(img1)
    Image.new("RGB", (50, 50), color="blue").save(img2)

    f1 = FolderItem(path=f1_dir, name="f1", image_paths=[img1, img2])
    window.folder_list.set_folders([f1])

    window._toggle_fullscreen()
    assert window.isFullScreen() is True
    assert window.thumbnail_strip.get_current_index() == 0

    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent

    # Simulate Right arrow event
    right_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Right, Qt.KeyboardModifier.NoModifier)
    handled = window.eventFilter(window.preview_pane.scroll_area, right_event)
    assert handled is True
    assert window.thumbnail_strip.get_current_index() == 1

    # Simulate Left arrow event
    left_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Left, Qt.KeyboardModifier.NoModifier)
    handled = window.eventFilter(window.preview_pane.scroll_area, left_event)
    assert handled is True
    assert window.thumbnail_strip.get_current_index() == 0

def test_scroll_position_resets_on_new_image(qtbot, tmp_path: Path):
    pane = PreviewPaneWidget()
    qtbot.addWidget(pane)
    pane.resize(400, 300)
    pane.show()

    # Create tall images that cause scrollbars to appear at 100% zoom
    img1_path = tmp_path / "img1.png"
    img2_path = tmp_path / "img2.png"
    Image.new("RGB", (300, 1200), color="red").save(img1_path)
    Image.new("RGB", (300, 1200), color="blue").save(img2_path)

    pane.set_zoom_mode("100%")
    pane.set_image(img1_path)

    # Scroll down on image 1
    pane.scroll_area.verticalScrollBar().setValue(400)
    assert pane.scroll_area.verticalScrollBar().value() == 400

    # Moving to image 2 should reset scroll position to top (0)
    pane.set_image(img2_path)
    assert pane.scroll_area.verticalScrollBar().value() == 0

def test_page_up_page_down_shortcuts(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(600, 400)
    window.show()

    f1_dir = tmp_path / "f1"
    f1_dir.mkdir()
    img1 = f1_dir / "1.png"
    img2 = f1_dir / "2.png"
    Image.new("RGB", (400, 1500), color="red").save(img1)
    Image.new("RGB", (400, 1500), color="blue").save(img2)

    f1 = FolderItem(path=f1_dir, name="f1", image_paths=[img1, img2])
    window.folder_list.set_folders([f1])
    window.preview_pane.set_zoom_mode("100%")

    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent

    # Initial position at top
    assert window.preview_pane.scroll_area.verticalScrollBar().value() == 0

    # PageDown on MainWindow
    pagedown_event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_PageDown, Qt.KeyboardModifier.NoModifier)
    handled = window.eventFilter(window, pagedown_event)
    assert handled is True
    assert window.preview_pane.scroll_area.verticalScrollBar().value() > 0

    # Navigating to next image restarts scroll position from the top
    window._navigate_next()
    assert window.thumbnail_strip.get_current_index() == 1
    assert window.preview_pane.scroll_area.verticalScrollBar().value() == 0

    window.thumbnail_cache.thread_pool.waitForDone(2000)

def test_fullscreen_exit_preserves_folder_scroll_and_selection(qtbot, tmp_path: Path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1000, 600)
    window.show()

    folders = [
        FolderItem(path=tmp_path / f"folder_{i:03d}", name=f"Title {i:03d}", image_paths=[])
        for i in range(100)
    ]
    window.folder_list.set_folders(folders)

    # Select title 50
    window.folder_list.list_widget.setCurrentRow(50)
    window.folder_list.scroll_to_current()

    # Enter fullscreen
    window._toggle_fullscreen()
    assert window.isFullScreen() is True

    # Navigate to next folder in fullscreen
    window.folder_list.select_next_folder()
    assert window.folder_list.get_current_folder().name == "Title 051"

    # Exit fullscreen
    window._toggle_fullscreen()
    assert window.isFullScreen() is False

    # Check that current folder is still Title 051 and visible in viewport
    assert window.folder_list.get_current_folder().name == "Title 051"
    current_item = window.folder_list.list_widget.currentItem()
    assert current_item.isSelected() is True
    item_rect = window.folder_list.list_widget.visualItemRect(current_item)
    assert window.folder_list.list_widget.viewport().rect().contains(item_rect)

    window.thumbnail_cache.thread_pool.waitForDone(2000)

def test_fullscreen_exit_restores_maximized_state(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.showMaximized()
    qtbot.waitUntil(lambda: window.isMaximized())

    # Enter fullscreen
    window._toggle_fullscreen()
    qtbot.waitUntil(lambda: window.isFullScreen())

    # Exit fullscreen
    window._toggle_fullscreen()
    qtbot.waitUntil(lambda: not window.isFullScreen())
    qtbot.waitUntil(lambda: window.isMaximized())

    window.thumbnail_cache.thread_pool.waitForDone(2000)

def test_main_window_menubar_and_clean_toolbar(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    menubar = window.menuBar()
    actions = menubar.actions()
    titles = [a.text() for a in actions]
    assert "&File" in titles
    assert "&Edit" not in titles
    assert "&View" not in titles
    assert "&Help" in titles
    assert "&Window" not in titles

    # Top bar has sidebar toggle button with vector icon (no text label)
    assert hasattr(window, "sidebar_toggle_btn")
    assert window.sidebar_toggle_btn.text() == ""
    assert not window.sidebar_toggle_btn.icon().isNull()
    assert hasattr(window, "overlay_toggle_btn")
    assert "Overlay" in window.overlay_toggle_btn.text()
    assert hasattr(window, "zoom_combo")
    assert hasattr(window, "fullscreen_btn")
    assert "Fullscreen" in window.fullscreen_btn.text()
    assert hasattr(window, "translate_btn")
    assert "Translate" in window.translate_btn.text()
    assert not window.translate_btn.isVisible()

    # Dynamic visibility of translate_btn based on folder selection count (> 1)
    window.show()
    window._on_folder_selection_count_changed(1)
    assert window.translate_btn.isHidden()
    window._on_folder_selection_count_changed(2)
    assert not window.translate_btn.isHidden()
    window._on_folder_selection_count_changed(0)
    assert window.translate_btn.isHidden()

    # Sidebar toggle functionality and state retention
    assert not window.folder_list.isHidden()
    window._toggle_sidebar()
    assert window.folder_list.isHidden()
    assert "Show Sidebar" in window.sidebar_toggle_btn.toolTip()
    window._toggle_sidebar()
    assert not window.folder_list.isHidden()
    assert "Hide Sidebar" in window.sidebar_toggle_btn.toolTip()

    # Menu and action checks
    assert "Open" in window.open_btn.text()
    assert "Batch Rename" in window.batch_rename_btn.text()
    assert "Overlay" in window.overlay_toggle_btn.text()

    window.thumbnail_cache.thread_pool.waitForDone(2000)


def test_sidebar_scroll_and_status_indicators(qtbot):
    from src.ui.folder_list import FolderListWidget
    widget = FolderListWidget()
    qtbot.addWidget(widget)

    items = [
        FolderItem(path=Path(f"/tmp/ch_{i}"), name=f"Chapter {i:02d}", image_paths=[])
        for i in range(1, 50)
    ]
    widget.set_folders(items)

    p1 = Path("/tmp/ch_1")
    # 1. Test status indicators
    assert widget.get_folder_status(p1) == ""
    widget.set_folder_status(p1, "queued")
    assert "[Queued]" in widget.list_widget.item(0).text()

    widget.set_folder_status(p1, "running")
    assert "[Translating...]" in widget.list_widget.item(0).text()

    widget.set_folder_status(p1, "done")
    assert "[Done]" in widget.list_widget.item(0).text()

    # 2. Test scroll retention
    widget.list_widget.verticalScrollBar().setValue(10)
    val = widget.list_widget.verticalScrollBar().value()
    widget.save_scroll_state()
    assert widget._saved_scroll == val
    widget.list_widget.verticalScrollBar().setValue(0)
    widget.restore_scroll_state()
    assert widget.list_widget.verticalScrollBar().value() == val


def test_main_window_manual_box_and_queue_button(qtbot, tmp_path: Path):
    from unittest.mock import MagicMock
    from src.infra.json_workspace import JsonTempWorkspace as TranslationWorkspace

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    # 1. Top bar button checks
    assert hasattr(window, "box_tool_btn")
    assert window.box_tool_btn.text() == "Box Select"
    assert not window.box_tool_btn.icon().isNull()

    assert hasattr(window, "add_labeling_queue_btn")
    assert window.add_labeling_queue_btn.text() == "Add labeling to Queue"
    assert not window.add_labeling_queue_btn.icon().isNull()

    assert hasattr(window, "rasterize_btn")
    assert window.rasterize_btn.text() == "Rasterize"
    assert not window.rasterize_btn.icon().isNull()

    # Menu items on add_labeling_queue_btn
    menu_actions = [a.text() for a in window.add_labeling_menu.actions()]
    assert "Translate to EN" in menu_actions
    assert "Translate to ID" in menu_actions

    # 2. Setup mock chapter folder and image
    ch_dir = tmp_path / "chapter_01"
    ch_dir.mkdir()
    img1 = ch_dir / "01.png"
    Image.new("RGB", (400, 600), color="white").save(img1)

    f1 = FolderItem(path=ch_dir, name="chapter_01", image_paths=[img1])
    window.folder_list.set_folders([f1])
    window.folder_list.list_widget.setCurrentRow(0)
    window.thumbnail_strip.set_images([img1], select_index=0)
    window._on_image_selected(img1)

    # Mock OCR detector
    mock_detector = MagicMock()
    mock_detector._engine = MagicMock(return_value="當天不行!")
    mock_detector._segment_bubble = MagicMock(return_value=((50, 50, 100, 100), (100, 100), "oval"))
    window.queue_manager.detector = mock_detector

    # Trigger manual box creation with EN
    window._on_manual_box_created((50, 50, 100, 100), target_lang="en")

    # Verify bubble was saved to workspace as untranslated manual label without running OCR in UI
    ws = TranslationWorkspace(ch_dir)
    manual_pages = ws.get_manual_labeled_page_filenames("en")
    assert "01.png" in manual_pages

    ocr_results = ws.load_ocr_results()
    assert "01.png" in ocr_results
    assert len(ocr_results["01.png"].bubbles) == 1
    bubble = ocr_results["01.png"].bubbles[0]
    assert bubble.id.startswith("p1_m_")
    assert bubble.id not in ws.load_translations("en")
    assert bubble.is_manual is True
    assert bubble.text_ja == ""  # Zero OCR in UI; deferred to Queue Manager
    assert bubble.text_en == ""
    assert bubble.bbox == (50, 50, 100, 100)

    # Manual box creates a pending job in Queue Manager
    assert len(window.queue_manager.jobs) == 1
    job = window.queue_manager.jobs[0]
    assert job.folder_path == ch_dir
    assert img1 in job.selected_image_paths
    window._on_add_labeling_to_queue("en")

    # Verify job exists in Queue Manager with manual page selected
    assert len(window.queue_manager.jobs) == 1
    job = window.queue_manager.jobs[0]
    assert job.folder_path == ch_dir
    assert job.target_lang == "en"
    assert img1 in job.selected_image_paths

    window.thumbnail_cache.thread_pool.waitForDone(2000)


def test_manual_box_creation_prevents_cache_collision(qtbot, tmp_path: Path):
    ch_dir = tmp_path / "chapter_cached"
    ch_dir.mkdir()
    img1 = ch_dir / "01.png"
    Image.new("RGB", (400, 600), color="white").save(img1)

    # Existing workspace with old cached translation residue from previous automatic run
    ws = TranslationWorkspace(ch_dir)
    ws.save_translations({
        "p1_b1": "keep buying. keep buying...",
        "p1_b2": "keep buying. keep buying..."
    }, target_lang="en")

    window = MainWindow()
    qtbot.addWidget(window)
    f1 = FolderItem(path=ch_dir, name="chapter_cached", image_paths=[img1])
    window.folder_list.set_folders([f1])
    window.folder_list.list_widget.setCurrentRow(0)
    window.thumbnail_strip.set_images([img1], select_index=0)
    window._on_image_selected(img1)

    # Draw manual box over page
    window._on_manual_box_created((20, 20, 80, 80), target_lang="en")

    ocr_results = ws.load_ocr_results()
    assert "01.png" in ocr_results
    bubbles = ocr_results["01.png"].bubbles
    assert len(bubbles) == 1
    new_b = bubbles[0]

    # Verify ID is unique, prefixed with p1_m_, and does not collide with p1_b1 or p1_b2
    assert new_b.id.startswith("p1_m_")
    assert new_b.id not in ("p1_b1", "p1_b2")

    # Verify translation cache has no residue for this new manual bubble
    current_trans = ws.load_translations("en")
    assert new_b.id not in current_trans

    # Verify page is marked as having an untranslated manual label
    assert "01.png" in ws.get_manual_labeled_page_filenames("en")

    # Verify overlay has no translated text for the manual bubble (forcing [Manual Label] display)
    overlay = window.preview_pane.overlay
    assert overlay._translations.get(new_b.id) is None

    window.thumbnail_cache.thread_pool.waitForDone(2000)


def test_footer_path_label_and_fullscreen_immersion(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    # 1. Path label is in status_bar, not top_bar_widget
    assert hasattr(window, "path_label")
    assert window.path_label.parent() == window.status_bar
    assert len(window.path_label.text()) > 0

    # 2. Queue Manager button shows counter directly
    assert hasattr(window, "queue_mgr_btn")
    assert window.queue_mgr_btn.text() == "Queue Manager (0)"
    assert not hasattr(window, "status_queue_pill")

    # 3. Enter Fullscreen -> true immersive fullscreen (no menubar, no topbar, no sidebar panel, no footer)
    window._toggle_fullscreen()
    assert window.isFullScreen() is True
    assert window.menuBar().isHidden() is True
    assert window.top_bar_widget.isHidden() is True
    assert window.folder_list.isHidden() is True
    assert window.splitter.sizes()[0] == 0
    assert window.thumbnail_strip.isHidden() is True
    assert window.status_bar.isHidden() is True

    # 4. Exit Fullscreen -> restored cleanly
    window._toggle_fullscreen()
    assert window.isFullScreen() is False
    assert window.menuBar().isHidden() is False
    assert window.top_bar_widget.isHidden() is False
    assert window.folder_list.isHidden() is False
    assert window.splitter.sizes()[0] > 0
    assert window.thumbnail_strip.isHidden() is False
    assert window.status_bar.isHidden() is False

    window.thumbnail_cache.thread_pool.waitForDone(2000)









