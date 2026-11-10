from pathlib import Path
from PIL import Image
from src.models.translation_item import PageTranslation, BubbleBlock
from src.infra.image_rasterizer import ImageRasterizer


def test_image_rasterizer_bakes_image_with_pixel_oracle(tmp_path: Path):
    # 1. Create a distinct black source image (0, 0, 0)
    src_img = tmp_path / "page_01.png"
    img = Image.new("RGB", (300, 400), color=(0, 0, 0))
    img.save(src_img)

    # 2. Page metadata with one oval bubble at (50, 50, 100, 80)
    bubble = BubbleBlock(
        id="p1_b1",
        bbox=(50, 50, 100, 80),
        text_ja="こんにちは",
        text_en="Hello World",
        shape="oval"
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

    # 4. Verify output image dimensions
    baked = Image.open(out_img).convert("RGB")
    assert baked.size == (300, 400)

    # Pixel Oracle:
    # A pixel inside the bubble center (100, 90) must have been modified by the white bubble background
    inside_pixel = baked.getpixel((100, 90))
    assert inside_pixel != (0, 0, 0), f"Expected inside pixel to be drawn, got {inside_pixel}"
    # The bubble background is nearly white (255, 255, 255, 245) over black
    assert inside_pixel[0] > 200 and inside_pixel[1] > 200 and inside_pixel[2] > 200

    # A pixel outside the bubble (10, 10) must remain strictly identical to source black (0, 0, 0)
    outside_pixel = baked.getpixel((10, 10))
    assert outside_pixel == (0, 0, 0), f"Expected outside pixel to be unchanged black, got {outside_pixel}"


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
