"""Registro central de sensores disponibles, usado por el Dashboard personalizable
y por el Registro de Sensores (Sensor Logging), igual que el catálogo de sensores de iCUE.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from algor.core.hardware import TelemetryData
from algor.core.i18n import _


@dataclass
class SensorDef:
    id: str
    label: str
    unit: str
    category: str
    min_val: float
    max_val: float
    getter: Callable[[TelemetryData], Optional[float]]


STATIC_SENSORS: List[SensorDef] = [
    SensorDef("cpu_temp_package", _("CPU Package"), "°C", _("Procesador"), 0, 100, lambda d: d.cpu_temp_package if d.cpu_temp_available else None),
    SensorDef("cpu_temp_max", _("CPU Núcleo Máx."), "°C", _("Procesador"), 0, 100, lambda d: d.cpu_temp_max if d.cpu_temp_available else None),
    SensorDef("cpu_usage_total", _("CPU Uso"), "%", _("Procesador"), 0, 100, lambda d: d.cpu_usage_total),
    SensorDef("cpu_freq_mhz", _("CPU Frecuencia"), "MHz", _("Procesador"), 0, 6000, lambda d: d.cpu_freq_mhz),
    SensorDef("gpu_temp", _("GPU Temp"), "°C", _("Tarjeta Gráfica"), 0, 100, lambda d: d.gpu_temp),
    SensorDef("gpu_usage", _("GPU Uso"), "%", _("Tarjeta Gráfica"), 0, 100, lambda d: d.gpu_usage),
    SensorDef("gpu_fan_speed", _("GPU Ventilador"), "%", _("Tarjeta Gráfica"), 0, 100, lambda d: d.gpu_fan_speed),
    SensorDef("gpu_memory_used_mb", _("GPU VRAM Usada"), "MB", _("Tarjeta Gráfica"), 0, 24576, lambda d: d.gpu_memory_used_mb),
    SensorDef("liquid_temp", _("Líquido AIO"), "°C", _("Líquido / Bomba"), 0, 70, lambda d: d.liquid_temp if d.liquid_temp_available else None),
    SensorDef("pump_rpm", _("Bomba AIO"), "RPM", _("Líquido / Bomba"), 0, 2500, lambda d: d.pump_rpm if d.pump_rpm_available else None),
]


def _dynamic_sensors(data: Optional[TelemetryData]) -> List[SensorDef]:
    sensors: List[SensorDef] = []
    if data is None:
        return sensors

    from algor.core.config import config
    from algor.core.fan_mapping import normalize_mapping, ROLES
    mappings = config.get('fan_mappings', {})
    for key in sorted(set(data.fan_channels) | set(mappings)):
        mapping = normalize_mapping(mappings.get(key, {}))
        if not mapping['confirmed']:
            continue
        label = mapping['name'] or ROLES[mapping['role']]
        sensors.append(SensorDef(
            id=f'fan_channel::{key}', label=label, unit='RPM', category=_('Ventiladores identificados'),
            min_val=0, max_val=5000,
            getter=lambda d, k=key: d.fan_channels.get(k, {}).get('rpm'),
        ))

    for key in sorted(data.fans_rpm.keys()):
        sensors.append(SensorDef(
            id=f"fan_rpm::{key}",
            label=_("Fan {name}").format(name=key.replace('_', ' ').upper()),
            unit="RPM", category=_("Ventiladores"), min_val=0, max_val=3000,
            getter=(lambda d, k=key: d.fans_rpm.get(k)),
        ))

    for key in sorted(data.fans_pwm.keys()):
        sensors.append(SensorDef(
            id=f"fan_pwm::{key}",
            label=_("PWM {name}").format(name=key.replace('_', ' ').upper()),
            unit="%", category=_("Ventiladores"), min_val=0, max_val=100,
            getter=(lambda d, k=key: d.fans_pwm.get(k)),
        ))

    for i in range(len(data.nvme_temps)):
        sensors.append(SensorDef(
            id=f"nvme_temp::{i}",
            label=_("NVMe #{n}").format(n=i + 1),
            unit="°C", category=_("Almacenamiento"), min_val=0, max_val=100,
            getter=(lambda d, idx=i: d.nvme_temps[idx] if idx < len(d.nvme_temps) else None),
        ))

    return sensors


def build_sensor_list(latest: Optional[TelemetryData] = None) -> List[SensorDef]:
    """Catálogo completo: sensores fijos + dinámicos detectados en el último muestreo."""
    return list(STATIC_SENSORS) + _dynamic_sensors(latest)


def get_sensor_map(latest: Optional[TelemetryData] = None) -> Dict[str, SensorDef]:
    return {s.id: s for s in build_sensor_list(latest)}
