"""Vista circular del mismo JPEG enviado por el trabajador LCD."""
from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QPainter, QColor, QPainterPath, QPixmap, QPen
from PyQt6.QtWidgets import QWidget


class LCDCapPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.setMaximumSize(340, 340)
        self._pixmap = QPixmap()

    def sizeHint(self):
        return QSize(320, 320)

    def set_jpeg(self, jpeg):
        pixmap = QPixmap()
        if jpeg:
            pixmap.loadFromData(jpeg, 'JPEG')
        self._pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height()) - 12
        rect = QRectF((self.width()-size)/2, (self.height()-size)/2, size, size)
        path = QPainterPath()
        path.addEllipse(rect)
        painter.setClipPath(path)
        painter.fillRect(rect, QColor('#101827'))
        if not self._pixmap.isNull():
            painter.drawPixmap(rect.toRect(), self._pixmap)
        else:
            painter.setPen(QColor('#b9c2d4'))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, 'Previsualización\nno disponible')
        painter.setClipping(False)
        painter.setPen(QPen(QColor('#36445e'), 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)
        painter.end()
