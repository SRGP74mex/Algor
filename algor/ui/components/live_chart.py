from collections import deque
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath, QLinearGradient
from PyQt6.QtWidgets import QWidget


class LiveChart(QWidget):
    """
    Gráfica en tiempo real de alta definición para telemetría continua de temperaturas y RPMs.
    """

    def __init__(self, max_samples: int = 50, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 180)
        self.max_samples = max_samples

        self.cpu_history = deque(maxlen=max_samples)
        self.gpu_history = deque(maxlen=max_samples)
        self.liquid_history = deque(maxlen=max_samples)

        # Rango de temperaturas predeterminado
        self.min_val = 20.0
        self.max_val = 90.0

        # Márgenes
        self.margin_left = 40
        self.margin_right = 16
        self.margin_top = 16
        self.margin_bottom = 24

    def add_sample(self, cpu_temp: float, gpu_temp: float, liquid_temp: float):
        self.cpu_history.append(cpu_temp)
        self.gpu_history.append(gpu_temp)
        self.liquid_history.append(liquid_temp)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        plot_w = w - self.margin_left - self.margin_right
        plot_h = h - self.margin_top - self.margin_bottom

        # 1. Fondo del gráfico
        plot_rect = QRectF(self.margin_left, self.margin_top, plot_w, plot_h)
        painter.fillRect(plot_rect, QColor("#121722"))
        painter.setPen(QPen(QColor("#243044"), 1))
        painter.drawRect(plot_rect)

        # 2. Líneas horizontales de referencia
        font = QFont(self.font())
        font.setPixelSize(10)
        painter.setFont(font)
        
        grid_pen = QPen(QColor("#1c2638"), 1, Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)

        for temp in [30, 50, 70, 90]:
            y_ratio = (temp - self.min_val) / (self.max_val - self.min_val)
            py = self.margin_top + (1.0 - y_ratio) * plot_h
            painter.drawLine(QPointF(self.margin_left, py), QPointF(w - self.margin_right, py))

            # Etiqueta
            painter.setPen(QColor("#6e7681"))
            painter.drawText(QRectF(0, py - 7, self.margin_left - 6, 14),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{temp}°")
            painter.setPen(grid_pen)

        # 3. Dibujar series temporales
        self._draw_series(painter, self.cpu_history, QColor("#00f0ff"), plot_w, plot_h, fill=True)
        self._draw_series(painter, self.gpu_history, QColor("#bd00ff"), plot_w, plot_h, fill=False)
        self._draw_series(painter, self.liquid_history, QColor("#00e676"), plot_w, plot_h, fill=False)

        # 4. Leyenda superior
        legend_x = self.margin_left + 10
        legend_y = self.margin_top + 10
        self._draw_legend_item(painter, legend_x, legend_y, "CPU", QColor("#00f0ff"))
        self._draw_legend_item(painter, legend_x + 65, legend_y, "GPU", QColor("#bd00ff"))
        self._draw_legend_item(painter, legend_x + 130, legend_y, "Líquido", QColor("#00e676"))

        painter.end()

    def _draw_series(self, painter: QPainter, history: deque, color: QColor,
                     plot_w: float, plot_h: float, fill: bool = False):
        if len(history) < 2:
            return

        # Separar huecos sin inventar ni unir lecturas ausentes.
        if None in history:
            # Los huecos permanecen vacíos; dibujar cada tramo en su posición.
            offset = 0
            for i, value in enumerate(history):
                if value is None:
                    offset = i + 1
                elif i == len(history) - 1 or history[i + 1] is None:
                    chunk = list(history)[offset:i + 1]
                    old_samples = self.max_samples
                    # Usar coordenadas originales mediante desplazamiento temporal.
                    painter.save()
                    painter.translate(-(len(history) - i - 1) * plot_w / (old_samples - 1), 0)
                    self._draw_series(painter, chunk, color, plot_w, plot_h, fill)
                    painter.restore()
            return
        pts = []
        step_x = plot_w / float(self.max_samples - 1)
        start_offset = (self.max_samples - len(history)) * step_x

        for i, val in enumerate(history):
            px = self.margin_left + start_offset + i * step_x
            y_ratio = max(0.0, min(1.0, (val - self.min_val) / (self.max_val - self.min_val)))
            py = self.margin_top + (1.0 - y_ratio) * plot_h
            pts.append(QPointF(px, py))

        path = QPainterPath()
        path.moveTo(pts[0])
        for p in pts[1:]:
            path.lineTo(p)

        # Relleno opcional para CPU
        if fill:
            fill_path = QPainterPath(path)
            fill_path.lineTo(pts[-1].x(), self.margin_top + plot_h)
            fill_path.lineTo(pts[0].x(), self.margin_top + plot_h)
            fill_path.closeSubpath()

            grad = QLinearGradient(0, self.margin_top, 0, self.margin_top + plot_h)
            grad.setColorAt(0.0, QColor(color.red(), color.green(), color.blue(), 40))
            grad.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.fillPath(fill_path, QBrush(grad))

        # Línea de la serie
        pen = QPen(color, 2.0)
        painter.setPen(pen)
        painter.drawPath(path)

    def _draw_legend_item(self, painter: QPainter, x: float, y: float, label: str, color: QColor):
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(x, y + 2, 8, 8), 2, 2)
        
        painter.setPen(QColor("#c9d1d9"))
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(x + 12, y - 2, 50, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)

