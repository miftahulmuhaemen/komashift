from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Set
from src.models.translation_item import PageTranslation


@dataclass(frozen=True)
class ChapterStatus:
    """Read-only snapshot of chapter OCR and translation state."""
    ocr_complete: bool
    translated_filenames: Set[str]
    manual_filenames: Set[str]
    chapter_language: str
    total_cached_translations: int

    def is_translation_complete(self, image_paths: Optional[List[Path]] = None) -> bool:
        """Helper to determine whether all given images are fully translated."""
        if not image_paths:
            return self.total_cached_translations > 0
        for p in image_paths:
            if p.name in self.manual_filenames:
                return False
        return all(p.name in self.translated_filenames for p in image_paths)


class PageRepository(Protocol):
    """Port defining the persistence contract for manga pages and translations."""

    def load_pages(self) -> Dict[str, PageTranslation]:
        """Load all OCR page translations for this chapter."""
        ...

    def save_page(self, page: PageTranslation) -> None:
        """Persist OCR detection/bubble data for a single page."""
        ...

    def load_translations(self, target_lang: Optional[str] = None) -> Dict[str, str]:
        """Load translated text mappings {bubble_id: translated_text}."""
        ...

    def save_translations(self, translations: Dict[str, str], target_lang: str = "en") -> None:
        """Persist translated text mappings."""
        ...

    def status(self, target_lang: str = "en", image_paths: Optional[List[Path]] = None) -> ChapterStatus:
        """Query the current chapter status (OCR and translation completion)."""
        ...

    def clear_cache(self) -> None:
        """Purge OCR and translation caches for this chapter."""
        ...
