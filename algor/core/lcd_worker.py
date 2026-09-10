"""Un único hilo posee el LCD. Buzón acotado: solo conserva el último estado."""
from copy import deepcopy
import threading
import time
import json
from pathlib import Path
from datetime import datetime, timezone
from PyQt6.QtCore import QThread, pyqtSignal
from algor.core.corsair_usb import CorsairNautilusDevice
from algor.core.i18n import _
from algor.core.lcd_renderer import LCDRenderer, cpu_reading, cpu_usage_reading, normalize_settings
from algor.core.logging_config import get_logger
from algor.core.lcd_memory import load_captured_image, save_captured_image, inspect_stored_image, PreparedMemoryMedia, prepare_custom_media

logger = get_logger('lcd')


class LCDSession:
    """Máquina de sesión comprobable sin Qt ni un dispositivo físico."""
    HEARTBEAT = 4.0  # Margen frente a los ~4.5 s observados en iCUE.

    def __init__(self, device, on_event=lambda text: None):
        self.device = device
        self.on_event = on_event
        self.connected = False
        self.sent = None
        self.brightness = None
        self.next_heartbeat = 0.0
        self.retry_at = 0.0
        self.retry_delay = 1.0
        self.last_error = ''
        self.last_tick = None

    def close(self):
        try:
            self.device.disconnect()
        finally:
            self.connected = False
            self.sent = None
            self.brightness = None

    def tick(self, jpeg, brightness, active, now, cancelled=lambda: False, lifecycle_now=None):
        # CLOCK_BOOTTIME includes suspend time on Linux, unlike monotonic.
        clock = now if lifecycle_now is None else lifecycle_now
        if self.last_tick is not None and clock - self.last_tick > 8:
            self.close()
            self.retry_at = 0
            self.retry_delay = 1
            self.on_event(_("LCD: pausa detectada; se restablece la sesión."))
        self.last_tick = clock
        if not active:
            if self.connected:
                self.close()
            self.retry_at = 0
            self.retry_delay = 1
            return 'idle', _('LCD detenido · previsualización local')
        if now < self.retry_at:
            return 'error', self.last_error
        try:
            if not self.connected:
                self.device.connect()
                self.connected = True
                self.next_heartbeat = now
                self.on_event(_('LCD: interfaz conectada; enviando contenido de sesión.'))
            if cancelled():
                raise InterruptedError(_('Sesión detenida.'))
            if jpeg != self.sent:
                self.device.send_jpeg(jpeg, cancelled)
                self.device.keep_alive()
                self.sent = jpeg
                self.next_heartbeat = now + self.HEARTBEAT
            elif now >= self.next_heartbeat:
                self.device.keep_alive()
                self.next_heartbeat = now + self.HEARTBEAT
            if brightness != self.brightness:
                self.device.set_brightness(brightness)
                self.brightness = brightness
            self.retry_delay = 1
            return 'active', _('Sesión LCD activa · confirma la imagen en la pantalla física')
        except InterruptedError:
            self.close()
            return 'idle', _('LCD detenido')
        except Exception as exc:
            self.close()
            code = getattr(exc, 'errno', None)
            if code in (13, 1):
                detail = _('Permisos USB insuficientes. Revisa la regla del LCD en Ajustes.')
            elif code == 16:
                detail = _('LCD ocupado. Libéralo desde VMware o cierra la otra aplicación.')
            else:
                detail = str(exc)
            self.retry_at = now + self.retry_delay
            self.retry_delay = min(10, self.retry_delay * 2)
            self.last_error = _('{detail} · reintentando conexión').format(detail=detail)
            logger.warning('Sesión LCD: %s', detail)
            return 'error', self.last_error


