from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QFrame, QPushButton, QComboBox, QSlider, QSpinBox)
from algor.core.config import config, DEFAULT_CONFIG
from algor.core.hardware import TelemetryData
from algor.core.i18n import _
from algor.ui.components.curve_editor import CurveEditor
from algor.ui.theme import Theme


class CurvesView(QWidget):
    """Vista de edición interactiva de curvas de ventilador y bomba."""
    curve_updated = pyqtSignal(str, list)
    manual_pwm_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_profile = config.get("active_profile", "balanced")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(14)

        # 1. Cabecera y Selección de Perfil
        top_card = QFrame()
        top_card.setObjectName("Card")
        top_layout = QHBoxLayout(top_card)
        top_layout.setContentsMargins(14, 10, 14, 10)
        top_layout.setSpacing(12)

        top_layout.addWidget(QLabel(_("🎛️ Perfil de Curva:")))

        self.combo_profile = QComboBox()
        self.combo_profile.addItems(["balanced", "silent", "extreme", "custom"])
        self.combo_profile.setCurrentText(self.active_profile)
        self.combo_profile.currentTextChanged.connect(self._on_profile_changed)
        top_layout.addWidget(self.combo_profile)

        top_layout.addWidget(QLabel(_("🎯 Sensor de Control:")))
        self.combo_sensor = QComboBox()
        self.combo_sensor.addItems([_("CPU Package (°C)"), _("Líquido Refrigerante (°C)"), _("GPU Core (°C)")])
        top_layout.addWidget(self.combo_sensor)

        top_layout.addStretch()

        btn_reset = QPushButton(_("↺ Restaurar Defecto"))
        btn_reset.clicked.connect(self._reset_curve)
        top_layout.addWidget(btn_reset)

        layout.addWidget(top_card)

        # Banner informativo de arquitectura de refrigeración AIO
        self.lbl_info_banner = QLabel(_(
            "💧 Bomba AIO: Flujo constante óptimo (~2,300 RPM) • 🌀 Curvas de respuesta configuradas para los Ventiladores del Radiador."
        ))
        self.lbl_info_banner.setWordWrap(True)
        self.lbl_info_banner.setStyleSheet(
            f"background-color: {Theme.BG_CARD}; color: #8e92a8; border: 1px solid {Theme.BORDER_SUBTLE}; "
            f"border-radius: 10px; padding: 8px 14px; font-size: {Theme.pt(-1)}pt; font-weight: 500;"
        )
        layout.addWidget(self.lbl_info_banner)

        # 2. Contenedor Central con Editor Interactivo
        editor_card = QFrame()
        editor_card.setObjectName("Card")
        editor_vbox = QVBoxLayout(editor_card)
        editor_vbox.setContentsMargins(14, 14, 14, 14)
        editor_vbox.setSpacing(8)

        info_header = QHBoxLayout()
        lbl_hint = QLabel(_("💡 Arrastra los puntos en la gráfica para moldear la curva de refrigeración."))
        lbl_hint.setStyleSheet("color: #8b949e; font-style: italic;")
        info_header.addWidget(lbl_hint)

        self.lbl_active_stat = QLabel(_("Temp Actual: -- °C ➔ PWM simulado: -- %"))
        self.lbl_active_stat.setStyleSheet("font-weight: bold; color: #00f0ff;")
        info_header.addWidget(self.lbl_active_stat, alignment=Qt.AlignmentFlag.AlignRight)

        editor_vbox.addLayout(info_header)

        self.lbl_thermal_response = QLabel(_("Comparando con la respuesta real… (reuniendo datos)"))
        self.lbl_thermal_response.setWordWrap(True)
        self.lbl_thermal_response.setStyleSheet("color: #8b949e; font-weight: 600;")
        editor_vbox.addWidget(self.lbl_thermal_response)

        # Lienzo del editor
        points = config.get_curve(self.active_profile)
        self.curve_editor = CurveEditor(points=points)
        self.curve_editor.curve_changed.connect(self._on_curve_modified)
        editor_vbox.addWidget(self.curve_editor)

        layout.addWidget(editor_card, stretch=3)

        # 3. Barra Inferior de Prueba Manual de PWM
        test_card = QFrame()
        test_card.setObjectName("Card")
        test_layout = QHBoxLayout(test_card)
        test_layout.setContentsMargins(14, 10, 14, 10)
        test_layout.setSpacing(12)

        test_layout.addWidget(QLabel(_("🔧 Control / Prueba Manual:")))

        self.test_slider = QSlider(Qt.Orientation.Horizontal)
        self.test_slider.setRange(0, 100)
        self.test_slider.setValue(50)
        self.test_slider.valueChanged.connect(self._on_test_slider)
        test_layout.addWidget(self.test_slider)

        self.lbl_test_val = QLabel("50%")
        self.lbl_test_val.setStyleSheet("font-weight: bold; color: #00f0ff; min-width: 40px;")
        test_layout.addWidget(self.lbl_test_val)

        self.btn_apply_test = QPushButton(_("Control por BIOS · solo lectura"))
        self.btn_apply_test.setEnabled(False)
        self.btn_apply_test.setObjectName("PrimaryBtn")
        self.btn_apply_test.clicked.connect(lambda: self.manual_pwm_requested.emit(self.test_slider.value()))
        test_layout.addWidget(self.btn_apply_test)

        layout.addWidget(test_card)

        self.lbl_pwm_caption = QLabel(_(
            "Sin canales verificados para escritura real: prueba uno en Ajustes → "
            "Identificar bomba y ventiladores. Nunca incluye la bomba."
        ))
        self.lbl_pwm_caption.setWordWrap(True)
        self.lbl_pwm_caption.setStyleSheet(f"color: #8b949e; font-size: {Theme.pt(-2)}pt;")
        layout.addWidget(self.lbl_pwm_caption)

    def set_pwm_eligible(self, eligible: bool) -> None:
        """Habilita el botón de prueba manual solo cuando hay al menos un canal
        con la prueba PWM superada y Reactivo activo. Ver fan_mapping.eligible_for_pwm_write
        y docs/PWM_REAL_CONTROL.md — nunca se habilita para la bomba."""
        self.btn_apply_test.setEnabled(eligible)
        if eligible:
            self.btn_apply_test.setText(_("⚠️ Aplicar al hardware (canal verificado)"))
            self.lbl_pwm_caption.setText(
                _("Esto escribe PWM real al canal verificado, con piso de 30% — nunca simulación.")
            )
        else:
            self.btn_apply_test.setText(_("Control por BIOS · solo lectura"))
            self.lbl_pwm_caption.setText(_(
                "Sin canales verificados para escritura real: prueba uno en Ajustes → "
                "Identificar bomba y ventiladores. Nunca incluye la bomba."
            ))

    def _on_profile_changed(self, prof_name: str):
        self.active_profile = prof_name
        config.set("active_profile", prof_name)
        points = config.get_curve(prof_name)
        self.curve_editor.set_points(points)

    def _on_curve_modified(self, points: list):
        config.set_curve(self.active_profile, points)
        self.curve_updated.emit(self.active_profile, points)

    def _reset_curve(self):
        if self.active_profile in DEFAULT_CONFIG["profiles"]:
            def_pts = DEFAULT_CONFIG["profiles"][self.active_profile]
            self.curve_editor.set_points(def_pts)
            config.set_curve(self.active_profile, def_pts)
            self.curve_updated.emit(self.active_profile, def_pts)

    def _on_test_slider(self, val: int):
        self.lbl_test_val.setText(f"{val}%")

    def set_active_profile(self, profile_name: str):
        if self.combo_profile.currentText() != profile_name:
            self.combo_profile.setCurrentText(profile_name)

    def update_telemetry(self, data: TelemetryData, calculated_pwm: int):
        sensor_type = self.combo_sensor.currentIndex()
        if sensor_type == 0:
            target_temp = data.cpu_temp_package
        elif sensor_type == 1:
            target_temp = data.liquid_temp
        else:
            target_temp = data.gpu_temp

        self.curve_editor.set_live_telemetry(target_temp, calculated_pwm)
        self.lbl_active_stat.setText(_("Temp: {temp:.1f}°C ➔ PWM simulado: {pwm}%").format(temp=target_temp, pwm=calculated_pwm))

    def update_thermal_response(self, status) -> None:
        from algor.core.thermal_response import (INSUFFICIENT_DATA, NO_RISE,
            RPM_UNAVAILABLE, RESPONDING, NOT_RESPONDING)
        texts = {
            INSUFFICIENT_DATA: (_('Comparando con la respuesta real… (reuniendo datos)'), '#8b949e'),
            NO_RISE: (_('Sin subida de temperatura sostenida para comparar todavía.'), '#8b949e'),
            RPM_UNAVAILABLE: (_('Sin lectura RPM confirmada para comparar (configura un canal en Mapeo de ventiladores).'), '#8b949e'),
            RESPONDING: (_('✅ Los ventiladores responden al calor real (control por BIOS activo).'), '#00e676'),
            NOT_RESPONDING: (_('⚠️ Sin respuesta de ventiladores detectada pese al aumento de temperatura.'), '#ffbd69'),
        }
        text, color = texts[status.state]
        self.lbl_thermal_response.setText(text)
        self.lbl_thermal_response.setStyleSheet(f'color: {color}; font-weight: 600;')
        self.curve_editor.set_response_status(status)
