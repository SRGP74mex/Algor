"""Asistente de identificación en lectura, sin probar velocidades automáticamente."""
import time
from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, QComboBox,
                             QLineEdit, QCheckBox, QSpinBox, QPushButton, QHBoxLayout, QMessageBox)
from algor.core.config import config
from algor.core.fan_mapping import normalize_mapping, valid_rpm, valid_temp, ROLES, FAN_ROLES, TEMP_ROLES
from algor.core.i18n import _
from algor.ui.views.pwm_safety_test_dialog import PwmSafetyTestDialog


class FanMappingDialog(QDialog):
    mappings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_('Identificar bomba y ventiladores'))
        self.resize(680, 580)
        self.channels = {}
        self.pwm_channels = {}
        self.received = None
        self._loaded = None
        layout = QVBoxLayout(self)
        note = QLabel(_('1. Selecciona una lectura.  2. Identifica el cable y asigna su función.\n'
                      '3. Confirma la asociación y guarda. El control permanece en BIOS.\n'
                      'No se varían voltajes ni se detienen ventiladores. Revisa cables con el equipo apagado.'))
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.channel = QComboBox()
        self.channel.setMinimumContentsLength(25)
        self.channel.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        form.addRow(_('Canal detectado:'), self.channel)
        self.reading = QLabel(_('N/D'))
        form.addRow(_('Lectura en vivo:'), self.reading)
        self.identity = QLabel()
        self.identity.setWordWrap(True)
        form.addRow(_('Identificador:'), self.identity)
        self.role = QComboBox()
        form.addRow(_('Función:'), self.role)
        self.name = QLineEdit()
        self.name.setStyleSheet("background: #1c2038; color: #f0f6fc; border: 1px solid #414765; border-radius: 4px; padding: 6px;")
        self.name.setMaxLength(80)
        self.name.setPlaceholderText(_('Ejemplo: Radiador, grupo 1'))
        form.addRow(_('Nombre:'), self.name)
        self.confirmed = QCheckBox(_('He confirmado qué componente corresponde a este canal'))
        form.addRow(self.confirmed)
        self.alarm = QCheckBox(_('Avisar por RPM bajas o pérdida de lectura'))
        form.addRow(self.alarm)
        self.minimum = QSpinBox()
        self.minimum.setRange(1, 20000)
        self.minimum.setSuffix(' RPM')
        form.addRow(_('Mínimo de aviso:'), self.minimum)
        self.delay = QSpinBox()
        self.delay.setRange(3, 60)
        self.delay.setSuffix(' s')
        form.addRow(_('Duración antes de avisar:'), self.delay)
        layout.addLayout(form)
        help_text = QLabel(_('El mínimo es un umbral de alerta, no una orden de velocidad. '
                           'Elige un valor adecuado a tus lecturas y equipo. La recuperación usa un margen '
                           'del 10 % (al menos 50 RPM). Un distribuidor puede mostrar el tacómetro de un '
                           'solo ventilador. «Sin conectar» nunca genera alertas. No se deduce la conexión '
                           'de un ventilador a partir del número de un PWM.'))
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.btn_pwm_test = QPushButton(_('🧪 Probar control PWM real (avanzado)…'))
        self.btn_pwm_test.setEnabled(False)
        self.btn_pwm_test.clicked.connect(self._open_pwm_test)
        layout.addWidget(self.btn_pwm_test)
        self.lbl_pwm_status = QLabel()
        self.lbl_pwm_status.setWordWrap(True)
        layout.addWidget(self.lbl_pwm_status)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.save = QPushButton(_('Guardar asignación'))
        self.save.setObjectName('PrimaryBtn')
        self.save.clicked.connect(self._save)
        buttons.addWidget(self.save)
        self.delete = QPushButton(_('🗑️ Eliminar asignación'))
        self.delete.setEnabled(False)
        self.delete.clicked.connect(self._delete)
        buttons.addWidget(self.delete)
        close = QPushButton(_('Cerrar'))
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.channel.currentIndexChanged.connect(self._load)
        self.role.currentIndexChanged.connect(self._role_changed)
        self.confirmed.toggled.connect(self._controls)
        self.alarm.toggled.connect(self._controls)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._refresh_reading)
        self.timer.start()
        self.feed(None)

    def feed(self, data):
        if data is not None:
            self.channels = {}
            for key, entry in data.fan_channels.items():
                self.channels[key] = {'label': entry.get('label', key.split('/')[-1]),
                                       'kind': 'fan', 'value': entry.get('rpm')}
            for key, entry in data.temp_channels.items():
                self.channels[key] = {'label': entry.get('label', key.split('/')[-1]),
                                       'kind': 'temp', 'value': entry.get('temp')}
            self.pwm_channels = dict(data.pwm_channels)
            self.received = time.monotonic()
        existing = {self.channel.itemData(i) for i in range(self.channel.count())}
        saved = config.get('fan_mappings', {})
        # "Solo lo que responde": RPM>0 real o temperatura plausible (0-125°C),
        # descartando lecturas de conector vacío o diodo desconectado — salvo
        # que ya tenga una asignación guardada, para no esconder configuración
        # existente que momentáneamente no responda.
        keys = {k for k, entry in self.channels.items() if self._is_responding(entry)} | set(saved)
        for key in sorted(keys - existing):
            entry = self.channels.get(key, {})
            kind_tag = ' 🌡️' if entry.get('kind') == 'temp' else ''
            self.channel.addItem(entry.get('label', key.split('/')[-1]) + kind_tag, key)
        self.save.setEnabled(self.channel.count() > 0)
        self._refresh_reading()

    @staticmethod
    def _is_responding(entry) -> bool:
        value = entry.get('value')
        if entry.get('kind') == 'temp':
            return valid_temp(value)
        return valid_rpm(value) and value > 0

    def _refresh_reading(self):
        key = self.channel.currentData()
        entry = self.channels.get(key, {})
        value = entry.get('value')
        fresh = self.received is not None and time.monotonic() - self.received <= 10
        if not fresh or value is None:
            self.reading.setText(_('N/D · lectura no disponible'))
        elif entry.get('kind') == 'temp':
            self.reading.setText(f'{value:.1f} °C' if valid_temp(value) else _('{value:.1f} °C (implausible)').format(value=value))
        else:
            self.reading.setText(f'{value:.0f} RPM' if valid_rpm(value) else _('N/D · lectura no disponible'))

    def _load(self):
        key = self.channel.currentData()
        kind = self.channels.get(key, {}).get('kind', 'fan')
        self._current_kind = kind
        mapping = normalize_mapping(config.get('fan_mappings', {}).get(key, {}))
        self._loaded = key
        applicable_roles = TEMP_ROLES if kind == 'temp' else FAN_ROLES
        self.role.blockSignals(True)
        self.role.clear()
        for role_key in applicable_roles:
            self.role.addItem(ROLES[role_key], role_key)
        found = self.role.findData(mapping['role'])
        self.role.setCurrentIndex(found if found >= 0 else 0)
        self.role.blockSignals(False)
        self.name.setText(mapping['name'])
        self.confirmed.setChecked(mapping['confirmed'])
        self.alarm.setChecked(mapping['alarm'])
        self.minimum.setValue(mapping['minimum'])
        self.delay.setValue(mapping['delay'])
        self.identity.setText(key or '')
        self.status.setText(_('Los cambios se aplican al pulsar Guardar asignación.'))
        self.delete.setEnabled(bool(key) and key in config.get('fan_mappings', {}))
        self._controls()
        self._refresh_reading()
        self._refresh_pwm_test_state()

    def _refresh_pwm_test_state(self):
        key = self.channel.currentData()
        if getattr(self, '_current_kind', 'fan') == 'temp':
            # El control PWM solo tiene sentido para ventiladores.
            self.btn_pwm_test.setVisible(False)
            self.lbl_pwm_status.setVisible(False)
            return
        self.btn_pwm_test.setVisible(True)
        self.lbl_pwm_status.setVisible(True)
        saved = normalize_mapping(config.get('fan_mappings', {}).get(key, {}) if key else {})
        is_pump = saved['role'] == 'pump'
        eligible_role = saved['confirmed'] and saved['role'] not in ('pump', 'unknown', 'unused')
        self.btn_pwm_test.setEnabled(eligible_role)
        self.btn_pwm_test.setToolTip(_('La bomba nunca se prueba ni se controla desde Algor.') if is_pump else '')
        if is_pump:
            self.lbl_pwm_status.setText(_('La bomba nunca se prueba ni se controla desde Algor.'))
        elif not saved['confirmed']:
            self.lbl_pwm_status.setText(_('Guarda la asignación (rol confirmado) antes de probar PWM real.'))
        elif saved['pwm_tested']:
            self.lbl_pwm_status.setText(_("✅ PWM probado y confirmado: {channel}").format(channel=saved['pwm_channel']))
        else:
            self.lbl_pwm_status.setText(_('Identificado pero sin probar para control PWM real.'))

    def _open_pwm_test(self):
        key = self.channel.currentData()
        if not key or getattr(self, '_current_kind', 'fan') == 'temp':
            return
        chip = key.split('@')[0]
        candidates = {ident: ch for ident, ch in self.pwm_channels.items() if ch.get('chip') == chip}
        label = self.channels.get(key, {}).get('label', key)
        dialog = PwmSafetyTestDialog(key, label, candidates, self)
        dialog.test_confirmed.connect(self._on_pwm_test_confirmed)
        dialog.exec()

    def _on_pwm_test_confirmed(self, fan_identity, pwm_identity):
        mappings = dict(config.get('fan_mappings', {}))
        mapping = dict(mappings.get(fan_identity, {}))
        mapping['pwm_tested'] = True
        mapping['pwm_channel'] = pwm_identity
        mapping['pwm_tested_at'] = int(time.time())
        mappings[fan_identity] = mapping
        config.set('fan_mappings', mappings)
        self.mappings_changed.emit()
        self._refresh_pwm_test_state()

    def _role_changed(self):
        self.confirmed.setChecked(False)
        self.alarm.setChecked(False)
        self._controls()

    def _controls(self):
        assigned = self.role.currentData() not in ('unknown', 'unused')
        self.confirmed.setEnabled(assigned)
        if not assigned:
            self.confirmed.setChecked(False)
        # Las alertas RPM son un concepto de ventilador; no se extienden a
        # canales de temperatura en esta versión (ver docs/PWM_REAL_CONTROL.md
        # para el porqué de mantener el alcance acotado).
        is_temp = getattr(self, '_current_kind', 'fan') == 'temp'
        allowed = assigned and self.confirmed.isChecked() and not is_temp
        self.alarm.setEnabled(allowed)
        self.alarm.setToolTip(_('Las alertas RPM no aplican a canales de temperatura.') if is_temp else '')
        if not allowed:
            self.alarm.setChecked(False)
        self.minimum.setEnabled(allowed and self.alarm.isChecked())
        self.delay.setEnabled(allowed and self.alarm.isChecked())

    def _save(self):
        key = self.channel.currentData()
        if not key:
            return
        # Preservar pwm_tested/pwm_channel existentes: este formulario no los edita,
        # y normalize_mapping ya los invalida por sí solo si el rol/confirmación
        # cambian de forma que los invaliden (p. ej. a "bomba" o "sin confirmar").
        existing = normalize_mapping(config.get('fan_mappings', {}).get(key, {}))
        mapping = normalize_mapping(dict(role=self.role.currentData(), name=self.name.text(),
                                          confirmed=self.confirmed.isChecked(), alarm=self.alarm.isChecked(),
                                          minimum=self.minimum.value(), delay=self.delay.value(),
                                          pwm_tested=existing['pwm_tested'], pwm_channel=existing['pwm_channel'],
                                          pwm_tested_at=existing['pwm_tested_at']))
        mappings = dict(config.get('fan_mappings', {}))
        mappings[key] = mapping
        config.set('fan_mappings', mappings)
        self.mappings_changed.emit()
        self._refresh_pwm_test_state()
        self.status.setText(_('Asignación guardada. ') + (_('Alertas habilitadas para este canal.') if mapping['alarm']
                                                     else _('Alertas desactivadas para este canal.')))

    def _delete(self):
        """Deshace por completo una asignación: rol, nombre, alarma y cualquier
        prueba PWM confirmada para este canal. También es el camino para limpiar
        un canal huérfano tras un cambio de hardware (ya no responde, pero
        seguía apareciendo en la lista solo porque tenía datos guardados)."""
        key = self.channel.currentData()
        mappings = dict(config.get('fan_mappings', {}))
        if not key or key not in mappings:
            return
        reply = QMessageBox.question(
            self, _('Eliminar asignación'),
            _('¿Eliminar la asignación de este canal? Esto borra rol, nombre, alarma y '
              'cualquier prueba PWM confirmada. No afecta al hardware.')
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        del mappings[key]
        config.set('fan_mappings', mappings)
        self.mappings_changed.emit()
        entry = self.channels.get(key, {})
        if not self._is_responding(entry):
            # Ya no responde y ya no está guardado: no califica para seguir en la
            # lista (mismo filtro que feed() aplica al poblarla).
            index = self.channel.currentIndex()
            if index >= 0:
                self.channel.removeItem(index)
            if self.channel.count() == 0:
                self.save.setEnabled(False)
        else:
            self._load()
        self.status.setText(_('Asignación eliminada.'))
