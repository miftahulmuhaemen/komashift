import io
import base64
from pathlib import Path
from typing import Tuple, Union
from PIL import Image

MIN_HEIGHT_FLOOR = 1200
MIN_QUALITY_FLOOR = 55


def compress_image_to_webp(
    image_path: Union[str, Path],
    scale_pct: int = 75,
    quality: int = 75,
    min_height: int = MIN_HEIGHT_FLOOR,
    min_quality: int = MIN_QUALITY_FLOOR
) -> Tuple[str, Tuple[int, int], Tuple[int, int]]:
    """
    Compresses an image to WebP with uniform aspect-ratio preserving downscaling
    and legibility guardrails (enforcing minimum height and quality floors).

    Args:
        image_path: Path to the source image file.
        scale_pct: Requested scale percentage (10 to 100). Default is 75.
        quality: Requested WebP compression quality (1 to 100). Default is 75.
        min_height: Minimum pixel height floor. Resolution never drops below this.
        min_quality: Minimum WebP compression quality floor.

    Returns:
        Tuple containing:
            - data_url: Base64 data URL string (data:image/webp;base64,...)
            - (scaled_w, scaled_h): Processed dimensions sent to the model.
            - (orig_w, orig_h): Original dimensions of the source image.
    """
    scale_pct = max(10, min(100, int(scale_pct)))
    effective_quality = max(min_quality, min(100, int(quality)))
    img_file = Path(image_path)

    with Image.open(img_file) as img:
        orig_w, orig_h = img.size

        # Aspect-Ratio Preserving Scalar Calculation:
        # Enforce resolution floor so low-res scans (< min_height) are never downscaled.
        if scale_pct < 100 and orig_h > min_height:
            target_h = int(orig_h * (scale_pct / 100.0))
            effective_h = max(min_height, target_h)
            factor = effective_h / float(orig_h)
        else:
            factor = 1.0

        scaled_w = max(1, int(round(orig_w * factor)))
        scaled_h = max(1, int(round(orig_h * factor)))

        # Passthrough Optimization: If source is already lightweight WebP and no resize needed
        if factor == 1.0 and img_file.suffix.lower() == ".webp" and img_file.stat().st_size <= 600 * 1024:
            raw_bytes = img_file.read_bytes()
            b64_str = base64.b64encode(raw_bytes).decode("utf-8")
            return f"data:image/webp;base64,{b64_str}", (orig_w, orig_h), (orig_w, orig_h)

        if factor < 1.0:
            img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=effective_quality)
        raw_bytes = buffer.getvalue()

    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    data_url = f"data:image/webp;base64,{b64_str}"

    return data_url, (scaled_w, scaled_h), (orig_w, orig_h)
