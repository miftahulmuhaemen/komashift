import io
import base64
from pathlib import Path
from PIL import Image
from src.services.image_compression import compress_image_to_webp, MIN_HEIGHT_FLOOR, MIN_QUALITY_FLOOR


def test_compress_image_to_webp_standard_manga(tmp_path: Path):
    # Standard high-res manga page: 1600 x 2400
    img_path = tmp_path / "sample_manga.png"
    img = Image.new("RGB", (1600, 2400), color=(255, 0, 0))
    img.save(img_path)

    # Compress at 50% scale, 80 quality
    data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
        img_path, scale_pct=50, quality=80
    )

    assert orig_w == 1600
    assert orig_h == 2400
    assert scaled_w == 800
    assert scaled_h == 1200
    # Strict Aspect Ratio Preservation
    assert abs((scaled_w / scaled_h) - (orig_w / orig_h)) < 0.001
    assert data_url.startswith("data:image/webp;base64,")

    # Verify decoded bytes are valid WebP
    b64_payload = data_url.replace("data:image/webp;base64,", "")
    decoded_bytes = base64.b64decode(b64_payload)
    with Image.open(io.BytesIO(decoded_bytes)) as decoded_img:
        assert decoded_img.format == "WEBP"
        assert decoded_img.size == (800, 1200)


def test_compress_image_resolution_floor_guardrail(tmp_path: Path):
    # Already low-res scan: 720 x 1080 (height < MIN_HEIGHT_FLOOR = 1200)
    img_path = tmp_path / "sample_lowres.png"
    img = Image.new("RGB", (720, 1080), color=(0, 0, 255))
    img.save(img_path)

    # 50% scale must be clamped so it is NOT downscaled below readable floor
    data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
        img_path, scale_pct=50, quality=50
    )

    assert orig_w == 720
    assert orig_h == 1080
    # Must NOT shrink to 360x540; preserved at original resolution
    assert scaled_w == 720
    assert scaled_h == 1080
    assert abs((scaled_w / scaled_h) - (orig_w / orig_h)) < 0.001


def test_compress_image_clamped_to_min_height(tmp_path: Path):
    # Intermediate size: 1200 x 1800. At 50%, target height would be 900 (< 1200).
    # Clamping must keep height at 1200 while preserving exact aspect ratio.
    img_path = tmp_path / "sample_inter.png"
    img = Image.new("RGB", (1200, 1800), color=(0, 255, 0))
    img.save(img_path)

    data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
        img_path, scale_pct=50, quality=60
    )

    assert orig_w == 1200
    assert orig_h == 1800
    assert scaled_h == 1200
    # Exact proportional width: 1200 * (1200 / 1800) = 800
    assert scaled_w == 800
    assert abs((scaled_w / scaled_h) - (orig_w / orig_h)) < 0.001


def test_compress_image_webp_passthrough(tmp_path: Path):
    # Lightweight webp that needs no resize should pass through directly
    img_path = tmp_path / "sample.webp"
    img = Image.new("RGB", (800, 1200), color=(100, 100, 100))
    img.save(img_path, format="WEBP", quality=80)

    data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
        img_path, scale_pct=100, quality=75
    )

    assert orig_w == 800
    assert orig_h == 1200
    assert scaled_w == 800
    assert scaled_h == 1200
    assert data_url.startswith("data:image/webp;base64,")
