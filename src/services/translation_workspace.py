import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from src.models.translation_item import PageTranslation

logger = logging.getLogger(__name__)

class TranslationWorkspace:
    def __init__(self, folder_path: Path):
        self.folder_path = Path(folder_path)
        self.temp_dir = self.folder_path / "temp"
        self._ensure_temp_dir()

    def _ensure_temp_dir(self):
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def get_temp_dir(self) -> Path:
        return self.temp_dir

    @property
    def ocr_file(self) -> Path:
        return self.temp_dir / "ocr_results.json"

    @property
    def translation_file(self) -> Path:
        return self.temp_dir / "translation_results.json"

    @property
    def log_file(self) -> Path:
        return self.temp_dir / "translation.log"

    def append_log(self, message: str):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}\n"
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.error(f"Failed to append to log: {e}")

    def save_page_ocr(self, page: PageTranslation):
        results = self.load_ocr_results()
        results[page.page_filename] = page

        data = {
            "version": 1,
            "pages": {fn: p.to_dict() for fn, p in results.items()}
        }
        self._atomic_write_json(self.ocr_file, data)
        self.append_log(f"Saved OCR results for page: {page.page_filename}")

    def load_ocr_results(self) -> Dict[str, PageTranslation]:
        if not self.ocr_file.exists():
            return {}
        try:
            with open(self.ocr_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            pages_data = data.get("pages", {})
            return {
                fn: PageTranslation.from_dict(p_data)
                for fn, p_data in pages_data.items()
            }
        except Exception as e:
            self.append_log(f"Error reading OCR file: {e}")
            return {}

    def is_ocr_complete(self, total_pages: int) -> bool:
        if total_pages <= 0:
            return False
        results = self.load_ocr_results()
        return len(results) >= total_pages

    def save_translations(self, translations: Dict[str, str]):
        data = {
            "version": 1,
            "translations": translations,
            "timestamp": datetime.now().isoformat()
        }
        self._atomic_write_json(self.translation_file, data)
        self.append_log(f"Saved {len(translations)} translations")

    def load_translations(self) -> Dict[str, str]:
        if not self.translation_file.exists():
            return {}
        try:
            with open(self.translation_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("translations", {})
        except Exception as e:
            self.append_log(f"Error reading translations: {e}")
            return {}

    def is_translation_complete(self) -> bool:
        return self.translation_file.exists() and len(self.load_translations()) > 0

    def _atomic_write_json(self, target_path: Path, data: dict):
        temp_file = target_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_file.replace(target_path)
