import uuid
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal

from src.models.translation_item import PageTranslation, BubbleBlock
from src.models.translation_job import TranslationJob, JobStatus, JobType
from src.services.translation_queue import TranslationQueueManager
from src.ports.page_repository import PageRepository
from src.infra.json_workspace import JsonTempWorkspace
from src.services.scanner import natural_sort_key


class TranslationViewModel(QObject):
    """ViewModel for translation overlay toggles, manual speech bubble labeling, and queue management."""

    overlay_toggled = pyqtSignal(bool)
    box_tool_toggled = pyqtSignal(bool)
    manual_box_created = pyqtSignal(str, object)  # (page_filename, BubbleBlock)

    def __init__(
        self,
        queue_manager: TranslationQueueManager,
        parent: Optional[QObject] = None
    ):
        super().__init__(parent)
        self.queue_manager = queue_manager
        self._overlay_enabled: bool = True
        self._box_tool_active: bool = False

    @property
    def is_overlay_enabled(self) -> bool:
        return self._overlay_enabled

    @property
    def is_box_tool_active(self) -> bool:
        return self._box_tool_active

    def toggle_overlay(self) -> bool:
        """Toggle overlay display state."""
        self._overlay_enabled = not self._overlay_enabled
        self.overlay_toggled.emit(self._overlay_enabled)
        return self._overlay_enabled

    def set_overlay_enabled(self, enabled: bool) -> None:
        if self._overlay_enabled != enabled:
            self._overlay_enabled = enabled
            self.overlay_toggled.emit(self._overlay_enabled)

    def set_box_tool_active(self, active: bool) -> bool:
        """Set box selection tool state."""
        if self._box_tool_active != active:
            self._box_tool_active = active
            self.box_tool_toggled.emit(self._box_tool_active)
        return self._box_tool_active

    def toggle_box_tool(self) -> bool:
        """Toggle box selection tool state."""
        return self.set_box_tool_active(not self._box_tool_active)

    def add_manual_bubble(
        self,
        folder_path: Path,
        image_path: Path,
        image_index: int,
        bbox: Tuple[int, int, int, int],
        target_lang: str = "en",
        image_size: Optional[Tuple[int, int]] = None,
        repository: Optional[PageRepository] = None
    ) -> Tuple[PageTranslation, Dict[str, str], BubbleBlock]:
        """
        Create a new manual bubble block, persist it into the page repository,
        and register the job in TranslationQueueManager.
        """
        repo = repository if repository is not None else JsonTempWorkspace(folder_path)
        pages = repo.load_pages()
        filename = image_path.name
        page = pages.get(filename)

        if not page:
            pw, ph = image_size if image_size else (1000, 1000)
            page = PageTranslation(filename, pw, ph, [])
            pages[filename] = page

        bx, by, bw, bh = bbox
        translations = repo.load_translations()
        existing_ids = {b.id for b in page.bubbles}
        while True:
            new_id = f"p{image_index + 1}_m_{uuid.uuid4().hex[:8]}"
            if new_id not in existing_ids and new_id not in translations:
                break

        bubble = BubbleBlock(
            id=new_id,
            bbox=(bx, by, bw, bh),
            text_ja="",
            text_en="",
            target_lang=target_lang,
            expanded_bbox=(bx, by, bw, bh),
            centroid=(bx + bw // 2, by + bh // 2),
            shape="rect",
            is_manual=True
        )
        page.bubbles.append(bubble)
        repo.save_page(page)

        translations.pop(new_id, None)

        # Update queue job
        existing_job = None
        for j in self.queue_manager.jobs:
            if j.folder_path == folder_path and j.job_type == JobType.TRANSLATION:
                existing_job = j
                break

        if existing_job:
            if image_path not in existing_job.image_paths:
                existing_job.image_paths.append(image_path)
            if existing_job.selected_image_paths is not None:
                if image_path not in existing_job.selected_image_paths:
                    existing_job.selected_image_paths.append(image_path)
            else:
                existing_job.selected_image_paths = [image_path]

            if existing_job.target_lang.lower() != target_lang.lower():
                existing_job.target_lang = "mix"

            if existing_job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
                existing_job.status = JobStatus.PENDING
                existing_job.status_message = "Pending manual label translation"
                existing_job.error_message = None
                existing_job.progress_pct = 0
            self.queue_manager.queue_updated.emit()
            self.queue_manager.notify_overall_progress()
        else:
            all_imgs = sorted([
                p for p in folder_path.iterdir()
                if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
            ], key=natural_sort_key)
            job = self.queue_manager.add_job(
                folder_path=folder_path,
                image_paths=all_imgs,
                target_lang=target_lang
            )
            job.selected_image_paths = [image_path]
            self.queue_manager.queue_updated.emit()

        self.manual_box_created.emit(filename, bubble)
        return page, translations, bubble
