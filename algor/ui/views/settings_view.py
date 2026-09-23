import os
import sys
import subprocess
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QSlider, QCheckBox, QSpinBox, QMessageBox,
                             QFileDialog, QScrollArea)
from algor.core.config import config
from algor.core.fan_mapping import eligible_for_pwm_write
from algor.core.hardware import TelemetryData
from algor.core.i18n import _
from algor.core.pwm_writer import PROTECTION_FLOOR_PERCENT
from algor.core.sensor_logger import SensorLogger
from algor.core.sensors import build_sensor_list
from algor.ui.theme import Theme


class SettingsView(QWidget):
    """Vista de configuración general, permisos udev, alertas y registro de sensores."""
    real_control_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_data: Optional[TelemetryData] = None
        self.worker = None
        self._dynamic_sensors_loaded = False
        self._sensor_checks: dict[str, QCheckBox] = {}
        self.logger = SensorLogger()
        self.logger.on_auto_stop = self._on_logging_auto_stopped
        self._init_ui()

    def _init_ui(self):
        self.setStyleSheet('QSpinBox { background-color: #1c2038; color: #f0f6fc; '
                           'border: 1px solid #414765; border-radius: 4px; padding: 5px; '
                           'min-width: 80px; selection-background-color: #6557ed; }')
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        alert_card = QFrame()
        alert_card.setObjectName('Card')
        alerts = QVBoxLayout(alert_card)
        alerts.addWidget(QLabel(_('Alertas de temperatura y disponibilidad')))
        self.chk_alerts = QCheckBox(_('Activar supervisión y notificaciones'))
        self.chk_alerts.setChecked(config.get('alerts', {}).get('enabled', True))
        self.chk_alerts.toggled.connect(lambda value: self._set_alert_option('enabled', value))
        alerts.addWidget(self.chk_alerts)
        self.alert_spins = {}
        for device, title in [('cpu', 'CPU'), ('gpu', 'GPU')]:
            row = QHBoxLayout()
            row.addWidget(QLabel(title))
            for suffix, label, default in [('warn', _('Aviso'), 80), ('crit', _('Crítica'), 90 if device == 'cpu' else 88)]:
                key = device + '_temp_' + suffix
                row.addWidget(QLabel(label))
                spin = QSpinBox()
                spin.setRange(1, 125)
                spin.setSuffix(' °C')
                spin.setValue(int(config.get('alerts', {}).get(key, default)))
                self.alert_spins[key] = spin
                spin.valueChanged.connect(lambda value, k=key: self._set_alert_option(k, value))
                row.addWidget(spin)
            alerts.addLayout(row)
        note = QLabel(_('Aviso tras 2 s; crítica inmediata; recuperación con margen de 3 °C. '
                      'Pérdidas de sensores/LCD tras 10 s. Ajusta los umbrales a tu equipo. '
                      'Supervisa mientras Algor está abierto, incluso en la bandeja. '
                      'Las alertas RPM se habilitan por canal en Identificar ventiladores.'))
        note.setWordWrap(True)
        alerts.addWidget(note)
        self.lbl_alert_status = QLabel(_('Esperando lecturas…'))
        self.lbl_alert_status.setWordWrap(True)
        alerts.addWidget(self.lbl_alert_status)
        row = QHBoxLayout()
        self.btn_test_alert = QPushButton(_('Probar notificación'))
        row.addWidget(self.btn_test_alert)
        history = QPushButton(_('Abrir historial de eventos'))
        history.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(
            str(Path.home() / '.local/state/algor/events'))))
        row.addWidget(history)
        alerts.addLayout(row)
        self.btn_fan_mapping = QPushButton(_('Identificar bomba y ventiladores…'))
        self.btn_fan_mapping.clicked.connect(self._open_fan_mapping)
        alerts.addWidget(self.btn_fan_mapping)
        layout.addWidget(alert_card)

        # 1. Permisos USB & Hardware
        udev_card = QFrame()
        udev_card.setObjectName("Card")
        udev_vbox = QVBoxLayout(udev_card)
        udev_vbox.setContentsMargins(16, 14, 16, 14)
        udev_vbox.setSpacing(10)

        title_udev = QLabel(_("🔌 Permisos USB del Nautilus LCD Cap"))
        title_udev.setStyleSheet(f"font-weight: bold; font-size: {Theme.pt(1)}pt; color: #f0f6fc;")
        udev_vbox.addWidget(title_udev)

        desc_udev = QLabel(_(
            "Instala una regla de este proyecto para dar a la sesión local activa acceso USB "
            "únicamente al Nautilus LCD Cap (1b1c:0c57). No habilita escrituras PWM ni "
            "cambios de voltaje en la placa base, y no añade soporte de protocolo al LCD. "
            "Después de instalarla, reinicia el equipo para aplicar los permisos."
        ))
        desc_udev.setWordWrap(True)
        desc_udev.setStyleSheet(f"color: #8b949e; font-size: {Theme.pt(-1)}pt;")
        udev_vbox.addWidget(desc_udev)

        btn_udev = QPushButton(_("🛡️ Instalar permisos del LCD Cap"))
        btn_udev.setObjectName("PrimaryBtn")
        btn_udev.clicked.connect(self._install_udev_rule)
        udev_vbox.addWidget(btn_udev, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(udev_card)

        # 1b. Control real de PWM (Reactivo) — experimental
        pwm_card = QFrame()
        pwm_card.setObjectName("Card")
        pwm_vbox = QVBoxLayout(pwm_card)
        pwm_vbox.setContentsMargins(16, 14, 16, 14)
        pwm_vbox.setSpacing(10)

        title_pwm = QLabel(_("🌀 Control real de PWM (Reactivo) — experimental"))
        title_pwm.setStyleSheet(f"font-weight: bold; font-size: {Theme.pt(1)}pt; color: #f0f6fc;")
        pwm_vbox.addWidget(title_pwm)

        desc_pwm = QLabel(_(
            "Aplica de verdad las curvas de Simulación de curvas a los canales que hayas "
            "probado y confirmado en «Identificar bomba y ventiladores». La bomba nunca "
            "queda incluida. Nunca se escribe menos de {floor}%, sin "
            "importar la curva. El permiso de abajo es intencionalmente más amplio que lo "
            "que la app realmente usa — la elegibilidad por canal es la barrera real. "
            "Reactivo nunca se recuerda entre reinicios: cada sesión empieza en Automático."
        ).format(floor=PROTECTION_FLOOR_PERCENT))
        desc_pwm.setWordWrap(True)
        desc_pwm.setStyleSheet(f"color: #8b949e; font-size: {Theme.pt(-1)}pt;")
        pwm_vbox.addWidget(desc_pwm)

        btn_pwm_udev = QPushButton(_("🛡️ Instalar permisos de escritura PWM"))
        btn_pwm_udev.clicked.connect(self._install_pwm_udev_rule)
        pwm_vbox.addWidget(btn_pwm_udev, alignment=Qt.AlignmentFlag.AlignLeft)

        btn_restore_auto = QPushButton(_("🔄 Restablecer todos los ventiladores a Automático (BIOS)"))
        btn_restore_auto.setStyleSheet("background-color: #1f6feb; border-color: #388bfd; color: #ffffff; font-weight: bold; padding: 7px;")
        btn_restore_auto.clicked.connect(self._restore_all_fans_to_auto)
        pwm_vbox.addWidget(btn_restore_auto, alignment=Qt.AlignmentFlag.AlignLeft)

        self.chk_real_control = QCheckBox(_("Activar Reactivo"))
        self.chk_real_control.setChecked(False)
        self.chk_real_control.setEnabled(False)
        self.chk_real_control.toggled.connect(self.real_control_toggled.emit)
        pwm_vbox.addWidget(self.chk_real_control)

        self.lbl_pwm_eligible = QLabel(_("Sin canales verificados todavía."))
        self.lbl_pwm_eligible.setWordWrap(True)
        self.lbl_pwm_eligible.setStyleSheet(f"color: #8b949e; font-size: {Theme.pt(-2)}pt;")
        pwm_vbox.addWidget(self.lbl_pwm_eligible)

        layout.addWidget(pwm_card)

        # 2. Frecuencia de Muestreo de Sensores
        poll_card = QFrame()
        poll_card.setObjectName("Card")
        poll_vbox = QVBoxLayout(poll_card)
        poll_vbox.setContentsMargins(16, 14, 16, 14)
        poll_vbox.setSpacing(10)

        title_poll = QLabel(_("⚡ Rendimiento y Frecuencia de Sensores"))
        title_poll.setStyleSheet(f"font-weight: bold; font-size: {Theme.pt(1)}pt; color: #f0f6fc;")
        poll_vbox.addWidget(title_poll)

        poll_hbox = QHBoxLayout()
        poll_hbox.addWidget(QLabel(_("Intervalo de actualización:")))

        self.slider_poll = QSlider(Qt.Orientation.Horizontal)
        self.slider_poll.setRange(200, 3000)
        self.slider_poll.setSingleStep(100)
        current_poll = config.get("polling_interval_ms", 1000)
        self.slider_poll.setValue(current_poll)
        self.slider_poll.valueChanged.connect(self._on_poll_changed)
        poll_hbox.addWidget(self.slider_poll)

        self.lbl_poll_val = QLabel(f"{current_poll} ms")
        self.lbl_poll_val.setStyleSheet("font-weight: bold; color: #00f0ff; min-width: 60px;")
        poll_hbox.addWidget(self.lbl_poll_val)
        poll_vbox.addLayout(poll_hbox)

        layout.addWidget(poll_card)

        # 2b. Registro de Sensores (Sensor Logging) estilo iCUE
        log_card = QFrame()
        log_card.setObjectName("Card")
        log_vbox = QVBoxLayout(log_card)
        log_vbox.setContentsMargins(16, 14, 16, 14)
        log_vbox.setSpacing(10)

        title_log = QLabel(_("📝 Registro de Sensores (CSV)"))
        title_log.setStyleSheet(f"font-weight: bold; font-size: {Theme.pt(1)}pt; color: #f0f6fc;")
        log_vbox.addWidget(title_log)

        desc_log = QLabel(_("Guarda la telemetría seleccionada en un archivo CSV a intervalos regulares."))
        desc_log.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: {Theme.pt(-1)}pt;")
        log_vbox.addWidget(desc_log)

        # Ubicación
        loc_row = QHBoxLayout()
        loc_row.addWidget(QLabel(_("Ubicación:")))
        log_cfg = config.get("sensor_logging", {})
        default_dir = log_cfg.get("directory") or str(Path.home() / "Documents")
        self.lbl_log_dir = QLabel(default_dir)
        self.lbl_log_dir.setStyleSheet(f"color: {Theme.TEXT_TITLE}; font-size: {Theme.pt(-1)}pt;")
        loc_row.addWidget(self.lbl_log_dir, 1)
        btn_browse = QPushButton(_("📁 Elegir Carpeta..."))
        btn_browse.clicked.connect(self._choose_log_directory)
        loc_row.addWidget(btn_browse)
        log_vbox.addLayout(loc_row)

        # Intervalo de registro
        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel(_("Intervalo (seg):")))
        self.spin_log_interval = QSpinBox()
        self.spin_log_interval.setRange(1, 3600)
        self.spin_log_interval.setValue(int(log_cfg.get("interval_sec", 5)))
        self.spin_log_interval.valueChanged.connect(
            lambda v: self._update_log_cfg("interval_sec", v)
        )
        interval_row.addWidget(self.spin_log_interval)
        interval_row.addStretch()
        log_vbox.addLayout(interval_row)

        # Límite de duración
        duration_row = QHBoxLayout()
        limit_minutes = int(log_cfg.get("limit_minutes", 0))
        self.chk_log_limit = QCheckBox(_("Limitar duración (min):"))
        self.chk_log_limit.setChecked(limit_minutes > 0)
        self.chk_log_limit.toggled.connect(self._on_log_limit_toggled)
        duration_row.addWidget(self.chk_log_limit)
        self.spin_log_duration = QSpinBox()
        self.spin_log_duration.setRange(1, 1440)
        self.spin_log_duration.setValue(limit_minutes if limit_minutes > 0 else 30)
        self.spin_log_duration.setEnabled(limit_minutes > 0)
        self.spin_log_duration.valueChanged.connect(self._on_log_duration_changed)
        duration_row.addWidget(self.spin_log_duration)
        duration_row.addStretch()
        log_vbox.addLayout(duration_row)

        # Selección de sensores
        log_vbox.addWidget(QLabel(_("Seleccionar Sensores:")))
        self.sensors_scroll = QScrollArea()
        self.sensors_scroll.setWidgetResizable(True)
        self.sensors_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sensors_scroll.setMaximumHeight(160)
        self._sensors_content = QWidget()
        self._sensors_layout = QVBoxLayout(self._sensors_content)
        self._sensors_layout.setContentsMargins(4, 2, 4, 2)
        self._sensors_layout.setSpacing(2)
        self.sensors_scroll.setWidget(self._sensors_content)
        log_vbox.addWidget(self.sensors_scroll)
        self._rebuild_sensor_checks()

        # Control de inicio/detención
        self.btn_log_toggle = QPushButton(_("⏺️ Iniciar Registro"))
        self.btn_log_toggle.setObjectName("PrimaryBtn")
        self.btn_log_toggle.clicked.connect(self._toggle_logging)
        log_vbox.addWidget(self.btn_log_toggle, alignment=Qt.AlignmentFlag.AlignLeft)

        self.lbl_log_status = QLabel("")
        self.lbl_log_status.setWordWrap(True)
        self.lbl_log_status.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: {Theme.pt(-2)}pt;")
        log_vbox.addWidget(self.lbl_log_status)

        layout.addWidget(log_card)

        # 2c. Apariencia: tamaño de fuente
        appearance_card = QFrame()
        appearance_card.setObjectName("Card")
        appearance_vbox = QVBoxLayout(appearance_card)
        appearance_vbox.setContentsMargins(16, 14, 16, 14)
        appearance_vbox.setSpacing(10)

        title_appearance = QLabel(_("🔤 Apariencia y Tamaño de Fuente"))
        title_appearance.setStyleSheet(f"font-weight: bold; font-size: {Theme.pt(1)}pt; color: #f0f6fc;")
        appearance_vbox.addWidget(title_appearance)

        desc_appearance = QLabel(_(
            "Si el texto se ve muy pequeño en tu pantalla, desactiva «Automático» y elige "
            "un tamaño manual. El cambio se aplica al reiniciar Algor."
        ))
        desc_appearance.setWordWrap(True)
        desc_appearance.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: {Theme.pt(-1)}pt;")
        appearance_vbox.addWidget(desc_appearance)

        font_row = QHBoxLayout()
        current_font_pt = config.get("ui_font_point_size")
        self.chk_font_auto = QCheckBox(_("Automático (usar el tamaño del sistema)"))
        self.chk_font_auto.setChecked(current_font_pt is None)
        font_row.addWidget(self.chk_font_auto)

        self.spin_font_size = QSpinBox()
        self.spin_font_size.setRange(7, 32)
        self.spin_font_size.setSuffix(" pt")
        self.spin_font_size.setValue(current_font_pt if current_font_pt else Theme.base_pt())
        self.spin_font_size.setEnabled(current_font_pt is not None)
        font_row.addWidget(self.spin_font_size)
        font_row.addStretch()
        appearance_vbox.addLayout(font_row)
        self.chk_font_auto.toggled.connect(self._on_font_auto_toggled)
        self.spin_font_size.valueChanged.connect(self._on_font_size_changed)

        self.lbl_font_restart_note = QLabel("")
        self.lbl_font_restart_note.setWordWrap(True)
        self.lbl_font_restart_note.setStyleSheet(f"color: #ffaa00; font-size: {Theme.pt(-2)}pt;")
        appearance_vbox.addWidget(self.lbl_font_restart_note)

        layout.addWidget(appearance_card)

        # 3. Opciones de Sistema y Bandeja
        sys_card = QFrame()
        sys_card.setObjectName("Card")
        sys_vbox = QVBoxLayout(sys_card)
        sys_vbox.setContentsMargins(16, 14, 16, 14)
        sys_vbox.setSpacing(10)

        title_sys = QLabel(_("🖥️ Integración con el Sistema"))
        title_sys.setStyleSheet(f"font-weight: bold; font-size: {Theme.pt(1)}pt; color: #f0f6fc;")
        sys_vbox.addWidget(title_sys)

        self.chk_tray = QCheckBox(_("Minimizar a la bandeja del sistema (System Tray)"))
        self.chk_tray.setChecked(config.get("minimize_to_tray", True))
        self.chk_tray.toggled.connect(lambda v: config.set("minimize_to_tray", v))
        sys_vbox.addWidget(self.chk_tray)

        self.chk_autostart = QCheckBox(_("Iniciar automáticamente al iniciar sesión en Linux"))
        self.chk_autostart.setChecked(config.get("autostart", False))
        self.chk_autostart.toggled.connect(self._toggle_autostart)
        sys_vbox.addWidget(self.chk_autostart)
        boot_note = QLabel(_('Para recuperar el LCD al iniciar sesión, activa también '
                           '«Iniciar el LCD al abrir Algor» en Pantalla LCD Cap. '
                           'La reconexión recupera contenido y brillo; no repite guardados en memoria.'))
        boot_note.setWordWrap(True)
        sys_vbox.addWidget(boot_note)
        boot_test = QPushButton(_('Cómo comprobar el arranque autónomo'))
        boot_test.clicked.connect(self._show_boot_test)
        sys_vbox.addWidget(boot_test)


        layout.addWidget(sys_card)
        layout.addStretch()

    def _open_fan_mapping(self):
        from algor.ui.views.fan_mapping_dialog import FanMappingDialog
        if not hasattr(self, 'fan_mapping_dialog'):
            self.fan_mapping_dialog = FanMappingDialog(self)
            self.fan_mapping_dialog.mappings_changed.connect(self._rebuild_sensor_checks)
        self.fan_mapping_dialog.feed(self._last_data)
        self.fan_mapping_dialog.show()
        self.fan_mapping_dialog.raise_()
        self.fan_mapping_dialog.activateWindow()

    def _set_alert_option(self, key, value):
        cfg = dict(config.get('alerts', {}))
        cfg[key] = value
        if key.endswith(('_warn', '_crit')):
            prefix = key.rsplit('_', 1)[0]
            warn, crit = prefix + '_warn', prefix + '_crit'
            if cfg.get(warn, 80) >= cfg.get(crit, 90):
                if key == warn:
                    cfg[warn] = min(value, 124)
                    cfg[crit] = cfg[warn] + 1
                else:
                    cfg[crit] = max(value, 2)
                    cfg[warn] = cfg[crit] - 1
            for k in (warn, crit):
                self.alert_spins[k].blockSignals(True)
                self.alert_spins[k].setValue(cfg[k])
                self.alert_spins[k].blockSignals(False)
        config.set('alerts', cfg)

    def _on_poll_changed(self, val: int):
        self.lbl_poll_val.setText(f"{val} ms")
        config.set("polling_interval_ms", val)

    def _on_font_auto_toggled(self, checked: bool) -> None:
        self.spin_font_size.setEnabled(not checked)
        config.set("ui_font_point_size", None if checked else self.spin_font_size.value())
        self._show_font_restart_note()

    def _on_font_size_changed(self, val: int) -> None:
        if not self.chk_font_auto.isChecked():
            config.set("ui_font_point_size", val)
            self._show_font_restart_note()

    def _show_font_restart_note(self) -> None:
        self.lbl_font_restart_note.setText(_("⚠️ Reinicia Algor para aplicar el nuevo tamaño de fuente."))

    def _install_udev_rule(self):
        script_path = Path(__file__).resolve().parents[3] / "setup_udev.sh"
        if not script_path.exists():
            QMessageBox.critical(self, _("Error"), _("No se encontró el script {path}").format(path=script_path))
            return

        try:
            res = subprocess.run(
                ["pkexec", "bash", str(script_path)], capture_output=True, text=True, timeout=120
            )
            if res.returncode == 0:
                QMessageBox.information(
                    self, _("Éxito"),
                    _("✅ Regla USB instalada para Nautilus LCD Cap (1b1c:0c57).\n"
                    "Reinicia el equipo para aplicar los permisos y retirar los permisos amplios "
                    "anteriores de los dispositivos ya conectados.\n"
                    "No se habilitaron escrituras PWM ni cambios de voltaje en la placa base.")
                )
            else:
                # pkexec sin ningún agente gráfico de polkit corriendo (típico en una
                # instalación mínima de Arch, sin GNOME/KDE completos) falla sin mostrar
                # ningún diálogo de contraseña — hay que decírselo al usuario en vez de
                # dejar un error críptico de pkexec sin explicación.
                detail = (res.stderr or res.stdout or "").strip()
                QMessageBox.warning(
                    self, _("Aviso"),
                    _("No se pudo completar la instalación automática.\n\n"
                    "Detalle: {detail}\n\n"
                    "Si no apareció ningún diálogo de contraseña, es posible que tu sistema "
                    "no tenga un agente gráfico de PolicyKit corriendo (común en instalaciones "
                    "mínimas de Arch) — instala uno (ej. polkit-gnome, polkit-kde-agent) o "
                    "ejecuta directamente en una terminal:\n\nsudo bash ./setup_udev.sh").format(
                        detail=detail or _('(sin salida de pkexec)'))
                )
        except subprocess.TimeoutExpired:
            QMessageBox.critical(
                self, _("Error"),
                _("pkexec no respondió a tiempo (¿quedó esperando un diálogo de contraseña que "
                "nunca apareció?). Ejecuta en una terminal:\n\nsudo bash ./setup_udev.sh")
            )
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Fallo al ejecutar pkexec: {error}").format(error=e))

    def _install_pwm_udev_rule(self):
        script_path = Path(__file__).resolve().parents[3] / "setup_udev_pwm.sh"
        if not script_path.exists():
            QMessageBox.critical(self, _("Error"), _("No se encontró el script {path}").format(path=script_path))
            return
        try:
            res = subprocess.run(
                ["pkexec", "bash", str(script_path)], capture_output=True, text=True, timeout=120
            )
            if res.returncode == 0:
                QMessageBox.information(
                    self, _("Éxito"),
                    _("✅ Permiso de escritura PWM instalado (grupo dedicado, solo it8792/it8620).\n"
                    "Cierra sesión y vuelve a entrar para que se aplique tu pertenencia al grupo.\n"
                    "Esto NO activa Reactivo por sí solo — sigue siendo un interruptor aparte, "
                    "y solo escribe en canales que pruebes y confirmes uno por uno.")
                )
            else:
                detail = (res.stderr or res.stdout or "").strip()
                QMessageBox.warning(
                    self, _("Aviso"),
                    _("No se pudo completar la instalación automática.\n\n"
                    "Detalle: {detail}\n\n"
                    "Ejecuta directamente en una terminal:\n\nsudo bash ./setup_udev_pwm.sh").format(
                        detail=detail or _('(sin salida de pkexec)'))
                )
        except subprocess.TimeoutExpired:
            QMessageBox.critical(
                self, _("Error"),
                _("pkexec no respondió a tiempo. Ejecuta en una terminal:\n\nsudo bash ./setup_udev_pwm.sh")
            )
        except Exception as e:
            QMessageBox.critical(self, _("Error"), _("Fallo al ejecutar pkexec: {error}").format(error=e))

    def set_pwm_eligible(self, mappings: dict) -> None:
        """Llamado en cada ciclo de telemetría: si el único canal elegible deja de
        serlo (p. ej. el usuario le quita la confirmación), Reactivo se apaga solo
        en vez de seguir escribiendo con una elegibilidad ya obsoleta."""
        count = sum(1 for m in mappings.values() if eligible_for_pwm_write(m))
        eligible = count > 0
        if not eligible and self.chk_real_control.isChecked():
            self.chk_real_control.setChecked(False)
        self.chk_real_control.setEnabled(eligible)
        self.lbl_pwm_eligible.setText(
            _("{count} canal(es) verificado(s) para escritura real.").format(count=count) if eligible
            else _("Sin canales verificados todavía — pruébalos en «Identificar bomba y ventiladores».")
        )

    def _show_boot_test(self):
        QMessageBox.information(self, _('Comprobar arranque y recuperación'),
            _('1. Cierra iCUE y Windows; libera el USB de VMware.\n'
            '2. Selecciona contenido reconocible y activa ambos inicios automáticos.\n'
            '3. Apaga Linux normalmente. Con el equipo apagado, corta la alimentación '
            'de la fuente hasta que el LCD se apague; después vuelve a encender.\n'
            '4. Entra directamente en Linux, sin abrir la VM, y comprueba imagen, '
            'brillo y sensores. «LCD activo» confirma envío USB, no la imagen visible.\n'
            '5. Guarda tu trabajo, suspende y reanuda. Comprueba que se recupera el LCD.\n'
            'El historial está en Ajustes → Abrir historial de eventos. '
            'No desconectes el USB interno con el equipo encendido.'))

    def _toggle_autostart(self, enabled: bool):
        desktop_file = Path.home() / '.config/autostart/algor.desktop'
        try:
            if enabled:
                desktop_file.parent.mkdir(parents=True, exist_ok=True)
                main_script = Path(__file__).resolve().parents[3] / 'main.py'
                def quote_exec(value):
                    value = str(value).replace('%', '%%')
                    for char in ('\\', '"', '`', '$'):
                        value = value.replace(char, '\\' + char)
                    # Desktop Entry string parsing precedes Exec parsing.
                    return '"' + value.replace('\\', '\\\\') + '"'
                content = ('[Desktop Entry]\nType=Application\n'
                           f'Exec={quote_exec(sys.executable)} {quote_exec(main_script)} --minimized\n'
                           'Hidden=false\nNoDisplay=false\nX-GNOME-Autostart-enabled=true\n'
                           'Name=Algor\nIcon=applications-system\n'
                           'Categories=System;HardwareSettings;\n')
                temporary = desktop_file.with_suffix('.desktop.tmp')
                temporary.write_text(content, encoding='utf-8')
                temporary.replace(desktop_file)
            else:
                desktop_file.unlink(missing_ok=True)
            config.set('autostart', enabled)
        except OSError as exc:
            self.chk_autostart.blockSignals(True)
            self.chk_autostart.setChecked(config.get('autostart', False))
            self.chk_autostart.blockSignals(False)
            QMessageBox.warning(self, _('Inicio automático'), _('No se pudo actualizar el inicio automático: {error}').format(error=exc))

    # ------------------------------------------------------------------
    # Registro de Sensores (Sensor Logging)
    # ------------------------------------------------------------------

    def _rebuild_sensor_checks(self):
        """(Re)crea la lista de checkboxes de sensores, agregando los dinámicos
        (fans, NVMe) en cuanto llega el primer muestreo de telemetría."""
        previously_checked = {sid for sid, chk in self._sensor_checks.items() if chk.isChecked()}
        log_cfg = config.get("sensor_logging", {})
        saved_ids = set(log_cfg.get("sensors", [])) if not previously_checked else previously_checked

        while self._sensors_layout.count():
            item = self._sensors_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sensor_checks = {}

        current_category = None
        for sensor in build_sensor_list(self._last_data):
            if sensor.category != current_category:
                current_category = sensor.category
                cat_label = QLabel(current_category.upper())
                cat_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: {Theme.pt(-3)}pt; font-weight: 700; letter-spacing: 1px;")
                self._sensors_layout.addWidget(cat_label)

            chk = QCheckBox(f"{sensor.label}  ({sensor.unit})")
            chk.setChecked(sensor.id in saved_ids)
            self._sensor_checks[sensor.id] = chk
            self._sensors_layout.addWidget(chk)

        self._sensors_layout.addStretch()

    def _update_log_cfg(self, key: str, value) -> None:
        log_cfg = dict(config.get("sensor_logging", {}))
        log_cfg[key] = value
        config.set("sensor_logging", log_cfg)

    def _choose_log_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, _("Elegir carpeta para el registro CSV"), self.lbl_log_dir.text())
        if directory:
            self.lbl_log_dir.setText(directory)
            self._update_log_cfg("directory", directory)

    def _on_log_limit_toggled(self, enabled: bool) -> None:
        self.spin_log_duration.setEnabled(enabled)
        self._update_log_cfg("limit_minutes", self.spin_log_duration.value() if enabled else 0)

    def _on_log_duration_changed(self, val: int) -> None:
        if self.chk_log_limit.isChecked():
            self._update_log_cfg("limit_minutes", val)

    def _toggle_logging(self) -> None:
        if self.logger.active:
            self.logger.stop()
            self._set_logging_ui_idle()
            return

        sensor_ids = [sid for sid, chk in self._sensor_checks.items() if chk.isChecked()]
        self._update_log_cfg("sensors", sensor_ids)
        duration = self.spin_log_duration.value() if self.chk_log_limit.isChecked() else None

        ok, result = self.logger.start(
            directory=self.lbl_log_dir.text(),
            sensor_ids=sensor_ids,
            interval_sec=self.spin_log_interval.value(),
            duration_min=duration,
            latest_data=self._last_data,
        )
        if not ok:
            QMessageBox.warning(self, _("Registro de Sensores"), result)
            return

        self.btn_log_toggle.setText(_("⏹️ Detener Registro"))
        self.lbl_log_status.setText(_("🔴 Grabando en: {path}").format(path=result))

    def _set_logging_ui_idle(self) -> None:
        self.btn_log_toggle.setText(_("⏺️ Iniciar Registro"))
        self.lbl_log_status.setText(_("Registro detenido. Último archivo: {path}").format(path=self.logger.path) if self.logger.path else "")

    def _on_logging_auto_stopped(self) -> None:
        self._set_logging_ui_idle()
        self.lbl_log_status.setText(_("✅ Registro finalizado (límite de duración alcanzado): {path}").format(path=self.logger.path))

    def _restore_all_fans_to_auto(self):
        """Restablece incondicionalmente todos los canales del sistema a Automático (enable=2)."""
        restored = []
        if self.worker:
            restored = self.worker.request_restore_all_auto()
        else:
            from algor.core.pwm_writer import _global_cleanup
            _global_cleanup()

        if self.chk_real_control.isChecked():
            self.chk_real_control.setChecked(False)

        msg = _("✅ Se han restablecido todos los ventiladores al control Automático de la BIOS.")
        if restored:
            msg += f" ({len(restored)} " + _("canales liberados)")
        self.lbl_pwm_eligible.setText(msg)
        self.lbl_pwm_eligible.setStyleSheet(f"color: #00e676; font-size: {Theme.pt(-2)}pt;")

    def feed_telemetry(self, data: TelemetryData) -> None:
        """Llamado en cada tick de telemetría para alimentar el registro CSV activo
        y para descubrir sensores dinámicos (fans, NVMe) apenas estén disponibles."""
        first_sample = self._last_data is None
        self._last_data = data
        if hasattr(self, 'fan_mapping_dialog'):
            self.fan_mapping_dialog.feed(data)
        if first_sample:
            self._rebuild_sensor_checks()
        self.logger.feed(data)
