import io
import base64
from pathlib import Path
from PIL import Image
from src.services.image_compression import compress_image_to_webp


def test_compress_image_to_webp(tmp_path: Path):
    # Create test RGB image 400x200
    img_path = tmp_path / "sample.png"
    img = Image.new("RGB", (400, 200), color=(255, 0, 0))
    img.save(img_path)

    # Compress at 50% scale, 80 quality
    data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
        img_path, scale_pct=50, quality=80
    )

    assert orig_w == 400
    assert orig_h == 200
    assert scaled_w == 200
    assert scaled_h == 100
    assert data_url.startswith("data:image/webp;base64,")

    # Verify decoded bytes are valid WebP
    b64_payload = data_url.replace("data:image/webp;base64,", "")
    decoded_bytes = base64.b64decode(b64_payload)
    with Image.open(io.BytesIO(decoded_bytes)) as decoded_img:
        assert decoded_img.format == "WEBP"
        assert decoded_img.size == (200, 100)


def test_compress_image_to_webp_100_percent(tmp_path: Path):
    img_path = tmp_path / "sample_full.png"
    img = Image.new("RGB", (300, 150), color=(0, 255, 0))
    img.save(img_path)

    data_url, (scaled_w, scaled_h), (orig_w, orig_h) = compress_image_to_webp(
        img_path, scale_pct=100, quality=75
    )

    assert orig_w == 300
    assert orig_h == 150
    assert scaled_w == 300
    assert scaled_h == 150
    assert data_url.startswith("data:image/webp;base64,")
