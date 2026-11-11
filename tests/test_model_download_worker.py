import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QThread
from src.infra.model_download_worker import ModelCacheCheckWorker, ModelDownloadWorker


def test_model_cache_check_worker_cached(qtbot):
    with patch("src.services.ai_assets_manager.AiAssetsManager.is_ocr_model_cached", return_value=True):
        worker = ModelCacheCheckWorker("some/cached-model")
        with qtbot.waitSignal(worker.check_completed, timeout=1000) as blocker:
            worker.start()
        model_id, is_cached = blocker.args
        assert model_id == "some/cached-model"
        assert is_cached is True
        worker.wait()


def test_model_cache_check_worker_uncached(qtbot):
    with patch("src.services.ai_assets_manager.AiAssetsManager.is_ocr_model_cached", return_value=False):
        worker = ModelCacheCheckWorker("some/uncached-model")
        with qtbot.waitSignal(worker.check_completed, timeout=1000) as blocker:
            worker.start()
        model_id, is_cached = blocker.args
        assert model_id == "some/uncached-model"
        assert is_cached is False
        worker.wait()


def test_model_download_worker_success(qtbot):
    with patch(
        "src.services.ai_assets_manager.AiAssetsManager.download_ocr_model",
        return_value="/mock/cache/path"
    ) as mock_download:
        worker = ModelDownloadWorker("custom/model")
        with qtbot.waitSignal(worker.finished, timeout=1000) as blocker:
            worker.start()
        success, res = blocker.args
        assert success is True
        assert res == "/mock/cache/path"
        worker.wait()


def test_model_download_worker_pause_resume_cancel(qtbot):
    worker = ModelDownloadWorker("custom/model")
    assert worker.is_paused() is False
    assert worker.is_cancelled() is False

    worker.pause()
    assert worker.is_paused() is True

    worker.resume()
    assert worker.is_paused() is False

    worker.cancel()
    assert worker.is_cancelled() is True


def test_model_download_worker_cancelled_exception(qtbot):
    with patch(
        "src.services.ai_assets_manager.AiAssetsManager.download_ocr_model",
        side_effect=InterruptedError("Cancelled")
    ):
        worker = ModelDownloadWorker("custom/model")
        with qtbot.waitSignal(worker.finished, timeout=1000) as blocker:
            worker.start()
        success, msg = blocker.args
        assert success is False
        assert "cancelled" in msg.lower()
        worker.wait()
