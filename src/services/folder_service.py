from pathlib import Path
from typing import Tuple, Optional

def rename_folder(current_path: Path | str, new_name: str) -> Tuple[bool, Optional[str], Optional[Path]]:
    path = Path(current_path)
    if not path.exists():
        return False, f"Folder does not exist: {path}", None

    clean_name = new_name.strip()
    if not clean_name:
        return False, "Folder name cannot be empty.", None

    # Check for invalid characters on Windows/Linux
    invalid_chars = '<>:"/\\|?*'
    if any(c in clean_name for c in invalid_chars):
        return False, f"Folder name cannot contain any of: {invalid_chars}", None

    new_path = path.parent / clean_name
    if new_path == path:
        return True, None, path

    if new_path.exists():
        return False, f"A folder named '{clean_name}' already exists in this location.", None

    try:
        path.rename(new_path)
        return True, None, new_path
    except Exception as e:
        return False, str(e), None
