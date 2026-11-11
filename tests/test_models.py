from pathlib import Path
from src.models.folder_item import FolderItem
from src.models.translation_item import BubbleBlock, PageTranslation
from src.models.translation_job import TranslationJob, JobStatus, JobType


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


def test_bubble_block_round_trip():
    # Full fields
    b1 = BubbleBlock(
        id="b1",
        bbox=(10, 20, 100, 200),
        text_ja="こんにちは",
        text_en="Hello",
        target_lang="en",
        expanded_bbox=(5, 15, 110, 210),
        centroid=(60, 120),
        shape="oval",
        is_manual=True
    )
    d1 = b1.to_dict()
    b1_loaded = BubbleBlock.from_dict(d1)
    assert b1_loaded.id == "b1"
    assert b1_loaded.bbox == (10, 20, 100, 200)
    assert b1_loaded.expanded_bbox == (5, 15, 110, 210)
    assert b1_loaded.centroid == (60, 120)
    assert b1_loaded.shape == "oval"
    assert b1_loaded.is_manual is True
    assert b1_loaded.target_lang == "en"

    # Minimal fields with None
    b2 = BubbleBlock(
        id="b2",
        bbox=(0, 0, 50, 50),
        text_ja="テスト"
    )
    d2 = b2.to_dict()
    b2_loaded = BubbleBlock.from_dict(d2)
    assert b2_loaded.expanded_bbox is None
    assert b2_loaded.centroid is None
    assert b2_loaded.is_manual is False


def test_page_translation_round_trip():
    b = BubbleBlock("b1", (0, 0, 10, 10), "txt")
    page = PageTranslation("01.png", 500, 800, [b])
    d = page.to_dict()
    page_loaded = PageTranslation.from_dict(d)
    assert page_loaded.page_filename == "01.png"
    assert page_loaded.page_width == 500
    assert page_loaded.page_height == 800
    assert len(page_loaded.bubbles) == 1


def test_translation_job_toggle_image_and_progress():
    p1 = Path("/mock/01.png")
    p2 = Path("/mock/02.png")
    p3 = Path("/mock/03.png")

    job = TranslationJob(
        folder_path=Path("/mock"),
        folder_name="mock",
        image_paths=[p1, p2, p3],
        target_lang="en"
    )

    # Initial selection is all images
    assert job.selected_image_paths == [p1, p2, p3]

    # Toggle off p2
    job.toggle_image(p2)
    assert job.selected_image_paths == [p1, p3]

    # Toggle on p2 - must preserve original folder ordering [p1, p2, p3]
    job.toggle_image(p2)
    assert job.selected_image_paths == [p1, p2, p3]

    # Update progress with total == 0 does not divide by zero
    job.update_progress(0, 0)
    assert job.progress_pct == 0

    job.update_progress(1, 4)
    assert job.progress_pct == 25
