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


class JobType(str, Enum):
    TRANSLATION = "translation"
    RASTERIZE = "rasterize"


@dataclass
class TranslationJob:
    folder_path: Path
    folder_name: str
    image_paths: List[Path]
    target_lang: str = "en"
    job_type: JobType = JobType.TRANSLATION
    selected_image_paths: List[Path] = field(default_factory=list)
    output_dir: Optional[Path] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    progress_current: int = 0
    progress_total: int = 0
    progress_pct: int = 0
    status_message: str = "Pending in queue"
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 2
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.selected_image_paths and self.image_paths:
            self.selected_image_paths = list(self.image_paths)
        if self.output_dir is None and self.job_type == JobType.RASTERIZE:
            self.output_dir = self.folder_path.parent / f"{self.folder_path.name}_translated"

    @property
    def lang_display(self) -> str:
        lang = self.target_lang.lower().strip()
        if lang in ("mix", "mixed", "mix-lang"):
            return "Mix-Lang"
        if lang in ("id", "indonesian"):
            return "ID"
        return "EN"

    @property
    def selected_count(self) -> int:
        return len(self.selected_image_paths)

    @property
    def total_count(self) -> int:
        return len(self.image_paths)

    def select_all(self):
        self.selected_image_paths = list(self.image_paths)

    def unselect_all(self):
        self.selected_image_paths = []

    def select_single(self, path: Path):
        p = Path(path)
        if p in self.image_paths:
            self.selected_image_paths = [p]
        else:
            self.selected_image_paths = []

    def toggle_image(self, path: Path, selected: bool):
        p = Path(path)
        if selected:
            if p in self.image_paths and p not in self.selected_image_paths:
                # Maintain original folder ordering
                ordered = [img for img in self.image_paths if img in self.selected_image_paths or img == p]
                self.selected_image_paths = ordered
        else:
            self.selected_image_paths = [img for img in self.selected_image_paths if img != p]

    def is_image_selected(self, path: Path) -> bool:
        return Path(path) in self.selected_image_paths

    def update_progress(self, message: str, current: int, total: int):
        self.status_message = message
        self.progress_current = current
        self.progress_total = total
        if total > 0:
            self.progress_pct = max(0, min(100, int((current / total) * 100)))
        else:
            self.progress_pct = 0
