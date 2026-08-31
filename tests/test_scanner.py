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

def test_natural_sorting_order(tmp_path: Path):
    folder = tmp_path / "manga_chapter_1"
    folder.mkdir()

    # Create files out of order
    file_names = ["107.webp", "108.webp", "109.webp", "11.webp", "110.webp", "111.webp", "1.webp", "2.webp"]
    for name in file_names:
        (folder / name).write_text("data")

    # Also create numbered folders
    f10 = tmp_path / "manga_chapter_10"
    f10.mkdir()
    (f10 / "01.jpg").write_text("data")

    f2 = tmp_path / "manga_chapter_2"
    f2.mkdir()
    (f2 / "01.jpg").write_text("data")

    results = scan_directory(tmp_path)
    assert len(results) == 3

    # Folders should be naturally sorted: chapter_1, chapter_2, chapter_10
    folder_names = [f.name for f in results]
    assert folder_names == ["manga_chapter_1", "manga_chapter_2", "manga_chapter_10"]

    # Images within chapter 1 should be naturally sorted
    ch1 = results[0]
    image_names = [p.name for p in ch1.image_paths]
    assert image_names == [
        "1.webp", "2.webp", "11.webp",
        "107.webp", "108.webp", "109.webp", "110.webp", "111.webp"
    ]
