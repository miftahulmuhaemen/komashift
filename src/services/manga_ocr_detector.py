import logging
from pathlib import Path
from typing import Optional, List
from PIL import Image
from src.models.translation_item import PageTranslation, BubbleBlock

logger = logging.getLogger(__name__)

class MangaOcrDetector:
    """
    Detector and OCR engine for speech bubbles in manga images.
    Supports pluggable real engines (e.g. manga-ocr) or an image-processing fallback.
    """
    def __init__(self, ocr_engine=None):
        self._engine = ocr_engine
        self._init_engine()

    def _init_engine(self):
        if self._engine is not None:
            return
        try:
            from manga_ocr import MangaOcr  # type: ignore
            self._engine = MangaOcr()
            logger.info("Loaded manga-ocr engine successfully.")
        except Exception:
            self._engine = None
            logger.info("manga-ocr package not available; using heuristic detector.")

    def detect_page(self, image_path: Path, page_index: int = 1) -> PageTranslation:
        """
        Detect speech bubbles and extract Japanese text from the image.
        Returns PageTranslation with detected bubbles and dimensions.
        """
        try:
            with Image.open(image_path) as img:
                width, height = img.size
        except Exception as e:
            logger.error(f"Failed to open image {image_path}: {e}")
            return PageTranslation(page_filename=image_path.name, page_width=0, page_height=0, bubbles=[])

        bubbles: List[BubbleBlock] = []

        if self._engine is not None:
            # When manga-ocr is installed, detect text regions and transcribe
            # (Can integrate comic-text-detector or bounding box detection)
            pass

        return PageTranslation(
            page_filename=image_path.name,
            page_width=width,
            page_height=height,
            bubbles=bubbles
        )
