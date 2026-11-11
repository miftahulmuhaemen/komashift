import logging
from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread
from src.models.translation_job import TranslationJob, JobStatus, JobType
from src.services.translation_worker import TranslationWorker
from src.services.manga_ocr_detector import MangaOcrDetector

logger = logging.getLogger(__name__)


class TranslationQueueManager(QObject):
    queue_updated = pyqtSignal()
    queue_state_changed = pyqtSignal(bool)           # is_running
    job_started = pyqtSignal(str)                   # job_id
    job_progress = pyqtSignal(str, str, int, int)   # job_id, message, current, total
    job_finished = pyqtSignal(str, bool, str)        # job_id, success, message
    overall_progress = pyqtSignal(int, int)          # completed_count, total_count

    def __init__(self, settings_getter=None, detector: Optional[MangaOcrDetector] = None, parent=None):
        super().__init__(parent)
        self.settings_getter = settings_getter
        self.detector = detector
        self.jobs: List[TranslationJob] = []
        self._is_running = False
        self._current_worker: Optional[TranslationWorker] = None
        self._current_job: Optional[TranslationJob] = None
        self._is_model_downloading = False
        self._model_download_message = ""

    @property
    def is_model_downloading(self) -> bool:
        return self._is_model_downloading

    def set_model_downloading(self, downloading: bool, message: str = ""):
        self._is_model_downloading = bool(downloading)
        self._model_download_message = message or ("Waiting for model download..." if downloading else "")
        if self._is_model_downloading:
            for j in self.jobs:
                if j.status == JobStatus.PENDING:
                    j.status_message = self._model_download_message
            self.queue_updated.emit()
        else:
            for j in self.jobs:
                if j.status == JobStatus.PENDING:
                    j.status_message = "Pending"
            self.queue_updated.emit()
            if self._is_running and self._current_worker is None:
                QTimer.singleShot(40, self._process_next)

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def pending_count(self) -> int:
        return sum(1 for j in self.jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING))

    @property
    def active_job(self) -> Optional[TranslationJob]:
        return self._current_job

    def get_job(self, job_id: str) -> Optional[TranslationJob]:
        for j in self.jobs:
            if j.id == job_id:
                return j
        return None

    def add_job(
        self,
        folder_path: Path,
        image_paths: List[Path],
        target_lang: str = "en",
        job_type: JobType = JobType.TRANSLATION,
        output_dir: Optional[Path] = None
    ) -> TranslationJob:
        folder_path = Path(folder_path)
        # Check if job already exists in pending or running state
        for j in self.jobs:
            if j.folder_path == folder_path and j.job_type == job_type and j.status in (JobStatus.PENDING, JobStatus.RUNNING):
                j.target_lang = target_lang
                self.queue_updated.emit()
                return j

        job = TranslationJob(
            folder_path=folder_path,
            folder_name=folder_path.name,
            image_paths=list(image_paths),
            target_lang=target_lang,
            job_type=job_type,
            output_dir=output_dir,
            status=JobStatus.PENDING
        )
        self.jobs.append(job)
        self.queue_updated.emit()
        self._emit_overall_progress()

        # If queue is already running and idle, process next
        if self._is_running and self._current_worker is None:
            self._process_next()

        return job

    def add_rasterize_job(
        self,
        folder_path: Path,
        image_paths: List[Path],
        target_lang: str = "en",
        output_dir: Optional[Path] = None
    ) -> TranslationJob:
        return self.add_job(
            folder_path=folder_path,
            image_paths=image_paths,
            target_lang=target_lang,
            job_type=JobType.RASTERIZE,
            output_dir=output_dir
        )

    def remove_job(self, job_id: str):
        job = self.get_job(job_id)
        if not job:
            return

        if job == self._current_job and self._current_worker:
            self._current_worker.requestInterruption()
            self._current_worker.wait(1000)
            self._current_worker = None
            self._current_job = None

        self.jobs = [j for j in self.jobs if j.id != job_id]
        self.queue_updated.emit()
        self._emit_overall_progress()

        if self._is_running and self._current_worker is None:
            self._process_next()

    def move_job(self, from_idx: int, to_idx: int):
        if 0 <= from_idx < len(self.jobs) and 0 <= to_idx < len(self.jobs):
            job = self.jobs.pop(from_idx)
            self.jobs.insert(to_idx, job)
            self.queue_updated.emit()

    def clear_completed(self):
        self.jobs = [j for j in self.jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING)]
        self.queue_updated.emit()
        self._emit_overall_progress()

    def start_queue(self):
        if self._is_running:
            return
        if not any(j.status == JobStatus.PENDING for j in self.jobs):
            # If all are failed/completed, restart failed or return
            has_failed = False
            for j in self.jobs:
                if j.status == JobStatus.FAILED:
                    j.status = JobStatus.PENDING
                    j.status_message = "Pending retry"
                    has_failed = True
            if not has_failed:
                return

        self._is_running = True
        self.queue_state_changed.emit(True)
        # Soft start: yield back to Qt event loop so UI repaints immediately without stutter
        QTimer.singleShot(40, self._process_next)

    def pause_queue(self):
        self._is_running = False
        self.queue_state_changed.emit(False)
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.requestInterruption()

    def stop_queue(self):
        """Alias for pause_queue for semantic clarity."""
        self.pause_queue()

    def _process_next(self):
        if not self._is_running:
            return

        next_job: Optional[TranslationJob] = None
        for j in self.jobs:
            if j.status == JobStatus.PENDING:
                next_job = j
                break

        if not next_job:
            self._is_running = False
            self._current_job = None
            self._current_worker = None
            self.queue_state_changed.emit(False)
            self._emit_overall_progress()
            return

        if self._is_model_downloading:
            next_job.status_message = self._model_download_message or "Waiting for model download..."
            self.queue_updated.emit()
            return

        # Check if there are selected pages
        selected_pages = next_job.selected_image_paths if next_job.selected_image_paths else next_job.image_paths
        if not selected_pages:
            next_job.status = JobStatus.FAILED
            next_job.status_message = "No pages selected"
            next_job.error_message = "No images were selected for this job."
            self.queue_updated.emit()
            self._emit_overall_progress()
            self._process_next()
            return

        self._current_job = next_job
        next_job.status = JobStatus.RUNNING
        next_job.status_message = "Starting..."
        self.job_started.emit(next_job.id)
        self.queue_updated.emit()

        api_key, base_url, model, timeout, batch_size, engine_mode, vision_scale_pct, vision_quality, max_retries, protocol, manga_ocr_model, onnx_force_cpu = self._get_api_credentials()
        self._current_worker = TranslationWorker(
            folder_path=next_job.folder_path,
            image_paths=selected_pages,
            api_key=api_key,
            base_url=base_url,
            model=model,
            target_lang=next_job.target_lang,
            detector=self.detector,
            timeout=timeout,
            batch_size=batch_size,
            engine_mode=engine_mode,
            vision_scale_pct=vision_scale_pct,
            vision_quality=vision_quality,
            max_retries=max_retries,
            protocol=protocol,
            manga_ocr_model=manga_ocr_model,
            onnx_force_cpu=onnx_force_cpu,
            job_type=next_job.job_type.value if hasattr(next_job.job_type, "value") else str(next_job.job_type),
            output_dir=next_job.output_dir
        )
        self._current_worker.progress_updated.connect(self._on_worker_progress)
        self._current_worker.translation_finished.connect(self._on_worker_finished)
        self._current_worker.start(QThread.Priority.NormalPriority)

    def _get_api_credentials(self):
        if self.settings_getter:
            res = self.settings_getter()
            if len(res) >= 12:
                return (
                    res[0], res[1], res[2], res[3], res[4],
                    res[5], res[6], res[7], res[8], res[9],
                    res[10], res[11]
                )
            if len(res) >= 10:
                return (
                    res[0], res[1], res[2], res[3], res[4],
                    res[5], res[6], res[7], res[8], res[9],
                    "", False
                )
            if len(res) >= 8:
                return (
                    res[0], res[1], res[2], res[3], res[4],
                    res[5], res[6], res[7], 3, "openai",
                    "", False
                )
            if len(res) >= 5:
                return (
                    res[0], res[1], res[2], res[3], res[4],
                    "hybrid", 75, 75, 3, "openai",
                    "", False
                )
            return (
                res[0], res[1], res[2], 300.0, 40,
                "hybrid", 75, 75, 3, "openai",
                "", False
            )
        return (
            "", "https://generativelanguage.googleapis.com/v1beta/openai/",
            "gemini-2.5-flash", 300.0, 40, "hybrid", 75, 75, 3, "openai",
            "", False
        )

    def _on_worker_progress(self, message: str, current: int, total: int):
        if self._current_job:
            self._current_job.update_progress(message, current, total)
            self.job_progress.emit(self._current_job.id, message, current, total)

    def _on_worker_finished(self, success: bool, message: str):
        if self._current_job:
            job_id = self._current_job.id
            failed_images = list(getattr(self._current_worker, "failed_image_paths", []))
            was_cancelled = (message == "Cancelled by user")

            if not was_cancelled and failed_images and self._current_job.retry_count < self._current_job.max_retries:
                if success:
                    self._current_job.status = JobStatus.COMPLETED
                    self._current_job.progress_pct = 100
                    self._current_job.status_message = f"Done ({len(failed_images)} failed re-queued)"
                    self._current_job.error_message = None
                else:
                    self._current_job.status = JobStatus.FAILED
                    self._current_job.status_message = f"Failed ({len(failed_images)} pages re-queued)"
                    self._current_job.error_message = message

                retry_job = TranslationJob(
                    folder_path=self._current_job.folder_path,
                    folder_name=f"{self._current_job.folder_name} (Retry)",
                    image_paths=failed_images,
                    selected_image_paths=list(failed_images),
                    target_lang=self._current_job.target_lang,
                    job_type=self._current_job.job_type,
                    output_dir=self._current_job.output_dir,
                    status=JobStatus.PENDING,
                    status_message=f"Pending retry ({len(failed_images)} pages)",
                    retry_count=self._current_job.retry_count + 1,
                    max_retries=self._current_job.max_retries
                )
                self.jobs.append(retry_job)
                logger.info(
                    f"Re-queued {len(failed_images)} failed images for '{self._current_job.folder_name}' "
                    f"(retry {retry_job.retry_count}/{retry_job.max_retries})"
                )
            elif success:
                self._current_job.status = JobStatus.COMPLETED
                self._current_job.progress_pct = 100
                self._current_job.status_message = "Completed"
                self._current_job.error_message = None
            else:
                self._current_job.status = JobStatus.FAILED
                self._current_job.status_message = "Failed"
                self._current_job.error_message = message

            self.job_finished.emit(job_id, success, message)
            self.queue_updated.emit()
            self._emit_overall_progress()

        self._current_worker = None
        self._current_job = None

        if self._is_running:
            self._process_next()

    def notify_overall_progress(self):
        """Public trigger to recalculate and emit overall progress."""
        self._emit_overall_progress()

    def _emit_overall_progress(self):
        completed = sum(1 for j in self.jobs if j.status == JobStatus.COMPLETED)
        total = len(self.jobs)
        self.overall_progress.emit(completed, total)
