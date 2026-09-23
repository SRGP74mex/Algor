"""Diálogo modal de ajuste rápido para un ventilador o bomba específica."""
import time
from typing import Optional
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QSlider, QMessageBox)
from algor.core.config import config
from algor.core.fan_mapping import normalize_mapping, ROLES
from algor.core.hardware import TelemetryData, HardwareWorker
from algor.core.i18n import _
from algor.core.pwm_writer import percent_to_raw, raw_to_percent
from algor.ui.theme import Theme


class FanQuickControlDialog(QDialog):
    """Ajuste rápido de velocidad y modo para un ventilador individual."""

    def __init__(self, sensor_id: str, data: Optional[TelemetryData],
                 worker: Optional[HardwareWorker] = None, parent=None):
        super().__init__(parent)
        self.sensor_id = sensor_id
        self._data = data
        self.worker = worker
        self.is_pump = False
        self.fan_name = ""
        self.fan_identity = ""
        self.pwm_identity: Optional[str] = None
        self.pwm_channel_dict: Optional[dict] = None

        self._resolve_channel_info()
        self._init_ui()

        # Timer para actualizar RPM en vivo mientras el diálogo esté abierto
        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self._refresh_live_status)
        self.timer.start()

    def _resolve_channel_info(self):
        """Identifica el componente, su canal PWM correspondiente y si es la bomba."""
        mappings = config.get("fan_mappings", {})

        if self.sensor_id == "pump_rpm":
            self.is_pump = True
            self.fan_name = _("💧 Bomba Líquida AIO")
            return

        if self.sensor_id.startswith("fan_channel::"):
            identity = self.sensor_id.split("::", 1)[1]
            self.fan_identity = identity
            raw_map = mappings.get(identity, {})
            norm = normalize_mapping(raw_map)
            self.fan_name = norm["name"] or ROLES.get(norm["role"], identity)
            if norm["role"] == "pump":
                self.is_pump = True
                return
            if norm.get("pwm_channel"):
                self.pwm_identity = norm["pwm_channel"]

        elif self.sensor_id.startswith("fan_rpm::"):
            key = self.sensor_id.split("::", 1)[1]  # ej: it8620_fan2
            self.fan_name = _("Ventilador {name}").format(name=key.replace("_", " ").upper())
            # Buscar mapping si existe
            for ident, raw_map in mappings.items():
                if ident.endswith(key.split("_")[-1]):
                    norm = normalize_mapping(raw_map)
                    if norm["role"] == "pump":
                        self.is_pump = True
                        return
                    if norm.get("pwm_channel"):
                        self.pwm_identity = norm["pwm_channel"]
                        break

        elif self.sensor_id.startswith("fan_pwm::"):
            key = self.sensor_id.split("::", 1)[1]  # ej: it8792_pwm2
            self.fan_name = _("Canal PWM {name}").format(name=key.replace("_", " ").upper())

        # Si no se encontró pwm_identity por mapeo, intentar resolver por chip y pwm_channels
        if not self.pwm_identity and self._data and self._data.pwm_channels:
            # Buscar si el sensor_id coincide o comparte chip
            for p_id, p_info in self._data.pwm_channels.items():
                if self.sensor_id.endswith(p_id.split("/")[-1]):
                    self.pwm_identity = p_id
                    self.pwm_channel_dict = p_info
                    break

        if self.pwm_identity and self._data and self._data.pwm_channels:
            self.pwm_channel_dict = self._data.pwm_channels.get(self.pwm_identity)

        # Si aún no tiene pwm_channel_dict pero hay pwm_channels, buscar candidato en el mismo chip
        if not self.pwm_channel_dict and self._data and self._data.pwm_channels:
            chip = None
            if "it8792" in self.sensor_id.lower() or "it8792" in self.fan_identity.lower():
                chip = "it8792"
            elif "it8620" in self.sensor_id.lower() or "it8620" in self.fan_identity.lower():
                chip = "it8620"
            if chip:
                for p_id, p_info in self._data.pwm_channels.items():
                    if chip in p_id:
                        self.pwm_identity = p_id
                        self.pwm_channel_dict = p_info
                        break

        if not self.fan_name:
            self.fan_name = _("Ventilador {id}").format(id=self.sensor_id)

    def _init_ui(self):
        self.setWindowTitle(_("Ajuste Rápido: {name}").format(name=self.fan_name))
        self.setMinimumWidth(460)
        self.setStyleSheet("""
            QDialog { background-color: #0d1117; color: #f0f6fc; }
            QLabel { color: #f0f6fc; }
            QFrame#Card { background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; }
            QPushButton { background-color: #21262d; color: #f0f6fc; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; font-weight: 500; }
            QPushButton:hover { background-color: #30363d; border-color: #8b949e; }
            QPushButton#PrimaryBtn { background-color: #238636; border-color: #2ea043; color: #ffffff; }
            QPushButton#PrimaryBtn:hover { background-color: #2ea043; }
            QPushButton#DangerBtn { background-color: #da3633; border-color: #f85149; color: #ffffff; }
            QPushButton#DangerBtn:hover { background-color: #f85149; }
            QSlider::groove:horizontal { height: 6px; background: #21262d; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #00f0ff; border-radius: 3px; }
            QSlider::handle:horizontal { background: #ffffff; border: 1px solid #00f0ff; width: 16px; margin: -5px 0; border-radius: 8px; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        # 1. Cabecera con Nombre y Estado en Vivo
        header_card = QFrame()
        header_card.setObjectName("Card")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(6)

        title_lbl = QLabel(f"🌀 {self.fan_name}")
        title_lbl.setStyleSheet(f"font-size: {Theme.pt(2)}pt; font-weight: bold; color: #00f0ff;")
        header_layout.addWidget(title_lbl)

        self.lbl_rpm = QLabel(_("Velocidad: Consultando RPM..."))
        self.lbl_rpm.setStyleSheet(f"font-size: {Theme.pt(0)}pt; font-weight: 600; color: #ffffff;")
        header_layout.addWidget(self.lbl_rpm)

        if self.pwm_identity:
            lbl_hw = QLabel(_("Canal PWM físico: {identity}").format(identity=self.pwm_identity))
            lbl_hw.setStyleSheet(f"font-size: {Theme.pt(-2)}pt; color: #8b949e;")
            header_layout.addWidget(lbl_hw)

        layout.addWidget(header_card)

        # 2. Si es la bomba AIO, mostrar protección y salir
        if self.is_pump:
            pump_warn = QLabel(_(
                "💧 **Protección Térmica de Bomba AIO**\n\n"
                "La bomba Corsair Nautilus / AIO opera por diseño a velocidad constante (~2,300 RPM) "
                "para garantizar la circulación continua del líquido refrigerante.\n\n"
                "Algor protege la bomba contra modificaciones manuales o reducciones de velocidad "
                "para evitar daños térmicos al procesador."
            ))
            pump_warn.setWordWrap(True)
            pump_warn.setStyleSheet("background-color: #122822; color: #10b981; border: 1px solid #1c4b38; "
                                    f"border-radius: 8px; padding: 12px; font-size: {Theme.pt(-1)}pt;")
            layout.addWidget(pump_warn)

            btn_close = QPushButton(_("Entendido / Cerrar"))
            btn_close.setObjectName("PrimaryBtn")
            btn_close.clicked.connect(self.accept)
            layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
            self._refresh_live_status()
            return

        # 3. Controles Rápidos de Velocidad
        ctrl_card = QFrame()
        ctrl_card.setObjectName("Card")
        ctrl_vbox = QVBoxLayout(ctrl_card)
        ctrl_vbox.setContentsMargins(14, 14, 14, 14)
        ctrl_vbox.setSpacing(12)

        ctrl_title = QLabel(_("⚙️ Modos y Ajustes Rápidos"))
        ctrl_title.setStyleSheet(f"font-weight: bold; font-size: {Theme.pt(0)}pt; color: #c9d1d9;")
        ctrl_vbox.addWidget(ctrl_title)

        # Fila de Presets Rápidos
        preset_layout = QHBoxLayout()
        preset_layout.setSpacing(8)

        btn_100 = QPushButton("⚡ 100% (255)")
        btn_100.setToolTip(_("Carga máxima de ventilación (255 raw)"))
        btn_100.clicked.connect(lambda: self._apply_percentage(100))
        preset_layout.addWidget(btn_100)

        btn_50 = QPushButton("⚖️ 50% (~128)")
        btn_50.setToolTip(_("Velocidad media balanceada (~128 raw)"))
        btn_50.clicked.connect(lambda: self._apply_percentage(50))
        preset_layout.addWidget(btn_50)

        btn_min = QPushButton("🤫 Mínimo (27%)")
        btn_min.setToolTip(_("Piso mínimo seguro de reposo (~70 raw / 27%)"))
        btn_min.clicked.connect(lambda: self._apply_percentage(27))
        preset_layout.addWidget(btn_min)

        ctrl_vbox.addLayout(preset_layout)

        # Control Deslizante Manual
        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel(_("Manual:")))

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(27, 100)
        self.slider.setValue(50)
        self.slider.valueChanged.connect(self._on_slider_changed)
        slider_row.addWidget(self.slider)

        self.lbl_slider_val = QLabel("50%")
        self.lbl_slider_val.setStyleSheet("font-weight: bold; color: #00f0ff; min-width: 45px;")
        slider_row.addWidget(self.lbl_slider_val)

        btn_apply_slider = QPushButton(_("Aplicar"))
        btn_apply_slider.setObjectName("PrimaryBtn")
        btn_apply_slider.clicked.connect(lambda: self._apply_percentage(self.slider.value()))
        slider_row.addWidget(btn_apply_slider)

        ctrl_vbox.addLayout(slider_row)

        # Botón de Restablecer a Automático (BIOS)
        btn_auto = QPushButton(_("🔄 Restablecer a Automático (Control BIOS)"))
        btn_auto.setStyleSheet("background-color: #1f6feb; border-color: #388bfd; color: #ffffff; font-weight: bold; padding: 8px;")
        btn_auto.clicked.connect(self._restore_auto)
        ctrl_vbox.addWidget(btn_auto)

        layout.addWidget(ctrl_card)

        # 4. Estado de Aplicación y Botón de Cierre
        self.lbl_status_msg = QLabel("")
        self.lbl_status_msg.setWordWrap(True)
        self.lbl_status_msg.setStyleSheet(f"font-size: {Theme.pt(-2)}pt; color: #8b949e;")
        layout.addWidget(self.lbl_status_msg)

        btn_close = QPushButton(_("Cerrar"))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        self._refresh_live_status()

    def _on_slider_changed(self, val: int):
        self.lbl_slider_val.setText(f"{val}%")

    def _refresh_live_status(self):
        """Lee el valor RPM en tiempo real."""
        if not self.worker or not self.worker.sampler:
            return
        data = self.worker.sampler.sample(self.worker.corsair_reader)

        rpm = None
        if self.sensor_id == "pump_rpm":
            from algor.core.fan_mapping import apply_pump_mapping
            apply_pump_mapping(data, config.get("fan_mappings", {}))
            rpm = data.pump_rpm if data.pump_rpm_available else None
        elif self.sensor_id.startswith("fan_channel::"):
            ident = self.sensor_id.split("::", 1)[1]
            rpm = data.fan_channels.get(ident, {}).get("rpm")
        elif self.sensor_id.startswith("fan_rpm::"):
            key = self.sensor_id.split("::", 1)[1]
            rpm = data.fans_rpm.get(key)

        if rpm is not None and rpm > 0:
            self.lbl_rpm.setText(_("Velocidad en vivo: {rpm} RPM").format(rpm=rpm))
        else:
            self.lbl_rpm.setText(_("Velocidad en vivo: {status}").format(
                status=f"{rpm} RPM" if rpm == 0 else _("N/D")))

    def _apply_percentage(self, percent: int):
        """Aplica el porcentaje de PWM al canal físico."""
        if not self.pwm_identity or not self.pwm_channel_dict:
            # Buscar canales disponibles
            if self.worker and self.worker.sampler:
                chans = self.worker.sampler.scan_pwm_channels()
                if chans:
                    self.pwm_identity = list(chans.keys())[0]
                    self.pwm_channel_dict = chans[self.pwm_identity]

        if not self.pwm_identity or not self.pwm_channel_dict:
            QMessageBox.warning(
                self, _("Sin canal PWM"),
                _("No se detectó un archivo de escritura PWM compatible para este ventilador.\n"
                  "Verifica los permisos PWM en Ajustes.")
            )
            return

        raw = percent_to_raw(percent)
        success = False
        if self.worker:
            success = self.worker.request_channel_manual_pwm(
                self.pwm_identity, percent, enforce_floor=False
            )

        if success:
            self.lbl_status_msg.setText(
                _("✅ PWM fijado en {pct}% (raw: {raw}/255) en {channel}.").format(
                    pct=percent, raw=raw, channel=self.pwm_identity.split("/")[-1]
                )
            )
            self.lbl_status_msg.setStyleSheet(f"font-size: {Theme.pt(-2)}pt; color: #00e676;")
        else:
            self.lbl_status_msg.setText(
                _("⚠️ No se pudo escribir en el canal {channel}. Revisa los permisos de Ajustes.").format(
                    channel=self.pwm_identity
                )
            )
            self.lbl_status_msg.setStyleSheet(f"font-size: {Theme.pt(-2)}pt; color: #ffaa00;")

    def _restore_auto(self):
        """Devuelve el canal a Automático (BIOS)."""
        if not self.pwm_identity:
            if self.worker:
                self.worker.request_restore_all_auto()
                self.lbl_status_msg.setText(_("✅ Todos los canales restablecidos a Automático (BIOS)."))
                self.lbl_status_msg.setStyleSheet(f"font-size: {Theme.pt(-2)}pt; color: #00e676;")
                return
            return

        success = False
        if self.worker:
            success = self.worker.request_channel_auto(self.pwm_identity)

        if success:
            self.lbl_status_msg.setText(
                _("✅ Canal {channel} devuelto al control Automático de la BIOS.").format(
                    channel=self.pwm_identity.split("/")[-1]
                )
            )
            self.lbl_status_msg.setStyleSheet(f"font-size: {Theme.pt(-2)}pt; color: #00e676;")
        else:
            self.lbl_status_msg.setText(
                _("⚠️ No se pudo restablecer el canal {channel}.").format(channel=self.pwm_identity)
            )
            self.lbl_status_msg.setStyleSheet(f"font-size: {Theme.pt(-2)}pt; color: #ffaa00;")