class LCDWorker(QThread):
    lifecycle_event = pyqtSignal(str)
    memory_status = pyqtSignal(bool, str)
    memory_prepared = pyqtSignal(object)
    preview_ready = pyqtSignal(bytes)
    status_changed = pyqtSignal(str, str)

    def __init__(self, settings=None, device_factory=CorsairNautilusDevice):
        super().__init__()
        self._condition = threading.Condition()
        self._settings = normalize_settings(settings or {})
        self._telemetry = None
        self._received_at = None
        self._memory_pending = None
        self._memory_busy = False
        self._active = False
        self._stopping = False
        self._device_factory = device_factory

    def configure(self, settings):
        with self._condition:
            self._settings = normalize_settings(settings)
            self._condition.notify_all()

    def set_active(self, active):
        with self._condition:
            if active and (self._memory_busy or self._memory_pending is not None):
                return
            self._active = bool(active)
            self._condition.notify_all()

    def request_memory_save(self, label):
        with self._condition:
            if self._stopping or self._active or self._memory_busy or self._memory_pending is not None:
                self.memory_status.emit(self._memory_busy, _('Detén la sesión LCD y espera a que termine cualquier guardado.'))
                return False
            if not isinstance(label, PreparedMemoryMedia) and label not in ('A', 'B', 'C', 'check'):
                self.memory_status.emit(False, _('Imagen de memoria desconocida.'))
                return False
            self._memory_pending = label
            self._memory_busy = True
            self._condition.notify_all()
        self.memory_status.emit(True, _('Consultando memoria…') if label == 'check' else _('Preparando guardado…'))
        return True

    def request_memory_prepare(self, path, rotation):
        with self._condition:
            if self._stopping or self._active or self._memory_busy:
                self.memory_status.emit(self._memory_busy, _('Detén la sesión antes de preparar contenido.'))
                return
            self._memory_pending = ('prepare', path, rotation)
            self._memory_busy = True
            self._condition.notify_all()
        self.memory_status.emit(True, _('Preparando archivo local sin escribir en el LCD…'))

    def _save_memory(self, session, label):
        record = dict(operation='query' if label == 'check' else 'save', image=None if label == 'check' else (label.label if isinstance(label, PreparedMemoryMedia) else label), outcome='started', diagnostics={}, physical_persistence='pending')
        journal = None
        message = ''
        try:
            asset = label if isinstance(label, PreparedMemoryMedia) else (None if label == 'check' else load_captured_image(label))
            if isinstance(asset, PreparedMemoryMedia):
                record.update(frame_count=len(asset.frames), source_durations=list(asset.source_durations), rotation=asset.rotation, experimental_timing=True, interval_field=asset.interval_field, optimization_summary=asset.optimization_summary)
            folder = Path.home() / '.local/state/algor/memory'
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            journal = folder / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ') + '.json')
            journal.write_text(json.dumps(record, indent=2))
            session.close()
            session.device.connect()
            if label == 'check':
                result = inspect_stored_image(session.device)
                name = result['identified_image']
                message = (_('El CRC del LCD corresponde a la imagen {name}.').format(name=name) if name else
                           _('El CRC del LCD no corresponde a las muestras A/B/C.'))
                message += ' ' + _('Consulta completada sin escribir memoria; confirma el contenido visible en la pantalla.')
            else:
                result = save_captured_image(session.device, asset,
                    lambda text: self.memory_status.emit(True, text), record['diagnostics'])
                message = (_('El LCD ya reconoce esta imagen.') if result['outcome'] == 'already_stored'
                           else _('CRC de la imagen confirmado.')) + ' ' + _('Comprueba que permanece al salir de Algor.')
            record.update(result)
        except Exception as exc:
            record.update(outcome='unconfirmed', error=str(exc))
            message = (_('Consulta no completada: {error}').format(error=exc) if label == 'check'
                       else _('Guardado no confirmado: {error} No se reintentó la escritura.').format(error=exc))
        finally:
            session.close()
            if journal is not None:
                try:
                    journal.write_text(json.dumps(record, indent=2))
                    message += ' ' + _('Registro: {path}').format(path=journal)
                except OSError as exc:
                    message += ' ' + _('No se pudo guardar el registro: {error}').format(error=exc)
            with self._condition:
                self._memory_busy = False
            self.memory_status.emit(False, message)

    def update_telemetry(self, data):
        with self._condition:
            self._telemetry = deepcopy(data)
            self._received_at = time.monotonic()
            self._condition.notify_all()

    def _cancelled(self):
        with self._condition:
            return self._stopping or not self._active

    def run(self):
        session = LCDSession(self._device_factory(), self.lifecycle_event.emit)
        renderer = LCDRenderer()
        last_preview = None
        last_status = None
        render_key = None
        jpeg = None
        try:
            while True:
                with self._condition:
                    if self._stopping:
                        break
                    memory = self._memory_pending
                    self._memory_pending = None
                    settings = dict(self._settings)
                    data, received, active = self._telemetry, self._received_at, self._active
                if memory is not None:
                    if isinstance(memory, tuple) and memory[0] == 'prepare':
                        try:
                            prepared = prepare_custom_media(memory[1], memory[2])
                            self.memory_prepared.emit(prepared)
                            message = _('Preparación lista. Revisa la miniatura antes de guardar.')
                        except Exception as exc:
                            self.memory_prepared.emit(None)
                            message = _('No se pudo preparar: {error}').format(error=exc)
                        with self._condition:
                            self._memory_busy = False
                        self.memory_status.emit(False, message)
                    else:
                        self._save_memory(session, memory)
                    continue
                now = time.monotonic()
                temperature = cpu_reading(data, received, now)
                usage = cpu_usage_reading(data, received, now)
                # Las imágenes estáticas se vuelven a comprobar por mtime cada décima de segundo; los JPEG preparados se almacenan en caché.
                key = (tuple(settings.items()), (temperature if settings['show_temperature'] else None, usage if settings['show_usage'] else None) if settings['mode'] == 'cpu_temp' else int(now * 10))
                try:
                    if key != render_key:
                        jpeg = renderer.render(settings, temperature, now=now, cpu_usage=usage)
                        render_key = key
                    if jpeg != last_preview:
                        self.preview_ready.emit(jpeg)
                        last_preview = jpeg
                    state = session.tick(jpeg, settings['brightness'], active, now, self._cancelled,
                                         lifecycle_now=time.clock_gettime(time.CLOCK_BOOTTIME)
                                         if hasattr(time, 'CLOCK_BOOTTIME') else now)
                except Exception as exc:
                    session.close()
                    state = ('error', _('No se puede preparar la imagen: {error}').format(error=exc))
                    if last_preview != b'':
                        self.preview_ready.emit(b'')
                        last_preview = b''
                if state != last_status:
                    self.status_changed.emit(*state)
                    last_status = state
                with self._condition:
                    if not self._stopping:
                        self._condition.wait(0.1)
        finally:
            session.close()
            self.status_changed.emit('idle', _('LCD detenido'))

    def stop(self):
        with self._condition:
            self._stopping = True
            self._active = False
            self._condition.notify_all()
        # Cada operación USB tiene timeout, y el envío consulta cancelación entre
        # fragmentos. No destruir un QThread que siga usando la interfaz.
        self.wait()
