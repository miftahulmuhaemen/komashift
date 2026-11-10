import os
from pathlib import Path
import pytest
from PyQt6.QtCore import QThreadPool, QSettings
from PyQt6.QtWidgets import QApplication
from PIL import Image

@pytest.fixture(autouse=True)
def drain_threadpool():
    """Cancel pending workers and drain QThreadPool to prevent async segfaults."""
    yield
    pool = QThreadPool.globalInstance()
    if pool is not None:
        pool.clear()
        pool.waitForDone(500)

@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path: Path):
    """Isolate QSettings into a temporary INI file so tests never touch host settings."""
    original_format = QSettings.defaultFormat()
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path))

    s = QSettings("FolderImagePreviewer", "FolderImagePreviewer")
    s.clear()
    s.setValue("llm_api_key", "test-api-key")
    s.setValue("llm_model", "test-model")
    s.setValue("llm_endpoint", "https://api.openai.com/v1")
    del s

    yield

    try:
        s2 = QSettings("FolderImagePreviewer", "FolderImagePreviewer")
        s2.clear()
        del s2
    except Exception:
        pass
    QSettings.setDefaultFormat(original_format)

@pytest.fixture
def tmp_library(tmp_path: Path) -> Path:
    """Create a sample 2-chapter x 2-page image directory for tests."""
    root = tmp_path / "manga_library"
    root.mkdir(parents=True, exist_ok=True)
    ch1 = root / "Chapter 01"
    ch1.mkdir()
    ch2 = root / "Chapter 02"
    ch2.mkdir()

    for ch in (ch1, ch2):
        im1 = Image.new("RGB", (100, 150), color="white")
        im1.save(ch / "01.png")
        im2 = Image.new("RGB", (100, 150), color="white")
        im2.save(ch / "02.png")

    return root
