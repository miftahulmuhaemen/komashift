from typing import Protocol, Any, Dict, Tuple, Optional
from src.models.translation_item import PageTranslation


class ComicTextRenderer(Protocol):
    """Port for rendering comic bubble translations onto a canvas or painter."""

    def render(
        self,
        painter: Any,
        page: PageTranslation,
        translations: Dict[str, str],
        scale_factor: float = 1.0,
        offset: Tuple[int, int] = (0, 0),
        orig_size: Optional[Tuple[int, int]] = None,
        scaled_size: Optional[Tuple[int, int]] = None,
    ) -> None:
        """Render speech bubbles onto a painter or canvas.

        Args:
            painter: The drawing context (e.g. QPainter).
            page: PageTranslation containing speech bubbles and geometry.
            translations: Mapping from bubble ID to translated text.
            scale_factor: Display scaling factor.
            offset: (x, y) offset for coordinates.
            orig_size: Optional (width, height) of original image.
            scaled_size: Optional (width, height) of destination canvas.
        """
        ...
