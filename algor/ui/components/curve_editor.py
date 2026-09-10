import math
from typing import Dict, List, Optional
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import (QPainter, QColor, QPen, QBrush, QFont, QPainterPath,
                         QLinearGradient, QMouseEvent)
from PyQt6.QtWidgets import QWidget


class CurveEditor(QWidget):
    """
    Editor visual interactivo de curvas de temperatura vs % PWM.
    Permite arrastrar puntos, visualizar la curva en tiempo real e indica el punto de operación actual.
    """
    curve_changed = pyqtSignal(list)

    def __init__(self, points: Optional[List[Dict[str, int]]] = None, parent=None):
        super().__init__(parent)
        self.setMinimumSize(450, 260)
        self.setMouseTracking(True)
        
        # Rango de ejes
        self.min_temp = 20.0
        self.max_temp = 90.0
        self.min_pwm = 0.0
        self.max_pwm = 100.0
        
        # Márgenes para etiquetas
        self.margin_left = 48
        self.margin_right = 24
        self.margin_top = 20
        self.margin_bottom = 36

        # Puntos de la curva [{'temp': 20, 'pwm': 30}, ...]
        self.points: List[Dict[str, int]] = points if points else [
            {"temp": 20, "pwm": 30},
            {"temp": 40, "pwm": 40},
            {"temp": 60, "pwm": 65},
            {"temp": 75, "pwm": 85},
            {"temp": 85, "pwm": 100}
        ]

        # Estado del ratón
        self._hovered_idx: Optional[int] = None
        self._dragging_idx: Optional[int] = None
        self.node_radius = 8

        # Telemetría en tiempo real
        self._current_live_temp = 32.0
        self._current_live_pwm = 35
        self._response_status = None

    def set_points(self, points: List[Dict[str, int]]):
        self.points = sorted(points, key=lambda x: x["temp"])
        self.update()

    def get_points(self) -> List[Dict[str, int]]:
        return self.points

    def set_live_telemetry(self, current_temp: float, current_pwm: int):
        self._current_live_temp = current_temp
        self._current_live_pwm = current_pwm
        self.update()

    def set_response_status(self, status) -> None:
        self._response_status = status
        self.update()

    # Conversión de coordenadas de datos a píxeles
    def _data_to_pixel(self, temp: float, pwm: float) -> QPointF:
        plot_w = self.width() - self.margin_left - self.margin_right
        plot_h = self.height() - self.margin_top - self.margin_bottom
        
        t_ratio = (temp - self.min_temp) / (self.max_temp - self.min_temp)
        p_ratio = (pwm - self.min_pwm) / (self.max_pwm - self.min_pwm)
        
        px = self.margin_left + t_ratio * plot_w
        py = self.margin_top + (1.0 - p_ratio) * plot_h
        return QPointF(px, py)

    # Conversión de píxeles a coordenadas de datos
    def _pixel_to_data(self, px: float, py: float) -> (float, float):
        plot_w = self.width() - self.margin_left - self.margin_right
        plot_h = self.height() - self.margin_top - self.margin_bottom
        
        t_ratio = (px - self.margin_left) / max(1.0, plot_w)
        p_ratio = 1.0 - ((py - self.margin_top) / max(1.0, plot_h))
        
        temp = self.min_temp + t_ratio * (self.max_temp - self.min_temp)
        pwm = self.min_pwm + p_ratio * (self.max_pwm - self.min_pwm)
        
        return max(self.min_temp, min(self.max_temp, temp)), max(self.min_pwm, min(self.max_pwm, pwm))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        plot_w = w - self.margin_left - self.margin_right
        plot_h = h - self.margin_top - self.margin_bottom

        # 1. Fondo de la cuadrícula
        plot_rect = QRectF(self.margin_left, self.margin_top, plot_w, plot_h)
        painter.fillRect(plot_rect, QColor("#121722"))
        painter.setPen(QPen(QColor("#243044"), 1))
        painter.drawRect(plot_rect)

        # 2. Líneas de cuadrícula (Grid Lines)
        grid_pen = QPen(QColor("#1b2538"), 1, Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        
        # Grid horizontal (PWM %)
        font_axis = QFont(self.font())
        font_axis.setPixelSize(10)
        painter.setFont(font_axis)
        
        for pwm_val in range(0, 101, 20):
            p = self._data_to_pixel(self.min_temp, pwm_val)
            painter.drawLine(QPointF(self.margin_left, p.y()), QPointF(w - self.margin_right, p.y()))
            
            # Etiqueta Y
            painter.setPen(QColor("#6e7681"))
            painter.drawText(QRectF(0, p.y() - 8, self.margin_left - 8, 16),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{pwm_val}%")
            painter.setPen(grid_pen)

        # Grid vertical (Temp °C)
        for temp_val in range(20, 91, 10):
            p = self._data_to_pixel(temp_val, self.min_pwm)
            painter.drawLine(QPointF(p.x(), self.margin_top), QPointF(p.x(), h - self.margin_bottom))
            
            # Etiqueta X
            painter.setPen(QColor("#6e7681"))
            painter.drawText(QRectF(p.x() - 20, h - self.margin_bottom + 6, 40, 20),
                             Qt.AlignmentFlag.AlignCenter, f"{temp_val}°C")
            painter.setPen(grid_pen)

        # 3. Dibujar la curva y el relleno con gradiente
        if self.points:
            sorted_pts = sorted(self.points, key=lambda x: x["temp"])
            pixel_pts = [self._data_to_pixel(pt["temp"], pt["pwm"]) for pt in sorted_pts]

            # Construir Path para curva
            path = QPainterPath()
            path.moveTo(pixel_pts[0])
            for i in range(1, len(pixel_pts)):
                path.lineTo(pixel_pts[i])

            # Relleno inferior translúcido
            fill_path = QPainterPath(path)
            fill_path.lineTo(pixel_pts[-1].x(), self.margin_top + plot_h)
            fill_path.lineTo(pixel_pts[0].x(), self.margin_top + plot_h)
            fill_path.closeSubpath()

            grad = QLinearGradient(0, self.margin_top, 0, self.margin_top + plot_h)
            grad.setColorAt(0.0, QColor(0, 240, 255, 70))
            grad.setColorAt(1.0, QColor(0, 180, 255, 5))
            painter.fillPath(fill_path, QBrush(grad))

            # Resplandor de la curva
            glow_pen = QPen(QColor(0, 240, 255, 80), 6)
            painter.setPen(glow_pen)
            painter.drawPath(path)

            # Línea principal
            line_pen = QPen(QColor("#00f0ff"), 2.5)
            painter.setPen(line_pen)
            painter.drawPath(path)

            # 4. Indicador de Telemetría en Vivo (Línea y punto actual)
            if self.min_temp <= self._current_live_temp <= self.max_temp:
                live_pt = self._data_to_pixel(self._current_live_temp, self._current_live_pwm)

                # Color según si hay evidencia de que algo (BIOS/app) responde al
                # calor real; solo lectura, nunca implica escritura de PWM.
                from algor.core.thermal_response import NOT_RESPONDING
                not_responding = bool(self._response_status) and self._response_status.state == NOT_RESPONDING
                live_color = "#ffbd69" if not_responding else "#00e676"
                live_halo = QColor(255, 189, 105, 90) if not_responding else QColor(0, 230, 118, 90)

                # Línea vertical de temperatura actual
                live_pen = QPen(QColor(live_color), 1.5, Qt.PenStyle.DashLine)
                painter.setPen(live_pen)
                painter.drawLine(QPointF(live_pt.x(), self.margin_top),
                                 QPointF(live_pt.x(), self.margin_top + plot_h))

                # Punto de operación activo, con halo verde o ámbar según la
                # respuesta térmica observada
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(live_halo))
                painter.drawEllipse(live_pt, 12, 12)
                painter.setBrush(QBrush(QColor(live_color)))
                painter.drawEllipse(live_pt, 5, 5)

            # 5. Puntos de control interactivos
            for i, p in enumerate(pixel_pts):
                is_hovered = (i == self._hovered_idx or i == self._dragging_idx)
                
                # Halo al pasar el mouse
                if is_hovered:
                    painter.setBrush(QBrush(QColor(0, 240, 255, 80)))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(p, self.node_radius + 6, self.node_radius + 6)

                # Nodo principal
                painter.setBrush(QBrush(QColor("#ffffff") if is_hovered else QColor("#00f0ff")))
                painter.setPen(QPen(QColor("#0d1117"), 2))
                painter.drawEllipse(p, self.node_radius, self.node_radius)

                # Tooltip con valores numéricos flotantes
                if is_hovered:
                    pt_data = sorted_pts[i]
                    tag_text = f"{pt_data['temp']}°C : {pt_data['pwm']}%"
                    painter.setFont(font_axis)
                    painter.setPen(QColor("#0d1117"))
                    tag_rect = QRectF(p.x() - 35, p.y() - 28, 70, 20)
                    painter.setBrush(QBrush(QColor("#00f0ff")))
                    painter.drawRoundedRect(tag_rect, 4, 4)
                    painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag_text)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            for i, pt in enumerate(self.points):
                p = self._data_to_pixel(pt["temp"], pt["pwm"])
                dist = math.hypot(pos.x() - p.x(), pos.y() - p.y())
                if dist <= self.node_radius + 4:
                    self._dragging_idx = i
                    self.update()
                    return

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        if self._dragging_idx is not None:
            temp, pwm = self._pixel_to_data(pos.x(), pos.y())
            # Restricciones para los extremos
            if self._dragging_idx == 0:
                temp = self.min_temp
            elif self._dragging_idx == len(self.points) - 1:
                temp = self.max_temp

            self.points[self._dragging_idx]["temp"] = int(round(temp))
            self.points[self._dragging_idx]["pwm"] = int(round(pwm))
            self.points = sorted(self.points, key=lambda x: x["temp"])
            # Reubicar índice del punto arrastrado tras ordenar
            for idx, pt in enumerate(self.points):
                if pt["temp"] == int(round(temp)) and pt["pwm"] == int(round(pwm)):
                    self._dragging_idx = idx
                    break

            # curve_changed se emite solo al soltar el mouse (mouseReleaseEvent), no aquí:
            # emitirlo en cada movimiento disparaba un guardado a disco (JSON completo)
            # por cada pixel arrastrado — decenas de escrituras por segundo mientras
            # mueves un punto. El arrastre se sigue viendo en vivo (self.update() abajo).
            self.update()
        else:
            # Detectar hover
            old_hover = self._hovered_idx
            self._hovered_idx = None
            for i, pt in enumerate(self.points):
                p = self._data_to_pixel(pt["temp"], pt["pwm"])
                dist = math.hypot(pos.x() - p.x(), pos.y() - p.y())
                if dist <= self.node_radius + 4:
                    self._hovered_idx = i
                    break
            if old_hover != self._hovered_idx:
                self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging_idx is not None:
                self.curve_changed.emit(self.points)
            self._dragging_idx = None
            self.update()

