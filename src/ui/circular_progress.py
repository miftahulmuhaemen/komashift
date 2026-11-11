from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QTimer, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor


class CircularSpinner(QWidget):
    """
    Lightweight, smooth indeterminate circular progress spinner.
    Renders directly via QPainter without external gif/images.
    """
    def __init__(self, parent=None, size: int = 18, color: str = "#38bdf8", track_color: str = "#334155"):
        super().__init__(parent)
        self._size = size
        self._color = QColor(color)
        self._track_color = QColor(track_color)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self.setFixedSize(self._size, self._size)
        self.setVisible(False)

    def _rotate(self):
        self._angle = (self._angle + 30) % 360
        self.update()

    def start(self):
        if not self._timer.isActive():
            self._timer.start(40)
        self.setVisible(True)
        self.update()

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()
        self.setVisible(False)

    def paintEvent(self, event):
        if not self.isVisible():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen_width = 2.2
        margin = pen_width / 2.0 + 1.0
        rect = QRectF(margin, margin, self.width() - 2 * margin, self.height() - 2 * margin)

        # Background track
        track_pen = QPen(self._track_color, pen_width)
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawEllipse(rect)

        # Spinning arc
        arc_pen = QPen(self._color, pen_width)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)

        # In Qt, 1 degree = 16 1/16th degrees
        start_angle = int(self._angle * 16)
        span_angle = int(100 * 16)
        painter.drawArc(rect, start_angle, span_angle)
