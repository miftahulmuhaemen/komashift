from pathlib import Path
from typing import Dict, List, Optional, Protocol, Union
from src.models.translation_item import BubbleBlock, PageTranslation


class TranslationError(Exception):
    """Exception raised when an external translation provider request fails."""
    pass


class TranslationProvider(Protocol):
    """Port defining the external translation provider contract."""

    def translate_batch(
        self,
        bubbles: List[BubbleBlock],
        target_lang: str = "en",
        page_index: Optional[int] = None,
        total_pages: Optional[int] = None
    ) -> Dict[str, str]:
        """Translate a batch of text bubble blocks."""
        ...

    def translate_single_text_with_context(
        self,
        text_ja: str,
        target_lang: str = "en",
        prev_context: Optional[str] = None,
        curr_context: Optional[str] = None,
        next_context: Optional[str] = None
    ) -> str:
        """Translate a single dialogue line using surrounding narrative context."""
        ...

    def translate_page_visual_hybrid(
        self,
        image_path: Union[str, Path],
        page: PageTranslation,
        target_lang: str = "en",
        scale_pct: int = 75,
        quality: int = 75,
        timeout: Optional[float] = None
    ) -> Dict[str, str]:
        """Translate page dialogue using vision-augmented multimodal context."""
        ...
