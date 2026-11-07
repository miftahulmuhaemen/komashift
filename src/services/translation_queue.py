import logging
from pathlib import Path
from typing import List, Optional
from PyQt6.QtCore import QObject, pyqtSignal
from src.models.translation_job import TranslationJob, JobStatus
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

    def add_job(self, folder_path: Path, image_paths: List[Path], target_lang: str = "en") -> TranslationJob:
        folder_path = Path(folder_path)
        # Check if job already exists in pending or running state
        for j in self.jobs:
            if j.folder_path == folder_path and j.status in (JobStatus.PENDING, JobStatus.RUNNING):
                j.target_lang = target_lang
                self.queue_updated.emit()
                return j

        job = TranslationJob(
            folder_path=folder_path,
            folder_name=folder_path.name,
            image_paths=list(image_paths),
            target_lang=target_lang,
            status=JobStatus.PENDING
        )
        self.jobs.append(job)
        self.queue_updated.emit()
        self._emit_overall_progress()

        # If queue is already running and idle, process next
        if self._is_running and self._current_worker is None:
            self._process_next()

        return job

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
        self._process_next()

    def pause_queue(self):
        self._is_running = False
        self.queue_state_changed.emit(False)
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.requestInterruption()

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

        self._current_job = next_job
        next_job.status = JobStatus.RUNNING
        next_job.status_message = "Starting..."
        self.job_started.emit(next_job.id)
        self.queue_updated.emit()

        api_key, base_url, model, timeout, batch_size = self._get_api_credentials()
        self._current_worker = TranslationWorker(
            folder_path=next_job.folder_path,
            image_paths=next_job.image_paths,
            api_key=api_key,
            base_url=base_url,
            model=model,
            target_lang=next_job.target_lang,
            detector=self.detector,
            timeout=timeout,
            batch_size=batch_size
        )
        self._current_worker.progress_updated.connect(self._on_worker_progress)
        self._current_worker.translation_finished.connect(self._on_worker_finished)
        self._current_worker.start()

    def _get_api_credentials(self):
        if self.settings_getter:
            res = self.settings_getter()
            if len(res) >= 5:
                return res[0], res[1], res[2], res[3], res[4]
            return res[0], res[1], res[2], 120.0, 40
        return ("", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash", 120.0, 40)

    def _on_worker_progress(self, message: str, current: int, total: int):
        if self._current_job:
            self._current_job.update_progress(message, current, total)
            self.job_progress.emit(self._current_job.id, message, current, total)

    def _on_worker_finished(self, success: bool, message: str):
        if self._current_job:
            job_id = self._current_job.id
            if success:
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

    def _emit_overall_progress(self):
        completed = sum(1 for j in self.jobs if j.status == JobStatus.COMPLETED)
        total = len(self.jobs)
        self.overall_progress.emit(completed, total)
