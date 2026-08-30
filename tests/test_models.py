from pathlib import Path
from src.models.folder_item import FolderItem

def test_folder_item_properties():
    folder_path = Path("/mock/albums/summer")
    images = [folder_path / "1.jpg", folder_path / "2.png"]
    item = FolderItem(path=folder_path, name="summer", image_paths=images)
    
    assert item.name == "summer"
    assert item.image_count == 2
    assert item.first_image == folder_path / "1.jpg"

def test_folder_item_empty_images():
    item = FolderItem(path=Path("/mock/empty"), name="empty", image_paths=[])
    assert item.image_count == 0
    assert item.first_image is None
