"""Comparación pasiva, de solo lectura, entre el aumento de temperatura y la
respuesta real de RPM observada. Nunca escribe PWM ni infiere una conclusión
sin datos suficientes (ver docs/PLAN_X99_Y_LCD.md: acceso hwmon solo lectura)."""
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

INSUFFICIENT_DATA = 'insufficient_data'
NO_RISE = 'no_rise'
RPM_UNAVAILABLE = 'rpm_unavailable'
RESPONDING = 'responding'
NOT_RESPONDING = 'not_responding'


@dataclass(frozen=True)
class ThermalResponseStatus:
    state: str
    delta_temp_c: Optional[float] = None
    delta_rpm: Optional[float] = None


@dataclass(frozen=True)
class _Sample:
    t: float
    temp: Optional[float]
    rpm: Optional[float]


class ThermalResponseMonitor:
    """Ventana deslizante de (temperatura, RPM observado) para inferir si algo
    (BIOS o la app) está respondiendo a un aumento de calor real. Solo lectura:
    no calcula ni sugiere ningún valor de PWM a escribir."""

    def __init__(self, window_seconds: float = 180.0, min_window_seconds: float = 60.0,
                 min_samples: int = 8, temp_rise_c: float = 3.0, rpm_rise: float = 150.0,
                 resume_gap_seconds: float = 30.0, max_samples: int = 900):
        self.window_seconds = window_seconds
        self.min_window_seconds = min_window_seconds
        self.min_samples = min_samples
        self.temp_rise_c = temp_rise_c
        self.rpm_rise = rpm_rise
        self.resume_gap_seconds = resume_gap_seconds
        self._samples: Deque[_Sample] = deque(maxlen=max_samples)

    def reset(self) -> None:
        self._samples.clear()

    def record_sample(self, temp: Optional[float], rpm: Optional[float], now: float) -> None:
        if self._samples:
            last = self._samples[-1].t
            if now < last or now - last > self.resume_gap_seconds:
                # Reloj retrocedido o hueco grande (suspensión/reanudación): la
                # ventana previa no es comparable, nunca se interpreta como
                # "no hubo respuesta".
                self.reset()
        self._samples.append(_Sample(now, temp, rpm))
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._samples and self._samples[0].t < cutoff:
            self._samples.popleft()

    def status(self) -> ThermalResponseStatus:
        samples = list(self._samples)
        if len(samples) < self.min_samples:
            return ThermalResponseStatus(INSUFFICIENT_DATA)
        covered = samples[-1].t - samples[0].t
        if covered < self.min_window_seconds:
            return ThermalResponseStatus(INSUFFICIENT_DATA)

        mid = len(samples) // 2
        first_half, second_half = samples[:mid], samples[mid:]
        temp_before = _average(s.temp for s in first_half)
        temp_after = _average(s.temp for s in second_half)
        if temp_before is None or temp_after is None:
            return ThermalResponseStatus(INSUFFICIENT_DATA)

        delta_temp = temp_after - temp_before
        if delta_temp < self.temp_rise_c:
            return ThermalResponseStatus(NO_RISE, delta_temp_c=delta_temp)

        rpm_before = _average(s.rpm for s in first_half)
        rpm_after = _average(s.rpm for s in second_half)
        if rpm_before is None or rpm_after is None:
            return ThermalResponseStatus(RPM_UNAVAILABLE, delta_temp_c=delta_temp)

        delta_rpm = rpm_after - rpm_before
        state = RESPONDING if delta_rpm >= self.rpm_rise else NOT_RESPONDING
        return ThermalResponseStatus(state, delta_temp_c=delta_temp, delta_rpm=delta_rpm)


def _average(values) -> Optional[float]:
    valid = [v for v in values if isinstance(v, (int, float))]
    return sum(valid) / len(valid) if valid else None
