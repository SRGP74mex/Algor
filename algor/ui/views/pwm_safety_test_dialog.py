"""Prueba guiada de PWM real: formaliza, con restauración garantizada y sin
automatismo silencioso, la secuencia que el usuario ya validó a mano en
terminal (100% → 15% → automático, 15 s cada tramo). Un canal a la vez, nunca
sobre la bomba, nunca sin que el equipo esté a la vista. Ver docs/PWM_REAL_CONTROL.md.
"""
import os
from pathlib import Path

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                             QComboBox, QPushButton, QMessageBox)
from algor.core.i18n import _
from algor.core.pwm_writer import percent_to_raw, MANUAL_ENABLE_VALUE, AUTO_ENABLE_VALUE

HOLD_SECONDS = 15
HIGH_PERCENT = 100
# Solo para esta prueba puntual y supervisada — distinto del piso de operación
# continua (30%), que vive únicamente en pwm_writer.py y nunca baja de ahí.
LOW_PERCENT = 15


class PwmSafetyTestDialog(QDialog):
    test_confirmed = pyqtSignal(str, str)  # (identidad del ventilador, identidad del pwm probado)

    def __init__(self, fan_identity: str, fan_label: str, candidates: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_('Probar control PWM real'))
        self.resize(560, 420)
        self.fan_identity = fan_identity
        self.candidates = candidates  # {identidad_pwm: {'pwm_path','enable_path','chip'}}
        self._original = None
        self._stage = 'idle'
        self._elapsed = 0

        layout = QVBoxLayout(self)
        warn = QLabel(_(
            'Vas a probar control PWM real sobre un candidato para "{label}". '
            'Un canal a la vez, con el equipo a la vista y sin trabajo sin guardar abierto. '
            'Primero sube a 100% (sin riesgo de apagado en ninguna placa), luego baja '
            'brevemente a {low}% para confirmar que sigue girando, y se restaura '
            'automático al terminar — la misma secuencia que ya validaste a mano.'
        ).format(label=fan_label, low=LOW_PERCENT))
        warn.setWordWrap(True)
        layout.addWidget(warn)

        row = QHBoxLayout()
        row.addWidget(QLabel(_('Candidato PWM (mismo chip; el índice no se asume, elígelo):')))
        self.combo = QComboBox()
        for identity in sorted(candidates):
            self.combo.addItem(identity.rsplit('/', 1)[-1], identity)
        row.addWidget(self.combo)
        layout.addLayout(row)

        self.status = QLabel(_('Sin iniciar.'))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        self.reading = QLabel(_('RPM en vivo: N/D'))
        layout.addWidget(self.reading)

        buttons = QHBoxLayout()
        self.btn_start = QPushButton(_('Iniciar prueba'))
        self.btn_start.setEnabled(bool(candidates))
        self.btn_start.clicked.connect(self._start)
        buttons.addWidget(self.btn_start)
        self.btn_abort = QPushButton(_('Abortar'))
        self.btn_abort.setEnabled(False)
        self.btn_abort.clicked.connect(self._abort)
        buttons.addWidget(self.btn_abort)
        close = QPushButton(_('Cerrar'))
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        if not candidates:
            self.status.setText(_('Sin candidatos PWM detectados en este chip.'))

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)

    def _selected_pwm_identity(self):
        return self.combo.currentData()

    def _fan_input_path(self) -> Path:
        pwm_identity = self._selected_pwm_identity()
        base = Path(self.candidates[pwm_identity]['pwm_path']).parent
        fan_channel = self.fan_identity.rsplit('/', 1)[-1]
        return base / f'{fan_channel}_input'

    @staticmethod
    def _read(path) -> "str | None":
        try:
            return Path(path).read_text().strip()
        except OSError:
            return None

    @staticmethod
    def _write(path, value) -> None:
        Path(path).write_text(str(value))

    def _start(self):
        pwm_identity = self._selected_pwm_identity()
        if not pwm_identity:
            return
        channel = self.candidates[pwm_identity]
        if not (os.access(channel['pwm_path'], os.W_OK) and os.access(channel['enable_path'], os.W_OK)):
            QMessageBox.warning(self, _('Falta permiso'),
                _('No hay permiso de escritura sobre este canal. Instala el permiso de '
                'escritura PWM en Ajustes primero (requiere cerrar sesión una vez).'))
            return
        original_enable = self._read(channel['enable_path'])
        original_pwm = self._read(channel['pwm_path'])
        self._original = (channel['enable_path'], channel['pwm_path'], original_enable, original_pwm)
        try:
            self._write(channel['enable_path'], MANUAL_ENABLE_VALUE)
            self._write(channel['pwm_path'], percent_to_raw(HIGH_PERCENT))
        except OSError as e:
            QMessageBox.critical(self, _('Error'), _('No se pudo escribir: {error}').format(error=e))
            self._restore()
            return
        self._stage = 'high'
        self._elapsed = 0
        self.btn_start.setEnabled(False)
        self.combo.setEnabled(False)
        self.btn_abort.setEnabled(True)
        self.status.setText(_('Subiendo a {percent}% — observa/escucha el equipo. {seconds}s...').format(
            percent=HIGH_PERCENT, seconds=HOLD_SECONDS))
        self.timer.start()

    def _tick(self):
        self._elapsed += 1
        rpm = self._read(self._fan_input_path())
        self.reading.setText(_('RPM en vivo: {rpm}').format(rpm=rpm if rpm is not None else _('N/D')))
        remaining = HOLD_SECONDS - self._elapsed
        if remaining > 0:
            etapa = _('Subiendo a 100%') if self._stage == 'high' else _('Bajando a {percent}%').format(percent=LOW_PERCENT)
            self.status.setText(_('{stage} — {seconds}s restantes...').format(stage=etapa, seconds=remaining))
            return
        if self._stage == 'high':
            channel = self.candidates[self._selected_pwm_identity()]
            try:
                self._write(channel['pwm_path'], percent_to_raw(LOW_PERCENT))
            except OSError as e:
                self.status.setText(_('Error al bajar a {percent}%: {error}').format(percent=LOW_PERCENT, error=e))
                self._restore()
                return
            self._stage = 'low'
            self._elapsed = 0
            self.status.setText(_('Bajando a {percent}% — confirma que sigue girando. {seconds}s...').format(
                percent=LOW_PERCENT, seconds=HOLD_SECONDS))
            return
        self.timer.stop()
        self._restore()
        self._ask_confirmation()

    def _restore(self):
        self.timer.stop()
        if self._original:
            enable_path, pwm_path, original_enable, original_pwm = self._original
            try:
                if original_pwm is not None:
                    self._write(pwm_path, original_pwm)
                self._write(enable_path, original_enable if original_enable is not None else str(AUTO_ENABLE_VALUE))
            except OSError:
                pass
        self.btn_start.setEnabled(bool(self.candidates))
        self.combo.setEnabled(True)
        self.btn_abort.setEnabled(False)
        self._stage = 'idle'

    def _abort(self):
        self.status.setText(_('Abortado — restaurando automático.'))
        self._restore()

    def _ask_confirmation(self):
        pwm_identity = self._selected_pwm_identity()
        reply = QMessageBox.question(
            self, _('Confirmar'),
            _('¿Confirmas que este fue el ventilador/grupo correcto y que respondió sin '
            'ningún comportamiento anómalo (apagado, olor, ruido extraño)?')
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.test_confirmed.emit(self.fan_identity, pwm_identity)
            self.status.setText(_('Confirmado y guardado — ya elegible para Reactivo.'))
        else:
            self.status.setText(_('No confirmado — el canal sigue sin habilitarse para escritura.'))

    def closeEvent(self, event):
        if self._stage != 'idle':
            self._restore()
        super().closeEvent(event)
