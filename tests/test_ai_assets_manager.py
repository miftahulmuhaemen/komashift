import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from src.services.ai_assets_manager import AiAssetsManager, DEFAULT_OCR_MODEL


def test_is_ocr_model_cached_default():
    # Empty string defaults to DEFAULT_OCR_MODEL
    with patch("huggingface_hub.try_to_load_from_cache", return_value="/mock/path/model.onnx"):
        assert AiAssetsManager.is_ocr_model_cached("") is True


def test_is_ocr_model_cached_local_dir_valid(tmp_path):
    model_dir = tmp_path / "valid_model"
    model_dir.mkdir()
    (model_dir / "encoder_model.onnx").touch()
    (model_dir / "decoder_model.onnx").touch()

    assert AiAssetsManager.is_ocr_model_cached(str(model_dir)) is True


def test_is_ocr_model_cached_local_dir_missing_files(tmp_path):
    model_dir = tmp_path / "incomplete_model"
    model_dir.mkdir()
    (model_dir / "encoder_model.onnx").touch()
    # Missing decoder_model.onnx

    assert AiAssetsManager.is_ocr_model_cached(str(model_dir)) is False


def test_is_ocr_model_cached_uncached_hf():
    with patch("huggingface_hub.try_to_load_from_cache", return_value=None):
        assert AiAssetsManager.is_ocr_model_cached("uncached/repo") is False


def test_download_ocr_model_local_dir(tmp_path):
    model_dir = tmp_path / "local_repo"
    model_dir.mkdir()
    (model_dir / "encoder_model.onnx").touch()
    (model_dir / "decoder_model.onnx").touch()

    res = AiAssetsManager.download_ocr_model(str(model_dir))
    assert res == str(model_dir.resolve())


def test_download_ocr_model_cancelled():
    with pytest.raises(InterruptedError):
        AiAssetsManager.download_ocr_model(
            "custom/repo",
            cancel_check=lambda: True
        )
