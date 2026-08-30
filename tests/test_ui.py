import pytest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox
from src.models.folder_item import FolderItem
from src.services.thumbnail_cache import ThumbnailCache
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

    with patch("src.ui.main_window.QInputDialog.getText", return_value=("renamed_folder", True)):
        window._on_rename_folder()
        assert window.folder_list.get_current_folder().name == "renamed_folder"
        assert window.folder_list.get_current_folder().path == tmp_path / "renamed_folder"
        assert (tmp_path / "renamed_folder").exists()
        assert not f1_dir.exists()

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
    settings = QSettings("FolderImagePreviewer", "FolderImagePreviewer")
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




