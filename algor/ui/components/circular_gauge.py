import math
from PyQt6.QtCore import Qt, QRectF, QPropertyAnimation, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QLinearGradient, QConicalGradient
from PyQt6.QtWidgets import QWidget


class CircularGauge(QWidget):
    """
    Medidor circular animado de alta definición con estética Dark/Cyber Neon.
    """

    def __init__(self, title: str = "TEMP", unit: str = "°C", min_val: float = 0, max_val: float = 100,
                 accent_color: str = "#00f0ff", parent=None):
        super().__init__(parent)
        self.title = title
        self.unit = unit
        self.min_val = min_val
        self.max_val = max_val
        self.accent_color = QColor(accent_color)
        
        self._available = False
        self._current_value = min_val
        self._displayed_value = min_val
        
        # Animación de valor suave
        self._anim = QPropertyAnimation(self, b"animated_value")
        self._anim.setDuration(400)
        
        self.setMinimumSize(160, 160)
        self.setMaximumSize(220, 220)

    def get_animated_value(self) -> float:
        return self._displayed_value

    def set_animated_value(self, val: float):
        self._displayed_value = val
        self.update()

    animated_value = pyqtProperty(float, get_animated_value, set_animated_value)

    def set_value(self, val: float, animated: bool = True):
        self._available = val is not None and math.isfinite(val)
        if not self._available:
            self._anim.stop()
            self._displayed_value = self.min_val
            self.update()
            return
        clamped = max(self.min_val, min(self.max_val, float(val)))
        self._current_value = clamped
        if animated:
            self._anim.stop()
            self._anim.setStartValue(self._displayed_value)
            self._anim.setEndValue(clamped)
            self._anim.start()
        else:
            self._displayed_value = clamped
            self.update()

    def set_accent_color(self, hex_color: str):
        self.accent_color = QColor(hex_color)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        size = min(w, h)
        center_x = w / 2.0
        center_y = h / 2.0
        
        margin = 14
        radius = (size / 2.0) - margin
        rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)

        start_angle = 225  # Ángulo de inicio (grados)
        span_total = -270  # Recorrido total (270 grados en sentido horario)

        # 1. Fondo de la pista (Track)
        track_pen = QPen(QColor("#182130"), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, int(start_angle * 16), int(span_total * 16))

        # 2. Pista de progreso activa
        progress_ratio = (self._displayed_value - self.min_val) / max(1.0, (self.max_val - self.min_val))
        active_span = span_total * progress_ratio

        # Color dinámico basado en temperatura o acento
        if self.unit == "°C":
            if self._displayed_value < 50:
                fg_color = QColor("#00e676")  # Verde fresco
            elif self._displayed_value < 70:
                fg_color = QColor("#00f0ff")  # Cian normal
            elif self._displayed_value < 82:
                fg_color = QColor("#ffaa00")  # Ámbar caliente
            else:
                fg_color = QColor("#ff3366")  # Rojo crítico
        else:
            fg_color = self.accent_color

        # Gradiente en el arco
        glow_pen = QPen(QColor(fg_color.red(), fg_color.green(), fg_color.blue(), 60), 16,
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(glow_pen)
        painter.drawArc(rect, int(start_angle * 16), int(active_span * 16))

        active_pen = QPen(fg_color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(active_pen)
        painter.drawArc(rect, int(start_angle * 16), int(active_span * 16))

        # 3. Punto indicador en la punta del arco
        if active_span != 0:
            current_angle_deg = start_angle + active_span
            rad = math.radians(-current_angle_deg)
            dot_x = center_x + radius * math.cos(rad)
            dot_y = center_y + radius * math.sin(rad)
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.setPen(QPen(fg_color, 2))
            painter.drawEllipse(QRectF(dot_x - 5, dot_y - 5, 10, 10))

        # 4. Textos centrales
        # Valor principal
        val_str = f"{int(round(self._displayed_value))}" if self.max_val > 150 else f"{self._displayed_value:.1f}"
        if self.unit == "RPM":
            val_str = f"{int(round(self._displayed_value))}"

        if not self._available:
            val_str = "N/D"

        painter.setPen(QColor("#f0f6fc"))
        font_val = QFont("JetBrains Mono")
        font_val.setStyleHint(QFont.StyleHint.Monospace)
        font_val.setPixelSize(int(size * 0.17))
        font_val.setBold(True)
        painter.setFont(font_val)

        val_rect = QRectF(center_x - radius, center_y - radius * 0.45, radius * 2, radius * 0.6)
        painter.drawText(val_rect, Qt.AlignmentFlag.AlignCenter, val_str)

        # Unidad
        font_unit = QFont(self.font())
        font_unit.setPixelSize(int(size * 0.08))
        font_unit.setBold(False)
        painter.setFont(font_unit)
        painter.setPen(fg_color)
        unit_rect = QRectF(center_x - radius, center_y + radius * 0.05, radius * 2, radius * 0.3)
        painter.drawText(unit_rect, Qt.AlignmentFlag.AlignCenter, self.unit)

        # Título inferior
        font_title = QFont(self.font())
        font_title.setPixelSize(int(size * 0.075))
        font_title.setBold(True)
        painter.setFont(font_title)
        painter.setPen(QColor("#8b949e"))
        title_rect = QRectF(center_x - radius, center_y + radius * 0.38, radius * 2, radius * 0.3)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self.title.upper())

        painter.end()

