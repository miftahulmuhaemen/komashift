import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional, Callable

logger = logging.getLogger(__name__)

try:
    from huggingface_hub import try_to_load_from_cache, hf_hub_download
except ImportError:
    try_to_load_from_cache = None
    hf_hub_download = None

COMIC_MODEL_URL = "https://github.com/ogkalu2/comic-text-detector/releases/download/v1.0.1/comic-text-detector.onnx"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "komashift" / "models"
DEFAULT_OCR_MODEL = "mayocream/manga-ocr-onnx"


class AiAssetsManager:
    """Manages AI model assets (ComicTextDetector ONNX, MangaOCR cache), providing resolution and on-demand streaming."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR

    def get_comic_model_path(self) -> Optional[Path]:
        """Resolves local comic text detector model path across install directory, cache, and repo root."""
        candidates = [
            # Custom user cache directory
            self.cache_dir / "comic-text-detector.onnx",
            # PyInstaller _MEIPASS (--onefile)
            Path(getattr(sys, "_MEIPASS", "")) / "assets" / "models" / "comic-text-detector.onnx",
            # Application executable directory (--onedir / installed)
            Path(sys.executable).parent / "assets" / "models" / "comic-text-detector.onnx",
            Path(sys.executable).parent / "_internal" / "assets" / "models" / "comic-text-detector.onnx",
            # Standard HuggingFace / cache fallback
            Path.home() / ".cache" / "comic_text_detector" / "comic-text-detector.onnx",
            # Dev repo root fallback
            Path(__file__).parent.parent.parent / "assets" / "models" / "comic-text-detector.onnx",
        ]
        for c in candidates:
            if c.is_file():
                return c
        return None

    def is_comic_model_available(self) -> bool:
        return self.get_comic_model_path() is not None

    def download_comic_model(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        url: str = COMIC_MODEL_URL,
    ) -> Path:
        """
        Downloads comic-text-detector.onnx to the user cache directory with progress callbacks.
        Returns the resolved Path on success.
        """
        import urllib.request

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        dest_path = self.cache_dir / "comic-text-detector.onnx"
        tmp_path = self.cache_dir / "comic-text-detector.onnx.tmp"

        logger.info(f"Downloading comic text detector model from {url} to {dest_path}")

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "KomaShift-App"}
        )

        with urllib.request.urlopen(req, timeout=30) as response, open(tmp_path, "wb") as out_file:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            block_size = 64 * 1024

            while True:
                if cancel_check and cancel_check():
                    out_file.close()
                    if tmp_path.exists():
                        tmp_path.unlink()
                    raise InterruptedError("Download was cancelled by user.")

                chunk = response.read(block_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size)

        tmp_path.replace(dest_path)
        logger.info(f"Successfully downloaded comic text detector to {dest_path}")
        return dest_path

    @staticmethod
    def is_ocr_model_cached(model_name_or_path: str = "") -> bool:
        """
        Checks whether the specified Manga OCR model is available locally.
        Returns True if:
        1. It is a local directory containing encoder_model.onnx and decoder_model.onnx.
        2. It is a Hugging Face repository ID with cached ONNX files.
        Default (empty string) resolves to 'mayocream/manga-ocr-onnx'.
        """
        target = (model_name_or_path or "").strip()
        if not target:
            target = DEFAULT_OCR_MODEL

        path = Path(target)
        if path.is_dir():
            enc = path / "encoder_model.onnx"
            dec = path / "decoder_model.onnx"
            return enc.is_file() and dec.is_file()

        try:
            if try_to_load_from_cache is None:
                return False
            enc_cached = try_to_load_from_cache(target, "encoder_model.onnx")
            dec_cached = try_to_load_from_cache(target, "decoder_model.onnx")
            return isinstance(enc_cached, str) and isinstance(dec_cached, str)
        except Exception as e:
            logger.debug(f"Failed to check Hugging Face cache for {target}: {e}")
            return False

    @staticmethod
    def download_ocr_model(
        model_name_or_path: str = "",
        progress_callback: Optional[Callable[[int, int], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        pause_check: Optional[Callable[[], bool]] = None,
    ) -> str:
        """
        Downloads the specified Manga OCR model from Hugging Face into the local HF cache.
        Supports progress reporting, pause, and cancellation.
        Returns the resolved local directory path on success.
        """
        target = (model_name_or_path or "").strip()
        if not target:
            target = DEFAULT_OCR_MODEL

        path = Path(target)
        if path.is_dir():
            enc = path / "encoder_model.onnx"
            dec = path / "decoder_model.onnx"
            if enc.is_file() and dec.is_file():
                return str(path.resolve())

        if cancel_check and cancel_check():
            raise InterruptedError("Download was cancelled by user.")

        if status_callback:
            status_callback(f"Connecting to Hugging Face ({target})...")

        import tqdm
        from huggingface_hub import snapshot_download

        class DownloadTqdm(tqdm.std.tqdm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                if status_callback and self.desc:
                    status_callback(f"Downloading {self.desc}...")

            def update(self, n=1):
                if cancel_check and cancel_check():
                    raise InterruptedError("Download was cancelled by user.")
                while pause_check and pause_check():
                    if cancel_check and cancel_check():
                        raise InterruptedError("Download was cancelled by user.")
                    time.sleep(0.08)
                super().update(n)
                if progress_callback and self.total:
                    progress_callback(self.n, self.total)

        downloaded_dir = snapshot_download(
            repo_id=target,
            max_workers=1,
            tqdm_class=DownloadTqdm,
        )

        if status_callback:
            status_callback(f"Model {target} ready.")

        return str(downloaded_dir)

