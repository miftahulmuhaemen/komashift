import pytest
from pathlib import Path
from src.services.scanner import scan_directory

def test_scan_directory_discovers_image_folders(tmp_path: Path):
    folder_a = tmp_path / "album_a"
    folder_a.mkdir()
    (folder_a / "img1.JPG").write_text("dummy")
    (folder_a / "img2.png").write_text("dummy")
    (folder_a / "notes.txt").write_text("dummy")

    folder_b = tmp_path / "album_b"
    folder_b.mkdir()
    (folder_b / "photo.webp").write_text("dummy")

    folder_empty = tmp_path / "empty_dir"
    folder_empty.mkdir()

    results = scan_directory(tmp_path)
    folder_names = [f.name for f in results]

    assert "album_a" in folder_names
    assert "album_b" in folder_names
    assert "empty_dir" not in folder_names

    item_a = next(f for f in results if f.name == "album_a")
    assert item_a.image_count == 2
