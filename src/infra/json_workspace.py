import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from src.models.translation_item import PageTranslation
from src.ports.page_repository import ChapterStatus
from src.ports.log_sink import LogSink
from src.infra.file_log_sink import FileLogSink

logger = logging.getLogger(__name__)


class JsonTempWorkspace:
    """Concrete filesystem adapter implementing PageRepository using <folder>/temp JSON files."""

    def __init__(self, folder_path: Path, log_sink: Optional[LogSink] = None):
        self.folder_path = Path(folder_path)
        self.temp_dir = self.folder_path / "temp"
        self._ensure_temp_dir()
        self.log_sink = log_sink if log_sink is not None else FileLogSink(self.temp_dir / "translation.log")

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
        return self.log_sink.log_file

    def append_log(self, message: str):
        self.log_sink.append(message)

    # --- PageRepository port implementation ---

    def load_pages(self) -> Dict[str, PageTranslation]:
        return self.load_ocr_results()

    def save_page(self, page: PageTranslation):
        self.save_page_ocr(page)

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

    def save_page_ocr(self, page: PageTranslation):
        results = self.load_ocr_results()
        results[page.page_filename] = page

        data = {
            "version": 1,
            "pages": {fn: p.to_dict() for fn, p in results.items()}
        }
        self._atomic_write_json(self.ocr_file, data)
        self.append_log(f"Saved OCR results for page: {page.page_filename}")

    def is_ocr_complete(self, total_pages: int) -> bool:
        if total_pages <= 0:
            return False
        results = self.load_ocr_results()
        return len(results) >= total_pages

    def get_translation_file(self, target_lang: str = "en") -> Path:
        lang = (target_lang or "en").lower().strip()
        if lang in ("mix", "mixed", "mix-lang", "all"):
            return self.translation_file
        if lang in ("en", "english"):
            specific = self.temp_dir / "translation_results_en.json"
            if specific.exists():
                return specific
            return self.translation_file
        return self.temp_dir / f"translation_results_{lang}.json"

    def save_translations(self, translations: Dict[str, str], target_lang: str = "en"):
        main_existing = self.load_translations()
        main_merged = {**main_existing, **translations}
        main_data = {
            "version": 1,
            "translations": main_merged,
            "timestamp": datetime.now().isoformat()
        }
        self._atomic_write_json(self.translation_file, main_data)

        target_file = self.get_translation_file(target_lang)
        if target_file != self.translation_file:
            existing_lang = {}
            if target_file.exists():
                try:
                    with open(target_file, "r", encoding="utf-8") as f:
                        existing_lang = json.load(f).get("translations", {})
                except Exception:
                    existing_lang = {}
            merged_lang = {**existing_lang, **translations}
            lang_data = {
                "version": 1,
                "target_lang": target_lang,
                "translations": merged_lang,
                "timestamp": datetime.now().isoformat()
            }
            self._atomic_write_json(target_file, lang_data)

        self.append_log(f"Saved {len(translations)} translations to {self.translation_file.name}")

    def load_translations(self, target_lang: Optional[str] = None) -> Dict[str, str]:
        all_trans: Dict[str, str] = {}
        if self.translation_file.exists():
            try:
                with open(self.translation_file, "r", encoding="utf-8") as f:
                    all_trans.update(json.load(f).get("translations", {}))
            except Exception as e:
                self.append_log(f"Error reading translations from {self.translation_file.name}: {e}")

        for t_file in self.temp_dir.glob("translation_results_*.json"):
            try:
                with open(t_file, "r", encoding="utf-8") as f:
                    for k, v in json.load(f).get("translations", {}).items():
                        if k not in all_trans:
                            all_trans[k] = v
            except Exception:
                pass

        if target_lang and target_lang.lower().strip() not in ("all", "mix", "mixed", "mix-lang"):
            t_file = self.get_translation_file(target_lang)
            if t_file.exists() and t_file != self.translation_file:
                try:
                    with open(t_file, "r", encoding="utf-8") as f:
                        return json.load(f).get("translations", {})
                except Exception:
                    pass

        return all_trans

    def get_page_language(self, filename: str) -> str:
        ocr_results = self.load_ocr_results()
        page = ocr_results.get(filename)
        if not page or not page.bubbles:
            return "EN"
        langs = set()
        for b in page.bubbles:
            b_lang = getattr(b, "target_lang", "").lower().strip()
            if b_lang in ("id", "indonesian"):
                langs.add("ID")
            elif b_lang in ("en", "english"):
                langs.add("EN")
        if len(langs) > 1:
            return "Mix-Lang"
        if len(langs) == 1:
            return next(iter(langs))
        return "EN"

    def get_chapter_language(self) -> str:
        ocr_results = self.load_ocr_results()
        if not ocr_results:
            return "EN"
        langs = set()
        for page in ocr_results.values():
            for b in page.bubbles:
                b_lang = getattr(b, "target_lang", "").lower().strip()
                if b_lang in ("id", "indonesian"):
                    langs.add("ID")
                elif b_lang in ("en", "english"):
                    langs.add("EN")
        if len(langs) > 1:
            return "Mix-Lang"
        if len(langs) == 1:
            return next(iter(langs))
        return "EN"

    def get_translated_page_filenames(self, target_lang: str = "en") -> Set[str]:
        ocr_results = self.load_ocr_results()
        if not ocr_results:
            return set()
        translations = self.load_translations(target_lang)
        translated_pages: Set[str] = set()
        for fn, page in ocr_results.items():
            if not page.bubbles:
                translated_pages.add(fn)
            elif all(
                (not getattr(b, "is_manual", False) or bool(b.text_ja))
                and b.id in translations and bool(translations.get(b.id))
                for b in page.bubbles
            ):
                translated_pages.add(fn)
        return translated_pages

    def get_manual_labeled_page_filenames(self, target_lang: str = "en") -> Set[str]:
        ocr_results = self.load_ocr_results()
        if not ocr_results:
            return set()
        translations = self.load_translations(target_lang)
        manual_pages: Set[str] = set()
        for fn, page in ocr_results.items():
            if any(getattr(b, "is_manual", False) and (not b.text_ja or b.id not in translations or not translations.get(b.id)) for b in page.bubbles):
                manual_pages.add(fn)
        return manual_pages

    def is_page_translated(self, filename: str, target_lang: str = "en") -> bool:
        return filename in self.get_translated_page_filenames(target_lang)

    def is_translation_complete(self, target_lang: str = "en", image_paths: Optional[List[Path]] = None) -> bool:
        target_file = self.get_translation_file(target_lang)
        if not target_file.exists():
            return False
        if image_paths is None:
            return len(self.load_translations(target_lang)) > 0
        if not image_paths:
            return False
        manual_untranslated = self.get_manual_labeled_page_filenames(target_lang)
        for p in image_paths:
            if p.name in manual_untranslated:
                return False
        translated = self.get_translated_page_filenames(target_lang)
        return all(p.name in translated for p in image_paths)

    def status(self, target_lang: str = "en", image_paths: Optional[List[Path]] = None) -> ChapterStatus:
        ocr_res = self.load_ocr_results()
        total_pages = len(image_paths) if image_paths else len(ocr_res)
        ocr_complete = (len(ocr_res) >= total_pages) if total_pages > 0 else False
        translated_fns = self.get_translated_page_filenames(target_lang)
        manual_fns = self.get_manual_labeled_page_filenames(target_lang)
        ch_lang = self.get_chapter_language()
        cached_trans = self.load_translations(target_lang)

        return ChapterStatus(
            ocr_complete=ocr_complete,
            translated_filenames=translated_fns,
            manual_filenames=manual_fns,
            chapter_language=ch_lang,
            total_cached_translations=len(cached_trans)
        )

    def clear_cache(self):
        if self.ocr_file.exists():
            try:
                self.ocr_file.unlink()
            except Exception:
                pass
        for t_file in self.temp_dir.glob("translation_results*.json"):
            try:
                t_file.unlink()
            except Exception:
                pass
        self.append_log("Cleared OCR and translation cache.")

    def _atomic_write_json(self, target_path: Path, data: dict):
        temp_file = target_path.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_file.replace(target_path)


# Backward-compatibility alias
TranslationWorkspace = JsonTempWorkspace
