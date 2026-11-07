from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import time
import uuid
from typing import List, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TranslationJob:
    folder_path: Path
    folder_name: str
    image_paths: List[Path]
    target_lang: str = "en"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    progress_current: int = 0
    progress_total: int = 0
    progress_pct: int = 0
    status_message: str = "Pending in queue"
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    @property
    def lang_display(self) -> str:
        return "ID" if self.target_lang.lower() in ("id", "indonesian") else "EN"

    def update_progress(self, message: str, current: int, total: int):
        self.status_message = message
        self.progress_current = current
        self.progress_total = total
        if total > 0:
            self.progress_pct = max(0, min(100, int((current / total) * 100)))
        else:
            self.progress_pct = 0
