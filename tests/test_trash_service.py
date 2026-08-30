from pathlib import Path
from unittest.mock import patch
from src.services.trash_service import send_folder_to_trash

def test_send_folder_to_trash_success(tmp_path: Path):
    target = tmp_path / "delete_me"
    target.mkdir()

    with patch("src.services.trash_service.send2trash") as mock_trash:
        success, error = send_folder_to_trash(target)
        assert success is True
        assert error is None
        mock_trash.assert_called_once_with(str(target))

def test_send_folder_to_trash_non_existent():
    success, error = send_folder_to_trash(Path("/non/existent/path"))
    assert success is False
    assert "does not exist" in error
