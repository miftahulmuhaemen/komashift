import weakref
from pathlib import Path
from typing import Tuple, Optional, Callable, Set
from collections import OrderedDict
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, pyqtSlot, Qt
from PyQt6.QtGui import QPixmap, QImage

from src.services.thumbnail_cache import create_thumbnail_image


class ThumbnailWorkerSignals(QObject):
    finished = pyqtSignal(str, QImage)


class ThumbnailWorker(QRunnable):
    def __init__(self, image_path: Path, size: Tuple[int, int]):
        super().__init__()
        self.image_path = image_path
        self.size = size
        self.signals = ThumbnailWorkerSignals()
        self.is_cancelled = False

    @pyqtSlot()
    def run(self):
        if self.is_cancelled:
            return
        qimg = create_thumbnail_image(self.image_path, self.size)
        if qimg is not None and not self.is_cancelled:
            try:
                self.signals.finished.emit(str(self.image_path), qimg)
            except RuntimeError:
                pass


class ThumbnailCache(QObject):
    def __init__(self, max_entries: int = 300, parent=None):
        super().__init__(parent)
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
        weak_self = weakref.ref(self)

        def handle_finished(path_str: str, qimg: QImage):
            instance = weak_self()
            if instance is None:
                return
            try:
                instance._active_workers.discard(worker)
                if qimg is not None and not qimg.isNull():
                    pixmap = QPixmap.fromImage(qimg)
                    if not pixmap.isNull():
                        instance.put(key, pixmap)
                        on_loaded(path_str, pixmap)
            except (RuntimeError, Exception):
                pass

        worker.signals.finished.connect(handle_finished, Qt.ConnectionType.QueuedConnection)
        self._active_workers.add(worker)
        self.thread_pool.start(worker)

    def shutdown(self, wait_ms: int = 500):
        """Cancel pending tasks and wait for threadpool to drain."""
        for worker in list(self._active_workers):
            try:
                worker.is_cancelled = True
            except Exception:
                pass
        self._active_workers.clear()
        if self.thread_pool:
            try:
                self.thread_pool.waitForDone(wait_ms)
            except Exception:
                pass
