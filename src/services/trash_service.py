from pathlib import Path
from typing import Tuple, Optional
from send2trash import send2trash

def send_folder_to_trash(folder_path: Path | str) -> Tuple[bool, Optional[str]]:
    path = Path(folder_path)
    if not path.exists():
        return False, f'Path does not exist: {path}'

    try:
        send2trash(str(path))
        return True, None
    except Exception as e:
        return False, str(e)
