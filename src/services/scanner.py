import os
import re
from pathlib import Path
from typing import List, Set, Optional, Union
from src.models.folder_item import FolderItem

DEFAULT_IMAGE_EXTENSIONS: Set[str] = {
    '.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'
}

def natural_sort_key(item: Union[Path, str]) -> List[Union[int, str]]:
    name = item.name if isinstance(item, Path) else str(item)
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', name)]

def scan_directory(
    root_path: Path | str,
    supported_extensions: Optional[Set[str]] = None
) -> List[FolderItem]:
    root = Path(root_path)
    if not root.is_dir():
        return []

    exts = supported_extensions or DEFAULT_IMAGE_EXTENSIONS
    folder_items: List[FolderItem] = []

    try:
        entries = sorted(list(root.iterdir()), key=natural_sort_key)
    except (PermissionError, OSError):
        return []

    for entry in entries:
        if not entry.is_dir() or entry.name.startswith(('.', '$')):
            continue

        try:
            image_paths = [
                img for img in entry.iterdir()
                if img.is_file() and img.suffix.lower() in exts
            ]
        except (PermissionError, OSError):
            continue

        if image_paths:
            image_paths.sort(key=natural_sort_key)
            folder_items.append(
                FolderItem(
                    path=entry,
                    name=entry.name,
                    image_paths=image_paths
                )
            )

    return folder_items
