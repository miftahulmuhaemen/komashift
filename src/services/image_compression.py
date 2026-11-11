import io
import base64
from pathlib import Path
from typing import Tuple, Union
from PIL import Image


def compress_image_to_webp(
    image_path: Union[str, Path],
    scale_pct: int = 75,
    quality: int = 75
) -> Tuple[str, Tuple[int, int], Tuple[int, int]]:
    """
    Compresses an image to WebP with percentage-based downscaling.

    Args:
        image_path: Path to the source image file.
        scale_pct: Scale percentage (10 to 100). Default is 75.
        quality: WebP compression quality (1 to 100). Default is 75.

    Returns:
        Tuple containing:
            - data_url: Base64 data URL string (data:image/webp;base64,...)
            - (scaled_w, scaled_h): Processed dimensions sent to the model.
            - (orig_w, orig_h): Original dimensions of the source image.
    """
    scale_pct = max(10, min(100, int(scale_pct)))
    quality = max(1, min(100, int(quality)))

    with Image.open(image_path) as img:
        orig_w, orig_h = img.size

        if scale_pct < 100:
            scaled_w = max(1, int(orig_w * (scale_pct / 100.0)))
            scaled_h = max(1, int(orig_h * (scale_pct / 100.0)))
            img = img.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)
        else:
            scaled_w, scaled_h = orig_w, orig_h

        # WebP supports RGB and RGBA. Convert palette or CMYK modes to RGB.
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=quality)
        raw_bytes = buffer.getvalue()

    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    data_url = f"data:image/webp;base64,{b64_str}"

    return data_url, (scaled_w, scaled_h), (orig_w, orig_h)
