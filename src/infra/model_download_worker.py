import logging
from typing import Optional
from PyQt6.QtCore import QThread, pyqtSignal
from src.services.ai_assets_manager import AiAssetsManager

logger = logging.getLogger(__name__)


class ModelCacheCheckWorker(QThread):
    """Checks whether a Manga OCR model is cached or present locally in a background thread."""
    check_completed = pyqtSignal(str, bool)  # (model_id, is_cached)

    def __init__(self, model_id: str, parent=None):
        super().__init__(parent)
        self.model_id = str(model_id).strip()

    def run(self):
        try:
            is_cached = AiAssetsManager.is_ocr_model_cached(self.model_id)
            self.check_completed.emit(self.model_id, is_cached)
        except Exception as e:
            logger.debug(f"Cache check error for {self.model_id}: {e}")
            self.check_completed.emit(self.model_id, False)


class ModelDownloadWorker(QThread):
    """
    Downloads Manga OCR model assets from Hugging Face in a background thread.
    Supports real-time progress callbacks, pause, resume, and cancellation.
    """
    progress = pyqtSignal(int, int, int)       # (downloaded_bytes, total_bytes, percent)
    status_changed = pyqtSignal(str)           # status message
    finished = pyqtSignal(bool, str)            # (success, message_or_resolved_path)

    def __init__(self, model_id: str, parent=None):
        super().__init__(parent)
        self.model_id = str(model_id).strip()
        self._is_paused = False
        self._is_cancelled = False

    def pause(self):
        self._is_paused = True
        self.status_changed.emit("Download paused.")

    def resume(self):
        self._is_paused = False
        self.status_changed.emit("Resuming download...")

    def cancel(self):
        self._is_cancelled = True
        self._is_paused = False
        self.requestInterruption()
        self.status_changed.emit("Cancelling download...")

    def is_paused(self) -> bool:
        return self._is_paused

    def is_cancelled(self) -> bool:
        return self._is_cancelled or self.isInterruptionRequested()

    def run(self):
        def _on_progress(downloaded: int, total: int):
            pct = int((downloaded / total) * 100) if total > 0 else 0
            self.progress.emit(downloaded, total, pct)

        def _on_status(msg: str):
            self.status_changed.emit(msg)

        try:
            resolved_path = AiAssetsManager.download_ocr_model(
                model_name_or_path=self.model_id,
                progress_callback=_on_progress,
                status_callback=_on_status,
                cancel_check=self.is_cancelled,
                pause_check=self.is_paused,
            )
            self.finished.emit(True, resolved_path)
        except InterruptedError:
            self.finished.emit(False, "Download was cancelled.")
        except Exception as e:
            logger.warning(f"Error downloading model {self.model_id}: {e}")
            self.finished.emit(False, str(e))
