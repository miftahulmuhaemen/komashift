import io
from pathlib import Path
from typing import Tuple, Optional
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
