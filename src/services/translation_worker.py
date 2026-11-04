import logging
from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import QThread, pyqtSignal
from src.services.translation_workspace import TranslationWorkspace
from src.services.translation_client import OpenAITranslator, TranslationError
from src.services.manga_ocr_detector import MangaOcrDetector

logger = logging.getLogger(__name__)

class TranslationWorker(QThread):
    progress_updated = pyqtSignal(str, int, int)      # (message, current, total)
    page_completed = pyqtSignal(str)                  # page_filename
    translation_finished = pyqtSignal(bool, str)       # (success, message)

    def __init__(
        self,
        folder_path: Path,
        image_paths: List[Path],
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        detector: Optional[MangaOcrDetector] = None,
        parent=None
    ):
        super().__init__(parent)
        self.folder_path = Path(folder_path)
        self.image_paths = list(image_paths)
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.workspace = TranslationWorkspace(self.folder_path)
        self.translator = OpenAITranslator(api_key=self.api_key, base_url=self.base_url, model=self.model)
        self.detector = detector or MangaOcrDetector()

    def run(self):
        total_pages = len(self.image_paths)
        if total_pages == 0:
            self.translation_finished.emit(False, "No images found in chapter folder.")
            return

        self.workspace.append_log(f"Starting translation process for {total_pages} pages")

        # 1. Check if translation is already completed
        if self.workspace.is_translation_complete():
            self.workspace.append_log("Translation already completed in cache. Done.")
            self.progress_updated.emit("Translation loaded from cache", total_pages, total_pages)
            self.translation_finished.emit(True, "Loaded from cache")
            return

        # 2. Check existing OCR progress to resume
        ocr_results = self.workspace.load_ocr_results()
        self.workspace.append_log(f"Loaded {len(ocr_results)} pre-existing OCR pages from cache")

        # 3. Perform OCR for any remaining pages
        for idx, img_path in enumerate(self.image_paths):
            if self.isInterruptionRequested():
                self.workspace.append_log("Worker cancelled by user during OCR")
                self.translation_finished.emit(False, "Cancelled by user")
                return

            filename = img_path.name
            if filename in ocr_results:
                self.progress_updated.emit(f"Cached OCR: {filename}", idx + 1, total_pages)
                continue

            self.progress_updated.emit(f"Scanning OCR: {filename}...", idx + 1, total_pages)
            try:
                page_data = self.detector.detect_page(img_path, page_index=idx + 1)
                self.workspace.save_page_ocr(page_data)
                ocr_results[filename] = page_data
                self.page_completed.emit(filename)
            except Exception as e:
                err_msg = f"OCR error on page {filename}: {e}"
                logger.error(err_msg)
                self.workspace.append_log(err_msg)
                # Continue with other pages or fail gracefully

        if self.isInterruptionRequested():
            self.workspace.append_log("Worker cancelled by user before translation")
            self.translation_finished.emit(False, "Cancelled by user")
            return

        # 4. Batch LLM Translation (Single Roundtrip)
        self.progress_updated.emit("Translating chapter dialogue with LLM...", total_pages, total_pages)
        self.workspace.append_log(f"Sending batch translation request for {len(ocr_results)} pages")

        try:
            pages_list = [ocr_results[img.name] for img in self.image_paths if img.name in ocr_results]
            translations = self.translator.translate_chapter(pages_list)
            self.workspace.save_translations(translations)
            self.workspace.append_log(f"Translation finished successfully: {len(translations)} bubbles")
            self.progress_updated.emit("Translation complete!", total_pages, total_pages)
            self.translation_finished.emit(True, f"Translated {len(translations)} bubbles successfully.")
        except TranslationError as e:
            err_msg = f"Translation API failed: {e}"
            logger.error(err_msg)
            self.workspace.append_log(err_msg)
            self.translation_finished.emit(False, err_msg)
        except Exception as e:
            err_msg = f"Unexpected translation error: {e}"
            logger.error(err_msg)
            self.workspace.append_log(err_msg)
            self.translation_finished.emit(False, err_msg)
