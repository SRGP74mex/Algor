from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QGridLayout)
from algor.core.hardware import TelemetryData
from algor.core.config import config
from algor.core.i18n import _
from algor.core.sensors import get_sensor_map
from algor.ui.components.circular_gauge import CircularGauge
from algor.ui.components.live_chart import LiveChart
from algor.ui.components.customize_dashboard_dialog import CustomizeDashboardDialog
from algor.ui.views.fan_quick_control_dialog import FanQuickControlDialog
from algor.ui.theme import Theme

GAUGE_ACCENT_CYCLE = [
    Theme.CYAN, Theme.PURPLE, Theme.EMERALD, Theme.AMBER,
    Theme.BLUE, Theme.CORAL, Theme.INDIGO_LIGHT,
]

# Ancho de referencia (gauge + espaciado) usado para calcular cuántas columnas
# caben por fila según el ancho real disponible, en vez de un número fijo.
GAUGE_TARGET_WIDTH = 190


class DashboardView(QWidget):
    """Vista principal con medidores HD, gráficas en tiempo real y perfiles rápidos."""
    profile_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_data: TelemetryData | None = None
        self.worker = None
        self.gauge_widgets: dict[str, CircularGauge] = {}
        self.active_sensor_ids: list[str] = []
        self._gauges_synced_with_data = False
        self._empty_placeholder: QLabel | None = None
        self._init_ui()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        available = self.gauges_frame.width() - 24  # márgenes internos de la tarjeta
        columns = max(1, available // GAUGE_TARGET_WIDTH)
        if columns != self.gauges_columns:
            self.gauges_columns = columns
            self._relayout_grid()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(14)

        # 1. Cuadrícula de Medidores Circulares HD (contenido generado dinámicamente).
        # Usa QGridLayout en vez de una fila horizontal única para que, al activar
        # varios sensores desde "Personalizar Panel", se acomoden en varias filas
        # en lugar de comprimirse o desbordar la ventana.
        self.gauges_frame = QFrame()
        self.gauges_frame.setObjectName("Card")
        self.gauges_layout = QGridLayout(self.gauges_frame)
        self.gauges_layout.setContentsMargins(12, 12, 12, 12)
        self.gauges_layout.setSpacing(8)
        self.gauges_columns = 4

        header_row = QHBoxLayout()
        header_row.addStretch()
        btn_customize = QPushButton(_("🧩 Personalizar Panel"))
        btn_customize.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_customize.clicked.connect(self._open_customize_dialog)
        header_row.addWidget(btn_customize)
        main_layout.addLayout(header_row)

        self._rebuild_gauges(config.get("dashboard_sensors", []))
        main_layout.addWidget(self.gauges_frame)

        # 2. Barra de Perfiles Rápidos Segmentada estilo Custos
        profile_bar = QFrame()
        profile_bar.setObjectName("SegmentedContainer")
        profile_layout = QHBoxLayout(profile_bar)
        profile_layout.setContentsMargins(4, 4, 4, 4)
        profile_layout.setSpacing(6)

        self.profile_buttons = {}
        profiles = [
            ("silent", _("🤫 Silencioso")),
            ("balanced", _("⚖️ Equilibrado")),
            ("extreme", _("🚀 Extremo")),
            ("custom", _("⚙️ Personalizado"))
        ]

        active_prof = config.get("active_profile", "balanced")
        for key, text in profiles:
            btn = QPushButton(text)
            btn.setCheckable(True)
            if key == active_prof:
                btn.setChecked(True)
                btn.setObjectName("PillActive")
            else:
                btn.setChecked(False)
                btn.setObjectName("PillInactive")
            btn.clicked.connect(lambda checked, k=key: self._on_profile_click(k))
            self.profile_buttons[key] = btn
            profile_layout.addWidget(btn)

        main_layout.addWidget(profile_bar)

        # 3. Gráfica en tiempo real & Resumen de hardware
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(14)

        # Tarjeta de la Gráfica
        chart_card = QFrame()
        chart_card.setObjectName("Card")
        chart_vbox = QVBoxLayout(chart_card)
        chart_vbox.setContentsMargins(12, 12, 12, 12)

        chart_title = QLabel(_("📈 Telemetría Térmica en Vivo"))
        chart_title.setStyleSheet(f"font-weight: bold; color: #c9d1d9; font-size: {Theme.pt(1)}pt;")
        chart_vbox.addWidget(chart_title)

        self.live_chart = LiveChart(max_samples=60)
        chart_vbox.addWidget(self.live_chart)
        bottom_layout.addWidget(chart_card, stretch=3)

        # Tarjeta de Datos Rápidos del Sistema
        info_card = QFrame()
        info_card.setObjectName("Card")
        info_vbox = QVBoxLayout(info_card)
        info_vbox.setContentsMargins(14, 14, 14, 14)
        info_vbox.setSpacing(10)

        info_title = QLabel(_("💻 Estado del Hardware"))
        info_title.setStyleSheet(f"font-weight: bold; color: #c9d1d9; font-size: {Theme.pt(1)}pt;")
        info_vbox.addWidget(info_title)

        self.lbl_cpu_load = QLabel(_("CPU Uso: -- %"))
        self.lbl_cpu_freq = QLabel(_("CPU Frecuencia: -- MHz"))
        self.lbl_gpu_load = QLabel(_("GPU Uso: -- %"))
        self.lbl_gpu_vram = QLabel(_("VRAM: -- / -- MB"))
        self.lbl_corsair_status = QLabel(_("Algor: Conectado"))

        for lbl in [self.lbl_cpu_load, self.lbl_cpu_freq, self.lbl_gpu_load, self.lbl_gpu_vram, self.lbl_corsair_status]:
            lbl.setStyleSheet(f"color: #8b949e; font-size: {Theme.pt(-1)}pt;")
            info_vbox.addWidget(lbl)

        info_vbox.addStretch()
        bottom_layout.addWidget(info_card, stretch=1)

        main_layout.addLayout(bottom_layout)

    def _on_profile_click(self, profile_key: str):
        for k, btn in self.profile_buttons.items():
            if k == profile_key:
                btn.setChecked(True)
                btn.setObjectName("PillActive")
            else:
                btn.setChecked(False)
                btn.setObjectName("PillInactive")
            # Forzar recarga del estilo en Qt
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self.profile_requested.emit(profile_key)

    def _rebuild_gauges(self, sensor_ids: list[str]) -> None:
        """Recrea los medidores circulares desde cero según los sensores activos.

        Sensores que aún no se puedan resolver (p. ej. discos/fans dinámicos antes
        de que llegue la primera muestra de telemetría) se omiten aquí, pero quedan
        en `active_sensor_ids` — `update_telemetry` reintenta reconstruir en cuanto
        llegan datos reales, para no perderlos silenciosamente (ver `_gauges_synced_with_data`).
        """
        while self.gauges_layout.count():
            item = self.gauges_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # hide()+setParent(None) de inmediato: deleteLater() por sí solo NO
                # saca al widget de la pantalla, solo agenda su destrucción para más
                # tarde — mientras tanto seguiría siendo hijo visible de gauges_frame
                # y podría quedar pintado encima del gauge nuevo que ocupe su mismo
                # lugar en la cuadrícula (así se veían dos sensores distintos
                # superpuestos al agregar/quitar sensores desde "Personalizar Panel").
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        self.gauge_widgets = {}
        self.active_sensor_ids = list(sensor_ids)
        sensor_map = get_sensor_map(self._last_data)

        for i, sensor_id in enumerate(self.active_sensor_ids):
            sensor = sensor_map.get(sensor_id)
            if sensor is None:
                continue
            accent = GAUGE_ACCENT_CYCLE[i % len(GAUGE_ACCENT_CYCLE)]
            gauge = CircularGauge(
                title=sensor.label, unit=sensor.unit,
                min_val=sensor.min_val, max_val=sensor.max_val, accent_color=accent,
                sensor_id=sensor_id,
            )
            gauge.reordered.connect(self._on_gauge_reordered)
            gauge.double_clicked.connect(self._on_gauge_double_clicked)
            self.gauge_widgets[sensor_id] = gauge

        self._relayout_grid()

    def _on_gauge_double_clicked(self, sensor_id: str) -> None:
        """Abre el diálogo de ajuste rápido para ventiladores o bomba."""
        if (sensor_id.startswith("fan_") or sensor_id == "pump_rpm" or "fan" in sensor_id.lower() or "pwm" in sensor_id.lower()):
            dialog = FanQuickControlDialog(sensor_id, self._last_data, worker=self.worker, parent=self)
            dialog.exec()

    def _relayout_grid(self) -> None:
        """Reacomoda los medidores YA CREADOS en la cuadrícula según `gauges_columns`,
        sin recrearlos (evita que la animación/valor de cada gauge se reinicie
        cada vez que cambia el ancho de la ventana)."""
        while self.gauges_layout.count():
            self.gauges_layout.takeAt(0)  # solo los saca del layout, no los destruye

        if not self.gauge_widgets:
            if self._empty_placeholder is None:
                self._empty_placeholder = QLabel(
                    _('Ningún sensor activo. Usa "Personalizar Panel" para agregar medidores.')
                )
                self._empty_placeholder.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: {Theme.pt(-1)}pt;")
                self._empty_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.gauges_layout.addWidget(self._empty_placeholder, 0, 0)
            self._empty_placeholder.show()
            return

        if self._empty_placeholder is not None:
            self._empty_placeholder.hide()

        col = 0
        for sensor_id in self.active_sensor_ids:
            gauge = self.gauge_widgets.get(sensor_id)
            if gauge is None:
                continue
            row, column = divmod(col, self.gauges_columns)
            self.gauges_layout.addWidget(gauge, row, column)
            gauge.show()
            col += 1

    def _on_gauge_reordered(self, dragged_id: str, target_id: str) -> None:
        """Mueve `dragged_id` a la posición de `target_id` tras un arrastre en el
        Panel General y persiste el nuevo orden en `dashboard_sensors`.

        Se reordena la lista lógica de sensores (no coordenadas x,y) porque
        `_relayout_grid` recalcula fila/columna a partir de ella y del número de
        columnas actual, que cambia con el ancho de la ventana.
        """
        if dragged_id not in self.active_sensor_ids or target_id not in self.active_sensor_ids:
            return
        new_ids = list(self.active_sensor_ids)
        new_ids.remove(dragged_id)
        new_ids.insert(new_ids.index(target_id), dragged_id)
        self.active_sensor_ids = new_ids
        config.set("dashboard_sensors", new_ids)
        self._relayout_grid()

    def _open_customize_dialog(self) -> None:
        dialog = CustomizeDashboardDialog(self.active_sensor_ids, self._last_data, parent=self)
        if dialog.exec():
            new_ids = dialog.selected_ids()
            config.set("dashboard_sensors", new_ids)
            self._rebuild_gauges(new_ids)

    def update_telemetry(self, data: TelemetryData):
        self._last_data = data

        # Al arrancar, "Personalizar Panel" pudo haber guardado sensores dinámicos
        # (discos, fans) que no existían todavía en el primer _rebuild_gauges (se
        # ejecuta antes de que llegue ninguna muestra real). En cuanto hay datos,
        # reintentamos una sola vez para no perderlos hasta que el usuario reabra
        # el diálogo y le dé "Aplicar" sin cambiar nada.
        if not self._gauges_synced_with_data:
            self._gauges_synced_with_data = True
            if any(sid not in self.gauge_widgets for sid in self.active_sensor_ids):
                self._rebuild_gauges(self.active_sensor_ids)

        # Actualizar medidores activos
        sensor_map = get_sensor_map(data)
        for sensor_id, gauge in self.gauge_widgets.items():
            sensor = sensor_map.get(sensor_id)
            if sensor is None:
                gauge.set_value(None)
                continue
            if sensor_id.startswith("fan_channel::") and gauge.title != sensor.label:
                gauge.title = sensor.label
                gauge.update()
            value = sensor.getter(data)
            gauge.set_value(value)

            # El líquido AIO sin un canal empírico confirmado es una ESTIMACIÓN
            # o de plano no disponible — que se note en el propio medidor, no solo
            # en un texto aparte que el usuario podría no ver.
            if sensor_id == "liquid_temp":
                new_title = _("LÍQUIDO SIN VERIFICAR") if not data.liquid_temp_available else sensor.label
                if gauge.title != new_title:
                    gauge.title = new_title
                    gauge.update()

        # Actualizar gráfica
        self.live_chart.add_sample(data.cpu_temp_package if data.cpu_temp_available else None, data.gpu_temp if data.gpu_name else None, data.liquid_temp if data.liquid_temp_available else None)

        # Actualizar etiquetas
        self.lbl_cpu_load.setText(_("CPU Uso: {value:.1f}%").format(value=data.cpu_usage_total))
        if data.cpu_freq_mhz > 0:
            self.lbl_cpu_freq.setText(_("CPU Frecuencia: {value:.0f} MHz").format(value=data.cpu_freq_mhz))
        self.lbl_gpu_load.setText(_("GPU Uso: {value:.0f}%").format(value=data.gpu_usage))
        if data.gpu_memory_total_mb > 0:
            self.lbl_gpu_vram.setText(_("VRAM: {used:.0f} / {total:.0f} MB").format(
                used=data.gpu_memory_used_mb, total=data.gpu_memory_total_mb))

        if data.corsair_connected:
            self.lbl_corsair_status.setText(f"🟢 {data.corsair_info}")
            self.lbl_corsair_status.setStyleSheet("color: #00e676; font-weight: bold;")
        else:
            # Antes se descartaba el motivo real (data.corsair_info) y se mostraba
            # siempre el mismo texto genérico, aunque la causa fuera, por ejemplo,
            # falta de permisos USB — dejando al usuario sin ninguna pista.
            reason = data.corsair_info or _("Algor LCD: Detectado (USB)")
            self.lbl_corsair_status.setText(f"🟠 {reason}")
            self.lbl_corsair_status.setStyleSheet("color: #ffaa00;")
