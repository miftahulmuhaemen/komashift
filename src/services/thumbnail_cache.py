import io
import os
from pathlib import Path
from typing import Tuple, Optional, Callable, Set
from collections import OrderedDict
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap, QImage, QGuiApplication
from PIL import Image

def _ensure_qt_app():
    if QGuiApplication.instance() is None:
        import sys
        return QGuiApplication(sys.argv if sys.argv else ["app"])
    return QGuiApplication.instance()

def create_thumbnail_image(image_path: Path, size: Tuple[int, int]) -> Optional[QImage]:
    try:
        with Image.open(image_path) as im:
            im.thumbnail(size, Image.Resampling.LANCZOS)
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            
            buffer = io.BytesIO()
            fmt = "PNG" if im.mode == "RGBA" else "JPEG"
            im.save(buffer, format=fmt)
            buffer.seek(0)
            
            qimg = QImage()
            if qimg.loadFromData(buffer.getvalue()):
                return qimg
            return None
    except Exception:
        return None

def create_thumbnail_pixmap(image_path: Path, size: Tuple[int, int]) -> Optional[QPixmap]:
    qimg = create_thumbnail_image(image_path, size)
    if qimg is not None:
        _ensure_qt_app()
        return QPixmap.fromImage(qimg)
    return None

class ThumbnailWorkerSignals(QObject):
    finished = pyqtSignal(str, QImage)

class ThumbnailWorker(QRunnable):
    def __init__(self, image_path: Path, size: Tuple[int, int]):
        super().__init__()
        self.image_path = image_path
        self.size = size
        self.signals = ThumbnailWorkerSignals()

    @pyqtSlot()
    def run(self):
        qimg = create_thumbnail_image(self.image_path, self.size)
        if qimg is not None:
            self.signals.finished.emit(str(self.image_path), qimg)

class ThumbnailCache:
    def __init__(self, max_entries: int = 300):
        self.max_entries = max_entries
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self.thread_pool = QThreadPool.globalInstance()
        self._active_workers: Set[ThumbnailWorker] = set()

    def get(self, image_path: Path, size: Tuple[int, int]) -> Optional[QPixmap]:
        key = f"{image_path}:{size[0]}x{size[1]}"
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def put(self, key: str, pixmap: QPixmap):
        if len(self._cache) >= self.max_entries:
            self._cache.popitem(last=False)
        self._cache[key] = pixmap

    def load_async(self, image_path: Path, size: Tuple[int, int], on_loaded: Callable[[str, QPixmap], None]):
        cached = self.get(image_path, size)
        if cached:
            on_loaded(str(image_path), cached)
            return

        worker = ThumbnailWorker(image_path, size)
        key = f"{image_path}:{size[0]}x{size[1]}"

        def handle_finished(path_str: str, qimg: QImage):
            self._active_workers.discard(worker)
            pixmap = QPixmap.fromImage(qimg)
            self.put(key, pixmap)
            on_loaded(path_str, pixmap)

        worker.signals.finished.connect(handle_finished)
        self._active_workers.add(worker)
        self.thread_pool.start(worker)

