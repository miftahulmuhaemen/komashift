import os
import sys
import logging
from pathlib import Path
from typing import Dict, Union, Optional

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPixmap, QPainter
from src.models.translation_item import PageTranslation
from src.ports.comic_text_renderer import ComicTextRenderer
from src.infra.qt_comic_renderer import QtComicTextRenderer

logger = logging.getLogger(__name__)


class ImageRasterizer:
    """Infra adapter to permanently bake vector translation overlays into rasterized images."""

    def __init__(self, renderer: Optional[ComicTextRenderer] = None):
        self._renderer = renderer if renderer is not None else QtComicTextRenderer()

    @classmethod
    def rasterize_page(
        cls,
        image_path: Union[str, Path],
        page: PageTranslation,
        translations: Dict[str, str],
        output_path: Union[str, Path],
        renderer: Optional[ComicTextRenderer] = None,
    ) -> bool:
        """
        Renders the vector translation overlay onto the source image and saves it to disk.

        Args:
            image_path: Path to the original raw image file.
            page: PageTranslation containing detected speech bubble contours and bboxes.
            translations: Mapping of bubble IDs to their translated text strings.
            output_path: Destination path for the baked image.
            renderer: Optional custom ComicTextRenderer adapter.

        Returns:
            True if rasterization and save succeeded, False otherwise.
        """
        app = QApplication.instance()
        if not app:
            app = QApplication([])

        image_path = Path(image_path)
        output_path = Path(output_path)

        if not image_path.exists():
            logger.error("Source image does not exist: %s", image_path)
            return False

        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            logger.error("Failed to load source image into QPixmap: %s", image_path)
            return False

        orig_w = pixmap.width()
        orig_h = pixmap.height()

        canvas = QPixmap(pixmap)
        painter = QPainter(canvas)
        active_renderer = renderer if renderer is not None else QtComicTextRenderer()
        try:
            active_renderer.render(
                painter=painter,
                page=page,
                translations=translations,
                scale_factor=1.0,
                offset=(0, 0),
                orig_size=(orig_w, orig_h),
                scaled_size=(orig_w, orig_h),
            )
        finally:
            painter.end()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        ext = output_path.suffix.lstrip(".").upper()
        if not ext:
            ext = "PNG"

        success = canvas.save(str(output_path), ext)
        if success:
            logger.info("Successfully rasterized: %s -> %s", image_path.name, output_path)
        else:
            logger.error("Failed to save rasterized image to %s", output_path)

        return success
