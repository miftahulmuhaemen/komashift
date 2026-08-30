from pathlib import Path
from src.services.folder_service import rename_folder

def test_rename_folder_success(tmp_path: Path):
    folder = tmp_path / "old_name"
    folder.mkdir()
    (folder / "file.txt").write_text("hello")

    success, error, new_path = rename_folder(folder, "new_name")
    assert success is True
    assert error is None
    assert new_path == tmp_path / "new_name"
    assert new_path.exists()
    assert not folder.exists()
    assert (new_path / "file.txt").read_text() == "hello"

def test_rename_folder_same_name(tmp_path: Path):
    folder = tmp_path / "same_name"
    folder.mkdir()

    success, error, new_path = rename_folder(folder, "same_name")
    assert success is True
    assert error is None
    assert new_path == folder

def test_rename_folder_already_exists(tmp_path: Path):
    f1 = tmp_path / "f1"
    f2 = tmp_path / "f2"
    f1.mkdir()
    f2.mkdir()

    success, error, new_path = rename_folder(f1, "f2")
    assert success is False
    assert "already exists" in error

def test_rename_folder_invalid_name(tmp_path: Path):
    folder = tmp_path / "f1"
    folder.mkdir()

    success, error, new_path = rename_folder(folder, "invalid/name")
    assert success is False
    assert "cannot contain" in error

def test_rename_non_existent(tmp_path: Path):
    folder = tmp_path / "non_existent"
    success, error, new_path = rename_folder(folder, "something")
    assert success is False
    assert "does not exist" in error
