import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.services.update_checker import (
    parse_semver,
    is_newer_version,
    UpdateCheckerService,
    ReleaseInfo,
)
from src.services.ai_assets_manager import AiAssetsManager


def test_semver_parsing_and_comparison():
    assert parse_semver("1.0.24") == (1, 0, 24)
    assert parse_semver("v1.2.0") == (1, 2, 0)
    assert parse_semver("2.0") == (2, 0, 0)

    assert is_newer_version("1.0.25", "1.0.24") is True
    assert is_newer_version("1.1.0", "1.0.24") is True
    assert is_newer_version("2.0.0", "1.99.99") is True
    assert is_newer_version("1.0.24", "1.0.24") is False
    assert is_newer_version("1.0.23", "1.0.24") is False


def test_update_checker_service_handles_newer_release():
    fake_response = {
        "tag_name": "v1.1.0",
        "body": "Bugfixes and performance improvements",
        "assets": [
            {
                "name": "KomaShift-Setup-v1.1.0.exe",
                "browser_download_url": "https://github.com/sahana/win-folder-thumbnail/releases/download/v1.1.0/KomaShift-Setup-v1.1.0.exe",
                "size": 52428800,
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = str(fake_response).replace("'", '"').encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        checker = UpdateCheckerService(repo="sahana/win-folder-thumbnail")
        info = checker.check_for_updates(current_version="1.0.24")

        assert info is not None
        assert info.version == "1.1.0"
        assert info.setup_asset_name == "KomaShift-Setup-v1.1.0.exe"
        assert info.setup_size_bytes == 52428800


def test_update_checker_service_returns_none_when_up_to_date():
    fake_response = {
        "tag_name": "v1.0.24",
        "body": "Current version",
        "assets": []
    }

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = str(fake_response).replace("'", '"').encode("utf-8")

    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        checker = UpdateCheckerService(repo="sahana/win-folder-thumbnail")
        info = checker.check_for_updates(current_version="1.0.24")

        assert info is None


def test_ai_assets_manager_resolution(tmp_path: Path):
    manager = AiAssetsManager(cache_dir=tmp_path)
    fake_model = tmp_path / "comic-text-detector.onnx"
    fake_model.write_text("dummy-weights")

    resolved = manager.get_comic_model_path()
    assert resolved == fake_model
    assert manager.is_comic_model_available() is True


def test_comic_model_url_validity():
    from src.services.ai_assets_manager import COMIC_MODEL_URL
    assert "huggingface.co" in COMIC_MODEL_URL
    assert "comictextdetector.pt.onnx" in COMIC_MODEL_URL


def test_inno_setup_script_structure():
    iss_path = Path(__file__).parent.parent / "installer" / "komashift_setup.iss"
    assert iss_path.is_file()
    content = iss_path.read_text(encoding="utf-8")
    assert "DefaultDirName={localappdata}\\Programs\\{#MyAppName}" in content
    assert "PrivilegesRequired=lowest" in content


def test_manga_ocr_detector_bubble_detector_availability():
    from src.services.manga_ocr_detector import MangaOcrDetector
    detector = MangaOcrDetector()
    detector._onnx_detector.is_available = MagicMock(return_value=True)
    assert detector.is_bubble_detector_available() is True

    detector._onnx_detector.is_available = MagicMock(return_value=False)
    assert detector.is_bubble_detector_available() is False

