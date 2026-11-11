from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from PyQt6.QtCore import QObject, pyqtSignal

from src.models.folder_item import FolderItem
from src.services.scanner import scan_directory
from src.services.folder_service import rename_folder
from src.services.trash_service import send_folder_to_trash


class LibraryViewModel(QObject):
    """ViewModel for library folder scanning, selection, renaming, and navigation."""

    folders_loaded = pyqtSignal(list)               # List[FolderItem]
    folder_renamed = pyqtSignal(str, str, str)      # old_path, new_path, new_name
    folders_deleted = pyqtSignal(list)              # List[str] of deleted folder paths
    current_image_changed = pyqtSignal(int)         # index

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._root_path: Optional[Path] = None
        self._folders: List[FolderItem] = []
        self._current_folder: Optional[FolderItem] = None
        self._current_image_index: int = 0

    @property
    def root_path(self) -> Optional[Path]:
        return self._root_path

    @property
    def folders(self) -> List[FolderItem]:
        return self._folders

    @property
    def current_folder(self) -> Optional[FolderItem]:
        return self._current_folder

    @property
    def current_image_index(self) -> int:
        return self._current_image_index

    def load_directory(self, root_path: Path) -> List[FolderItem]:
        """Scan directory for image folders and update internal state."""
        self._root_path = Path(root_path)
        self._folders = scan_directory(self._root_path)
        self.folders_loaded.emit(self._folders)
        return self._folders

    def set_current_folder(self, folder: Optional[FolderItem]) -> None:
        self._current_folder = folder
        self._current_image_index = 0

    def set_current_image_index(self, index: int) -> None:
        self._current_image_index = index
        self.current_image_changed.emit(index)

    def navigate_next(self, total_images: int) -> int:
        """Advance to next image index, wrapping around."""
        if total_images <= 0:
            return 0
        new_idx = (self._current_image_index + 1) % total_images
        self.set_current_image_index(new_idx)
        return new_idx

    def navigate_previous(self, total_images: int) -> int:
        """Go to previous image index, wrapping around."""
        if total_images <= 0:
            return 0
        new_idx = (self._current_image_index - 1 + total_images) % total_images
        self.set_current_image_index(new_idx)
        return new_idx

    def rename(self, target_path: Path, new_name: str) -> Tuple[bool, Optional[str], Optional[Path]]:
        """Rename single folder."""
        success, error, new_path = rename_folder(target_path, new_name)
        if success and new_path:
            self.folder_renamed.emit(str(target_path), str(new_path), new_name)
        return success, error, new_path

    def delete_folders(self, folders: List[FolderItem]) -> Tuple[int, List[str]]:
        """Send selected folders to recycle bin / trash."""
        success_count = 0
        errors = []
        deleted_paths = []
        for folder in folders:
            success, error = send_folder_to_trash(folder.path)
            if success:
                success_count += 1
                deleted_paths.append(str(folder.path))
            else:
                errors.append(f"{folder.name}: {error}")
        if deleted_paths:
            self.folders_deleted.emit(deleted_paths)
        return success_count, errors
