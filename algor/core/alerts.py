"""Alertas por transiciones; sin control térmico ni escrituras al hardware."""
import math
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from algor.core.i18n import _


def _safe_float(value, default):
    """Convierte a float o cae al valor por defecto si el dato de config es inválido."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


@dataclass(frozen=True)
class AlertEvent:
    key: str
    level: str
    message: str


class EventJournal:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder else Path.home() / '.local/state/algor/events'
        self.error = ''
        self.handler = None
        try:
            self.folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.handler = RotatingFileHandler(self.folder / 'events.jsonl', maxBytes=1024*1024,
                                               backupCount=3, encoding='utf-8')
            self.handler.setFormatter(logging.Formatter('%(message)s'))
        except OSError as exc:
            self.error = str(exc)

    def record(self, event):
        if self.handler:
            payload = json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),
                                      **event.__dict__), ensure_ascii=False)
            # Surface write errors to the UI instead of silently losing history.
            try:
                if self.handler.shouldRollover(logging.makeLogRecord({'msg': payload})):
                    self.handler.doRollover()
                self.handler.stream.write(payload + '\n')
                self.handler.flush()
            except OSError as exc:
                self.error = str(exc)

    def close(self):
        if self.handler:
            self.handler.close()
            self.handler = None


class AlertEngine:
    def __init__(self, now=0):
        self.started = now
        self.received = None
        self.data = None
        self.states = {}
        self.pending = {}
        self.seen_gpu = False
        self.thermal_response_status = None

    def feed(self, data, now, thermal_response=None):
        self.data, self.received = data, now
        self.seen_gpu |= bool(getattr(data, 'gpu_temp_available', False))
        self.thermal_response_status = thermal_response

    def _transition(self, key, level, message, now, delay=0):
        previous = self.states.get(key, ('ok', ''))[0]
        if level == previous:
            self.pending.pop(key, None)
            return []
        target, since = self.pending.get(key, (None, now))
        if target != level:
            since = now
            self.pending[key] = (level, since)
        if now - since < delay:
            return []
        self.pending.pop(key, None)
        self.states[key] = (level, message)
        return [AlertEvent(key, level, message)]

    def evaluate(self, cfg, now, lcd_state='idle', fan_mappings=None):
        if not cfg.get('enabled', True):
            events = [AlertEvent(k, 'disabled', _('Supervisión desactivada por el usuario.'))
                      for k, (level, _msg) in self.states.items() if level != 'ok']
            self.states.clear()
            self.pending.clear()
            return events
        events = []
        fresh = self.received is not None and now - self.received <= 10
        missing = not fresh and now - self.started >= 10
        events += self._transition('telemetry', 'warning' if missing else 'ok',
                                  _('Sin actualizaciones de sensores durante más de 10 s.') if missing
                                  else _('La telemetría vuelve a responder.'), now)
        for device, field in [('cpu', 'cpu_temp_package'), ('gpu', 'gpu_temp')]:
            if device == 'gpu' and not self.seen_gpu:
                continue
            label = device.upper()
            value = getattr(self.data, field, None)
            valid = (fresh and getattr(self.data, device + '_temp_available', False)
                     and isinstance(value, (int, float)) and math.isfinite(value))
            events += self._transition(device + '_sensor', 'ok' if valid else 'warning',
                                      _('{label}: lectura recuperada.').format(label=label) if valid
                                      else _('{label}: temperatura no disponible.').format(label=label),
                                      now, 0 if valid else 10)
            if not valid:
                # Never clear an overtemperature alarm with a missing/placeholder reading.
                self.pending.pop(device + '_temperature', None)
                continue
            default_warn = 80.0
            default_crit = 90.0 if device == 'cpu' else 88.0
            warn = _safe_float(cfg.get(device + '_temp_warn', default_warn), default_warn)
            crit = max(warn + 1, _safe_float(cfg.get(device + '_temp_crit', default_crit), default_crit))
            key = device + '_temperature'
            prev = self.states.get(key, ('ok', ''))[0]
            if value >= crit or (prev == 'critical' and value >= crit - 3):
                level = 'critical'
            elif value >= warn or (prev in ('warning', 'critical') and value >= warn - 3):
                level = 'warning'
            else:
                level = 'ok'
            text_map = {'critical': _('temperatura crítica'), 'warning': _('temperatura elevada'), 'ok': _('temperatura recuperada')}
            events += self._transition(key, level, _('{label}: {text} ({value:.1f} °C).').format(
                label=label, text=text_map[level], value=value), now,
                                       2 if level == 'warning' and prev == 'ok' else 0)
            if device == 'cpu':
                from algor.core.thermal_response import NOT_RESPONDING
                status = self.thermal_response_status
                hot = level in ('warning', 'critical')
                no_response = hot and status is not None and status.state == NOT_RESPONDING
                events += self._transition(
                    'thermal_response', 'warning' if no_response else 'ok',
                    _('CPU: sin respuesta de ventiladores detectada pese al aumento de temperatura.')
                    if no_response else
                    _('CPU: los ventiladores acompañan la temperatura o no hay evidencia suficiente para dudarlo.'),
                    now, 15 if no_response else 0)
        events += self._evaluate_fans(fan_mappings or {}, now, fresh)
        events += self._transition('lcd', 'warning' if lcd_state == 'error' else 'ok',
                                  _('LCD: conexión o envío fallando durante más de 10 s.') if lcd_state == 'error'
                                  else (_('LCD: sesión recuperada.') if lcd_state == 'active' else _('LCD: sesión detenida.')),
                                  now, 10 if lcd_state == 'error' else 0)
        return events

    def _evaluate_fans(self, mappings, now, fresh):
        from algor.core.fan_mapping import normalize_mapping, valid_rpm, ROLES
        events = []
        enabled = {}
        for channel, raw in mappings.items():
            mapping = normalize_mapping(raw)
            if mapping['alarm']:
                enabled['rpm::' + channel] = (channel, mapping)
        for key in list(set(self.states) | set(self.pending)):
            if key.startswith('rpm::') and key not in enabled:
                previous = self.states.pop(key, ('ok', ''))[0]
                self.pending.pop(key, None)
                if previous != 'ok':
                    events.append(AlertEvent(key, 'disabled', _('Supervisión RPM desactivada para este canal.')))
        channels = getattr(self.data, 'fan_channels', {})
        for key, (channel, mapping) in enabled.items():
            label = mapping['name'] or ROLES[mapping['role']]
            value = channels.get(channel, {}).get('rpm')
            previous = self.states.get(key, ('ok', ''))[0]
            if not fresh or not valid_rpm(value):
                level = 'missing'
                text = _('{label}: lectura RPM no disponible; no se puede confirmar el giro.').format(label=label)
            else:
                minimum = mapping['minimum']
                margin = max(50, round(minimum * 0.1))
                low = value < minimum or (previous == 'low' and value < minimum + margin)
                level = 'low' if low else 'ok'
                text = (_('{label}: RPM bajas ({value:.0f}; mínimo configurado {minimum}).').format(
                            label=label, value=value, minimum=minimum) if low
                        else _('{label}: lectura RPM recuperada ({value:.0f}).').format(label=label, value=value))
            changes = self._transition(key, level, text, now, 0 if level == 'ok' else mapping['delay'])
            for event in changes:
                severity = ('critical' if level == 'low' and mapping['role'] == 'pump' else
                            'warning' if level in ('low', 'missing') else 'ok')
                events.append(AlertEvent(event.key, severity, event.message))
        return events

    def active_messages(self):
        return [message for level, message in self.states.values() if level != 'ok']
