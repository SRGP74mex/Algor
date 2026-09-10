"""Identidades persistentes y asignaciones explícitas, solo lectura."""
import math
from pathlib import Path
from typing import Optional

from algor.core.i18n import _

ROLES = {'unknown': _('Sin identificar'), 'pump': _('Bomba'), 'radiator': _('Radiador'),
         'chassis': _('Chasis'), 'unused': _('Sin conectar'), 'liquid_temp': _('Líquido / Refrigerante')}

# Qué roles tiene sentido ofrecer según el tipo de canal detectado — evita que
# la UI ofrezca "Bomba" para una lectura de temperatura o viceversa. La
# elegibilidad real de todas formas la garantiza cada función apply_*_mapping
# al buscar la identidad en el diccionario correspondiente (fan_channels vs
# temp_channels), esto es solo para no confundir al usuario en el desplegable.
FAN_ROLES = ('unknown', 'pump', 'radiator', 'chassis', 'unused')
TEMP_ROLES = ('unknown', 'liquid_temp', 'unused')


def channel_identity(base, chip, channel):
    # Resolve device (ISA/PCI/USB topology), never persist volatile hwmonN indices.
    device = Path(base) / 'device'
    if not device.exists():
        device = Path(base).resolve().parent
    physical = str(device.resolve())
    if '/hwmon' in physical:
        physical = physical.split('/hwmon')[0]
    if physical.endswith('/virtual'):
        # No device topology: do not assign multiple virtual sensors to one identity.
        return None
    return f'{chip}@{physical}/{channel}'


def normalize_mapping(value):
    if not isinstance(value, dict):
        value = {}
    role = value.get('role', 'unknown')
    if role not in ROLES:
        role = 'unknown'
    def number(key, default, low, high):
        try:
            return max(low, min(high, int(value.get(key, default))))
        except (TypeError, ValueError, OverflowError):
            return default
    confirmed = value.get('confirmed') is True and role not in ('unknown', 'unused')
    # La bomba nunca es elegible para pruebas/escritura PWM, sin importar lo que
    # traiga un config.json editado a mano: esta puerta es estructural, no una
    # convención de la UI. Ver docs/PWM_REAL_CONTROL.md.
    pwm_tested = value.get('pwm_tested') is True and confirmed and role not in ('unknown', 'unused', 'pump')
    pwm_channel = str(value.get('pwm_channel', '')).strip()[:200] if pwm_tested else ''
    return dict(role=role, name=str(value.get('name', '')).strip()[:80], confirmed=confirmed,
                alarm=value.get('alarm') is True and confirmed,
                minimum=number('minimum', 300, 1, 20000), delay=number('delay', 5, 3, 60),
                pwm_tested=pwm_tested, pwm_channel=pwm_channel,
                pwm_tested_at=number('pwm_tested_at', 0, 0, 99999999999) if pwm_tested else 0)


def valid_rpm(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def valid_temp(value):
    """Rango plausible para un sensor físico de PC: descarta None y también
    lecturas de diodo desconectado (p. ej. -55°C, visto en este mismo equipo
    en un canal sin usar) que no son 'cero real', son ruido de un pin flotante."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 125


def apply_pump_mapping(data, mappings):
    data.pump_rpm_available = False
    data.pump_rpm = 0
    pumps = [key for key, raw in mappings.items()
             if (m := normalize_mapping(raw))['confirmed'] and m['role'] == 'pump']
    if len(pumps) == 1:
        value = data.fan_channels.get(pumps[0], {}).get('rpm')
        if valid_rpm(value):
            data.pump_rpm = value
            data.pump_rpm_available = True


def apply_liquid_temp_mapping(data, mappings):
    """Igual que apply_pump_mapping pero para temperatura: nunca se inventa el
    líquido. Si el usuario confirma exactamente un canal como 'liquid_temp',
    ese pasa a ser la lectura real; con cero o varios, sigue sin verificar."""
    data.liquid_temp_available = False
    data.liquid_temp = 0.0
    candidates = [key for key, raw in mappings.items()
                  if (m := normalize_mapping(raw))['confirmed'] and m['role'] == 'liquid_temp']
    if len(candidates) == 1:
        value = data.temp_channels.get(candidates[0], {}).get('temp')
        if valid_temp(value):
            data.liquid_temp = value
            data.liquid_temp_available = True
            data.liquid_temp_is_estimated = False


def eligible_for_pwm_write(raw_mapping) -> bool:
    """True solo si este canal puede recibir escrituras PWM reales: identificado,
    confirmado, con la prueba guiada superada y sin ser la bomba. Único punto que
    todo código de escritura (pwm_writer.py) debe consultar — nunca reimplementar
    esta condición en otro lugar."""
    m = normalize_mapping(raw_mapping)
    return bool(m['pwm_tested'] and m['pwm_channel'])


def aggregate_confirmed_fan_rpm(data, mappings) -> Optional[float]:
    """Promedio de RPM de los canales confirmados que NO son la bomba
    (radiador/chasis). None si no hay ningún canal confirmado con lectura
    válida — nunca se inventa un valor para alimentar una comparación."""
    values = [data.fan_channels.get(key, {}).get('rpm')
              for key, raw in mappings.items()
              if (m := normalize_mapping(raw))['confirmed'] and m['role'] != 'pump']
    values = [v for v in values if valid_rpm(v)]
    return sum(values) / len(values) if values else None
