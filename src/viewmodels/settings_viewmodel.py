from typing import Tuple, Optional, List
from PyQt6.QtCore import QObject, QSettings, pyqtSignal


class SettingsViewModel(QObject):
    """ViewModel for application configuration and QSettings management."""

    settings_changed = pyqtSignal()

    def __init__(self, settings: Optional[QSettings] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._settings = settings if settings is not None else QSettings("KomaShift", "KomaShift")

    @property
    def raw_settings(self) -> QSettings:
        """Access underlying QSettings instance for Qt dialog integration."""
        return self._settings

    def get_last_root_folder(self) -> Optional[str]:
        val = self._settings.value("last_root_folder", type=str)
        return val if val else None

    def set_last_root_folder(self, path: str) -> None:
        self._settings.setValue("last_root_folder", str(path))
        self.settings_changed.emit()

    def get_api_credentials(self) -> Tuple[str, str, str, int, int, str, int, int, int, str, str, bool]:
        """Returns (api_key, base_url, model, timeout, batch_size, engine_mode, scale_pct, quality, max_retries, protocol, manga_ocr_model, onnx_force_cpu)."""
        api_key = self._settings.value("llm_api_key", "", type=str).strip()
        base_url = self._settings.value(
            "llm_base_url",
            "https://generativelanguage.googleapis.com/v1beta/openai/",
            type=str
        )
        model = self._settings.value("llm_model", "gemini-2.5-flash", type=str)
        timeout = max(300, self._settings.value("llm_timeout_seconds", 300, type=int))
        batch_size = self._settings.value("llm_batch_size", 0, type=int)
        engine_mode = self._settings.value("llm_engine_mode", "hybrid", type=str)
        vision_scale_pct = self._settings.value("llm_vision_scale_pct", 75, type=int)
        vision_quality = self._settings.value("llm_vision_quality", 75, type=int)
        max_retries = max(1, min(5, self._settings.value("llm_max_retries", 3, type=int)))
        protocol = self._settings.value("llm_protocol", "openai", type=str)
        manga_ocr_model = self._settings.value("manga_ocr_model", "", type=str).strip()
        onnx_force_cpu = self._settings.value("onnx_force_cpu", False, type=bool)
        return (
            api_key,
            base_url,
            model,
            timeout,
            batch_size,
            engine_mode,
            vision_scale_pct,
            vision_quality,
            max_retries,
            protocol,
            manga_ocr_model,
            onnx_force_cpu,
        )

    def get_manga_ocr_model(self) -> str:
        return self._settings.value("manga_ocr_model", "", type=str).strip()

    def set_manga_ocr_model(self, model: str) -> None:
        self._settings.setValue("manga_ocr_model", str(model).strip())
        self.settings_changed.emit()

    def get_onnx_force_cpu(self) -> bool:
        return self._settings.value("onnx_force_cpu", False, type=bool)

    def set_onnx_force_cpu(self, force: bool) -> None:
        self._settings.setValue("onnx_force_cpu", bool(force))
        self.settings_changed.emit()

    def get_detected_providers(self) -> List[str]:
        try:
            from src.services.onnx_bubble_detector import OnnxBubbleDetector
            return OnnxBubbleDetector.get_detected_providers()
        except Exception:
            return ["CPUExecutionProvider"]

    def set_api_key(self, api_key: str) -> None:
        self._settings.setValue("llm_api_key", api_key.strip())
        self.settings_changed.emit()

    def check_for_updates(self, on_available_callback) -> None:
        try:
            from src.services.update_checker import UpdateCheckWorker
            self._update_worker = UpdateCheckWorker(parent=self)
            self._update_worker.update_available.connect(lambda info: on_available_callback(info.version))
            self._update_worker.start()
        except Exception:
            pass
