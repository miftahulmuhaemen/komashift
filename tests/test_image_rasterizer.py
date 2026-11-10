from pathlib import Path
from PIL import Image
from src.models.translation_item import PageTranslation, BubbleBlock
from src.services.image_rasterizer import ImageRasterizer


def test_image_rasterizer_bakes_image(tmp_path: Path):
    # 1. Create a raw white image
    src_img = tmp_path / "page_01.png"
    img = Image.new("RGB", (300, 400), color="white")
    img.save(src_img)

    # 2. Page metadata with one bubble
    bubble = BubbleBlock(
        id="p1_b1",
        bbox=(50, 50, 100, 80),
        text_ja="こんにちは",
        text_en="Hello World"
    )
    page = PageTranslation("page_01.png", 300, 400, [bubble])
    translations = {"p1_b1": "Hello World"}

    out_img = tmp_path / "page_01_baked.png"

    # 3. Rasterize
    success = ImageRasterizer.rasterize_page(
        image_path=src_img,
        page=page,
        translations=translations,
        output_path=out_img
    )

    assert success is True
    assert out_img.exists()
    assert out_img.stat().st_size > 0

    # Verify output can be read as a valid image with matching dimensions
    baked = Image.open(out_img)
    assert baked.size == (300, 400)


def test_image_rasterizer_missing_file(tmp_path: Path):
    missing_src = tmp_path / "non_existent.png"
    out_img = tmp_path / "out.png"
    page = PageTranslation("non_existent.png", 100, 100, [])

    success = ImageRasterizer.rasterize_page(
        image_path=missing_src,
        page=page,
        translations={},
        output_path=out_img
    )
    assert success is False
    assert not out_img.exists()
