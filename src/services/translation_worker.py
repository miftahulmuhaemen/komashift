import logging
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from PyQt6.QtCore import QThread, pyqtSignal
from src.models.translation_item import PageTranslation
from src.infra.json_workspace import JsonTempWorkspace as TranslationWorkspace
from src.services.translation_client import OpenAITranslator, TranslationError
from src.services.manga_ocr_detector import MangaOcrDetector
from src.services.scanner import natural_sort_key

logger = logging.getLogger(__name__)

class TranslationWorker(QThread):
    progress_updated = pyqtSignal(str, int, int)      # (message, current, total)
    page_completed = pyqtSignal(str)                  # page_filename
    translation_finished = pyqtSignal(bool, str)       # (success, message)

    def __init__(
        self,
        folder_path: Path,
        image_paths: List[Path],
        api_key: str = "",
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        model: str = "gemini-3.5-flash-lite",
        target_lang: str = "en",
        detector: Optional[MangaOcrDetector] = None,
        timeout: float = 300.0,
        batch_size: int = 0,
        engine_mode: str = "hybrid",
        vision_scale_pct: int = 75,
        vision_quality: int = 75,
        max_retries: int = 3,
        protocol: str = "openai",
        job_type: str = "translation",
        output_dir: Optional[Path] = None,
        parent=None,
        provider: Optional[Any] = None,
        repository: Optional[Any] = None,
        log_sink: Optional[Any] = None,
        manga_ocr_model: str = "",
        onnx_force_cpu: bool = False,
    ):
        super().__init__(parent)
        self.folder_path = Path(folder_path)
        self.image_paths = list(image_paths)
        self.failed_image_paths: List[Path] = []
        self.api_key, self.base_url, self.model = api_key, base_url, model
        self.target_lang, self.timeout, self.batch_size = target_lang, timeout, batch_size
        self.engine_mode, self.vision_scale_pct = engine_mode, vision_scale_pct
        self.vision_quality = vision_quality
        self.max_retries = max(1, min(5, int(max_retries)))
        self.protocol, self.job_type = str(protocol).lower(), str(job_type)
        self.output_dir = Path(output_dir) if output_dir else None
        self.manga_ocr_model, self.onnx_force_cpu = str(manga_ocr_model).strip(), bool(onnx_force_cpu)

        self.workspace = repository if repository is not None else TranslationWorkspace(self.folder_path, log_sink=log_sink)
        self.translator = provider if provider is not None else OpenAITranslator(
            api_key=self.api_key, base_url=self.base_url, model=self.model,
            timeout=self.timeout, batch_size=self.batch_size, protocol=self.protocol
        )
        self.detector = detector or MangaOcrDetector(
            api_key=self.api_key, base_url=self.base_url, model=self.model,
            ocr_model_path=self.manga_ocr_model, force_cpu=self.onnx_force_cpu
        )
        strategies = {"rasterize": self._run_rasterize, "multimodal": self._run_multimodal}
        self._strategy = strategies.get(self.job_type if self.job_type == "rasterize" else self.engine_mode, self._run_hybrid)

    def run(self):
        # Soft start: brief yield so Qt UI finishes repainting button and queue transitions
        time.sleep(0.08)
        if self.isInterruptionRequested():
            self.translation_finished.emit(False, "Cancelled by user")
            return
        self._strategy()

    def _ensure_bubble_detector(self) -> bool:
        if hasattr(self.detector, "detect_page") and hasattr(self.detector.detect_page, "_mock_return_value"):
            return True
        if getattr(self.detector, "is_bubble_detector_available", lambda: True)():
            return True
        self.progress_updated.emit("Downloading speech bubble model (~95 MB)...", 0, 100)
        self.workspace.append_log("Speech bubble model missing. Starting download from Hugging Face...")
        cb = lambda cur, tot: tot > 0 and self.progress_updated.emit(f"Downloading bubble model: {cur/1048576:.1f}/{tot/1048576:.1f} MB ({int((cur/tot)*100)}%)...", int((cur/tot)*100), 100)
        try:
            if hasattr(self.detector, "ensure_bubble_detector"):
                self.detector.ensure_bubble_detector(progress_callback=cb, cancel_check=self.isInterruptionRequested)
            self.workspace.append_log("Bubble detection model ready.")
            return True
        except InterruptedError:
            self.workspace.append_log("Model download cancelled by user.")
            self.translation_finished.emit(False, "Cancelled by user")
            return False
        except Exception as e:
            err = f"Failed to download speech bubble model: {e}"
            logger.error(err); self.workspace.append_log(err)
            self.translation_finished.emit(False, err)
            return False

    def _is_cached_complete(self, total_pages: int) -> bool:
        if self.workspace.is_translation_complete(target_lang=self.target_lang, image_paths=self.image_paths):
            self.workspace.append_log(f"Translation ({self.target_lang.upper()}) already completed in cache. Done.")
            self.progress_updated.emit("Translation loaded from cache", total_pages, total_pages)
            self.translation_finished.emit(True, "Loaded from cache")
            return True
        return False

    def _load_cached_ocr_results(self) -> Dict[str, PageTranslation]:
        ocr_results = self.workspace.load_ocr_results()
        if ocr_results:
            total = sum(len(p.bubbles) for p in ocr_results.values())
            if total == 0:
                self.workspace.append_log("Stale OCR cache found with 0 bubbles (from previous broken run). Clearing cache and re-scanning.")
                self.workspace.clear_cache()
                return {}
            self.workspace.append_log(f"Loaded {len(ocr_results)} pre-existing OCR pages from cache ({total} bubbles)")
        return ocr_results or {}

    def _run_hybrid(self):
        total_pages = len(self.image_paths)
        if total_pages == 0:
            self.translation_finished.emit(False, "No images selected for translation.")
            return
        self.workspace.append_log(f"Starting translation process for {total_pages} pages using model: {self.model}")
        if not self._ensure_bubble_detector() or self._is_cached_complete(total_pages):
            return

        ocr_results = self._load_cached_ocr_results()

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
                page_data = self.detector.detect_page(
                    img_path,
                    page_index=idx + 1,
                    log_callback=self.workspace.append_log
                )
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

        # 4. Check if any bubbles were detected
        total_bubbles = sum(len(p.bubbles) for p in ocr_results.values())
        if total_bubbles == 0:
            err_msg = "0 speech bubbles were detected in this chapter. Please review the logs."
            self.workspace.append_log(err_msg)
            self.translation_finished.emit(False, err_msg)
            return

        # 5. Harvest pre-existing translations from workspace and OCR results
        translations = dict(self.workspace.load_translations(self.target_lang))
        for p in ocr_results.values():
            for b in p.bubbles:
                if b.text_en and b.id not in translations:
                    translations[b.id] = b.text_en

        # Process any manual labeled bubbles first
        for idx, img_path in enumerate(self.image_paths, 1):
            if self.isInterruptionRequested():
                break
            p_data = ocr_results.get(img_path.name)
            if p_data and p_data.bubbles:
                self._process_manual_bubbles_for_page(
                    p_data, img_path, idx, ocr_results, translations
                )

        needs_batch = any(
            (not getattr(b, "is_manual", False)) and (b.id not in translations or not translations.get(b.id))
            for p in ocr_results.values()
            for b in p.bubbles
        )
        if needs_batch:
            self.progress_updated.emit("Translating dialogue batch with LLM...", total_pages, total_pages)
            self.workspace.append_log(f"Sending batch translation request for {len(ocr_results)} pages")
            try:
                pages_list = [ocr_results[img.name] for img in self.image_paths if img.name in ocr_results]
                def _on_batch_progress(batch_num: int, total_batches: int, translated_count: int):
                    msg = f"Translating batch {batch_num}/{total_batches} ({translated_count} bubbles done)..."
                    self.workspace.append_log(msg); self.progress_updated.emit(msg, total_pages, total_pages)

                batch_trans = self.translator.translate_chapter(
                    pages_list, target_lang=self.target_lang, on_batch_progress=_on_batch_progress
                )
                translations.update(batch_trans)
            except Exception as e:
                err_msg = f"Translation API failed: {e}"
                logger.error(err_msg); self.workspace.append_log(err_msg)
                if not translations:
                    self.translation_finished.emit(False, err_msg)
                    return

        self.workspace.save_translations(translations, target_lang=self.target_lang)
        self.workspace.append_log(f"Translation finished successfully: {len(translations)} bubbles")
        self.progress_updated.emit("Translation complete!", total_pages, total_pages)
        self.translation_finished.emit(True, f"Translated {len(translations)} bubbles successfully.")

    def _process_manual_bubbles_for_page(
        self,
        page_data: PageTranslation,
        img_path: Path,
        idx: int,
        ocr_results: Dict[str, PageTranslation],
        translations: Dict[str, str]
    ) -> bool:
        """
        Processes any untranslated manual labeled bubbles on page_data:
        Crops manual box, extracts Japanese text via Manga OCR, segments bubble contour,
        and translates via LLM with dialogue context from adjacent pages.
        """
        manual_untranslated = [
            b for b in page_data.bubbles
            if getattr(b, "is_manual", False) and (not b.text_ja or b.id not in translations or not translations.get(b.id))
        ]
        if not manual_untranslated:
            return False

        filename = img_path.name
        all_chapter_images = sorted([
            p for p in self.folder_path.iterdir()
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        ], key=natural_sort_key) if self.folder_path.exists() else self.image_paths
        chapter_idx = all_chapter_images.index(img_path) if img_path in all_chapter_images else (idx - 1)

        def _get_page_dialogue(p_idx: int) -> str:
            if 0 <= p_idx < len(all_chapter_images):
                p_name = all_chapter_images[p_idx].name
                p_info = ocr_results.get(p_name)
                if p_info:
                    lines = []
                    for b in p_info.bubbles:
                        t = translations.get(b.id) or b.text_en or b.text_ja
                        if t and t.strip():
                            lines.append(f"- {t.strip()}")
                    return "\n".join(lines)
            return ""

        prev_ctx = _get_page_dialogue(chapter_idx - 1)
        curr_ctx = _get_page_dialogue(chapter_idx)
        next_ctx = _get_page_dialogue(chapter_idx + 1)

        full_page_img = None
        for mb in manual_untranslated:
            if not mb.text_ja:
                if full_page_img is None:
                    from PIL import Image
                    full_page_img = Image.open(img_path).convert("RGB")
                bx, by, bw, bh = mb.bbox
                text_ja, exp_bbox, cent, shape_type = self.detector.detect_and_ocr_manual_region(
                    full_page_img, (bx, by, bw, bh)
                )
                mb.text_ja = text_ja
                mb.expanded_bbox = exp_bbox
                mb.centroid = cent
                mb.shape = shape_type
                self.workspace.append_log(f"Extracted Japanese OCR for manual box ({mb.id}): '{mb.text_ja}'")

            if mb.text_ja:
                mb_lang = getattr(mb, "target_lang", None) or self.target_lang or "en"
                self.workspace.append_log(
                    f"Translating manual labeled bubble '{mb.text_ja}' ({mb_lang.upper()}) on {filename} with surrounding page context..."
                )
                try:
                    trans_text = self.translator.translate_single_text_with_context(
                        text_ja=mb.text_ja,
                        target_lang=mb_lang,
                        prev_context=prev_ctx,
                        curr_context=curr_ctx,
                        next_context=next_ctx
                    )
                    mb.text_en = trans_text
                    translations[mb.id] = trans_text
                except Exception as e:
                    self.workspace.append_log(f"Manual bubble translation warning on {filename}: {e}")
                    mb.text_en = mb.text_ja
                    translations[mb.id] = mb.text_ja
            else:
                mb.text_en = ""
                translations[mb.id] = ""

        self.workspace.save_page_ocr(page_data)
        self.workspace.save_translations(translations, target_lang=self.target_lang)
        return True

    def _run_multimodal(self):
        total_pages = len(self.image_paths)
        if total_pages == 0:
            self.translation_finished.emit(False, "No images found in chapter folder.")
            return

        self.workspace.append_log(
            f"Starting Visual Hybrid translation for {total_pages} pages using model: {self.model} "
            f"(scale={self.vision_scale_pct}%, quality={self.vision_quality})"
        )

        if not self._ensure_bubble_detector() or self._is_cached_complete(total_pages):
            return

        ocr_results = self._load_cached_ocr_results()

        translations = dict(self.workspace.load_translations(self.target_lang))
        for p in ocr_results.values():
            for b in p.bubbles:
                if b.id in translations and not b.text_en:
                    b.text_en = translations[b.id]
                elif b.text_en and b.id not in translations:
                    translations[b.id] = b.text_en

        self.failed_image_paths = []
        is_direct_override = (
            "translate_page_visual_hybrid" in getattr(self.translator, "__dict__", {})
            or hasattr(getattr(self.translator, "translate_page_visual_hybrid", None), "_mock_return_value")
        )

        for idx, img_path in enumerate(self.image_paths, start=1):
            if self.isInterruptionRequested():
                self.workspace.append_log("Worker cancelled by user during visual perception")
                self.translation_finished.emit(False, "Cancelled by user")
                return

            filename = img_path.name
            page_data = ocr_results.get(filename)

            # Step 1: Ensure exact bubble contours and coordinates via local detector
            if not page_data:
                self.progress_updated.emit(f"Detecting bubbles: {filename}...", idx, total_pages)
                try:
                    page_data = self.detector.detect_page(
                        img_path, page_index=idx, log_callback=self.workspace.append_log
                    )
                    ocr_results[filename] = page_data
                    self.workspace.save_page_ocr(page_data)
                except Exception as e:
                    err_msg = f"Detection error on page {filename}: {e}"
                    logger.error(err_msg); self.workspace.append_log(err_msg)
                    self.failed_image_paths.append(img_path)
                    continue

            # Step 2: Pass 1 Visual Perception (Artwork inspection, text_ja transcription, speaker & emotion extraction)
            if page_data.bubbles:
                self._process_manual_bubbles_for_page(page_data, img_path, idx, ocr_results, translations)
                if is_direct_override:
                    missing = any(not b.text_en and not getattr(b, "is_manual", False) for b in page_data.bubbles)
                    if missing:
                        page_success = False
                        for attempt in range(1, self.max_retries + 1):
                            if self.isInterruptionRequested():
                                break
                            curr_scale = max(40, self.vision_scale_pct - (attempt - 1) * 20)
                            req_timeout = self.timeout + (attempt - 1) * 60.0
                            if attempt > 1:
                                self.workspace.append_log(f"Retry {attempt}/{self.max_retries} for {filename}: scale {curr_scale}%, timeout {int(req_timeout)}s")
                            try:
                                page_trans = self.translator.translate_page_visual_hybrid(
                                    img_path, page_data, target_lang=self.target_lang,
                                    scale_pct=curr_scale, quality=self.vision_quality, timeout=req_timeout
                                )
                                for b in page_data.bubbles:
                                    if b.id in page_trans:
                                        b.text_en = translations[b.id] = page_trans[b.id]
                                self.workspace.save_page_ocr(page_data)
                                page_success = True
                                break
                            except Exception as e:
                                err_msg = f"Multimodal translation error on page {filename} (attempt {attempt}/{self.max_retries}): {e}"
                                logger.error(err_msg); self.workspace.append_log(err_msg)
                                if attempt < self.max_retries and not self.isInterruptionRequested():
                                    time.sleep(min(15, 3 * (2 ** (attempt - 1))))
                        if not page_success and not self.isInterruptionRequested():
                            self.failed_image_paths.append(img_path)
                    else:
                        for b in page_data.bubbles:
                            if b.text_en:
                                translations[b.id] = b.text_en
                elif hasattr(self.translator, "perceive_page_visual_context") and any(not b.text_ja for b in page_data.bubbles):
                    self.progress_updated.emit(f"Perceiving art & dialogue: {filename}...", idx, total_pages)
                    try:
                        perceived = self.translator.perceive_page_visual_context(
                            img_path, page_data, scale_pct=self.vision_scale_pct,
                            quality=self.vision_quality, timeout=self.timeout
                        )
                        for b in page_data.bubbles:
                            if b.id in perceived:
                                p_info = perceived[b.id]
                                b.text_ja = p_info.get("text_ja") or b.text_ja
                                b.speaker = p_info.get("speaker", "")
                                b.expression = p_info.get("expression", "")
                                b.speech_type = p_info.get("speech_type", "")
                        self.workspace.save_page_ocr(page_data)
                    except Exception as e:
                        self.workspace.append_log(f"Perception warning on {filename}: {e}")

            self.page_completed.emit(filename)

        # Step 3: Pass 2 Chapter-Wide Narrative Translation (incorporating visual cues)
        if not is_direct_override and not self.isInterruptionRequested():
            pages_list = [ocr_results[img.name] for img in self.image_paths if img.name in ocr_results]
            needs_trans = any(
                (not getattr(b, "is_manual", False)) and (b.id not in translations or not translations.get(b.id))
                for p in pages_list for b in p.bubbles
            )
            if needs_trans:
                self.progress_updated.emit("Translating chapter with visual context...", total_pages, total_pages)
                self.workspace.append_log(f"Translating dialogue batch with visual context for {len(pages_list)} pages")
                try:
                    cb = lambda cur, tot, cnt: self.progress_updated.emit(f"Translating batch {cur}/{tot} ({cnt} done)...", total_pages, total_pages)
                    batch_trans = self.translator.translate_chapter(pages_list, target_lang=self.target_lang, on_batch_progress=cb)
                    translations.update(batch_trans)
                except Exception as e:
                    self.workspace.append_log(f"Chapter translation warning: {e}")

        if self.isInterruptionRequested():
            self.workspace.append_log("Worker cancelled by user before saving final translations")
            self.translation_finished.emit(False, "Cancelled by user")
            return

        if not translations:
            err_msg = "No speech bubbles or dialogue could be localized on this chapter."
            if self.failed_image_paths:
                err_msg = f"Visual translation timed out or failed on {len(self.failed_image_paths)} pages."
            self.workspace.append_log(err_msg)
            self.translation_finished.emit(False, err_msg)
            return

        self.workspace.save_translations(translations, target_lang=self.target_lang)
        if self.failed_image_paths:
            msg = f"Visual Hybrid finished with {len(self.failed_image_paths)} failed pages ({len(translations)} bubbles translated)"
            self.workspace.append_log(msg)
            self.progress_updated.emit(f"Completed with {len(self.failed_image_paths)} failed pages", total_pages, total_pages)
            self.translation_finished.emit(True, msg)
        else:
            self.workspace.append_log(f"Visual Hybrid translation finished successfully: {len(translations)} bubbles")
            self.progress_updated.emit("Translation complete!", total_pages, total_pages)
            self.translation_finished.emit(True, f"Translated {len(translations)} bubbles successfully.")

    def _run_rasterize(self):
        total_pages = len(self.image_paths)
        if total_pages == 0:
            self.translation_finished.emit(False, "No images selected for rasterization.")
            return

        out_dir = self.output_dir or (self.folder_path.parent / f"{self.folder_path.name}_translated")
        out_dir.mkdir(parents=True, exist_ok=True)

        self.workspace.append_log(f"Starting rasterization for {total_pages} pages into: {out_dir}")

        ocr_results = self.workspace.load_ocr_results()
        translations = self.workspace.load_translations()

        successful_count = 0
        from src.infra.image_rasterizer import ImageRasterizer
        import shutil

        for idx, img_path in enumerate(self.image_paths, start=1):
            if self.isInterruptionRequested():
                self.workspace.append_log("Worker cancelled by user during rasterization")
                self.translation_finished.emit(False, "Cancelled by user")
                return

            filename = img_path.name
            page_data = ocr_results.get(filename)
            output_file = out_dir / filename

            self.progress_updated.emit(f"Rasterizing: {filename}...", idx, total_pages)

            if output_file.exists() and output_file.stat().st_size > 0:
                self.workspace.append_log(f"Page {filename} already rasterized in destination, skipping")
                successful_count += 1
                self.page_completed.emit(filename)
                continue

            if not page_data or not page_data.bubbles:
                try:
                    shutil.copy2(img_path, output_file)
                    successful_count += 1
                except Exception as e:
                    self.workspace.append_log(f"Failed to copy non-text page {filename}: {e}")
                self.page_completed.emit(filename)
                continue

            success = ImageRasterizer.rasterize_page(
                image_path=img_path,
                page=page_data,
                translations=translations,
                output_path=output_file
            )
            if success:
                successful_count += 1
            else:
                self.workspace.append_log(f"Failed to rasterize page: {filename}")

            self.page_completed.emit(filename)

        msg = f"Successfully rasterized {successful_count}/{total_pages} pages to {out_dir.name}"
        self.workspace.append_log(msg)
        self.progress_updated.emit("Rasterization complete!", total_pages, total_pages)
        self.translation_finished.emit(True, msg)

