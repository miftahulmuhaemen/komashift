from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

@dataclass
class FolderItem:
    path: Path
    name: str
    image_paths: List[Path] = field(default_factory=list)

    @property
    def image_count(self) -> int:
        return len(self.image_paths)

    @property
    def first_image(self) -> Optional[Path]:
        return self.image_paths[0] if self.image_paths else None
