from typing import Dict, List
from algor.core.config import config


class FanCurveEngine:
    """Motor de cálculo y aplicación de curvas de ventilador y bomba."""

    def __init__(self):
        self.active_profile = config.get("active_profile", "balanced")
        self.hysteresis = config.get("hysteresis_c", 2.0)
        self._last_evaluated_temp = 30.0
        self._last_target_pwm = 35
        # Reactivo (escritura PWM real) SIEMPRE arranca en False, sin importar lo
        # que diga config.json: es una decisión deliberada, no un descuido — dado
        # el historial de apagones de este usuario, cada sesión debe reactivarlo
        # explícitamente. Ver docs/PWM_REAL_CONTROL.md.
        self.real_control_enabled = False

    def set_real_control_enabled(self, enabled: bool) -> None:
        """No persiste en config a propósito — ver el comentario en __init__."""
        self.real_control_enabled = enabled

    def set_profile(self, profile_name: str):
        config.set("active_profile", profile_name)
        self.active_profile = config.get("active_profile", "balanced")

    def get_active_points(self) -> List[Dict[str, int]]:
        return config.get_curve(self.active_profile)

    def calculate_pwm(self, current_temp: float) -> int:
        """
        Calcula el porcentaje de PWM (0-100%) correspondiente a la temperatura actual
        aplicando interpolación lineal suave entre los puntos de la curva y filtro de histéresis.
        """
        points = self.get_active_points()
        if not points:
            return 50

        sorted_pts = sorted(points, key=lambda x: x["temp"])
        
        # Filtro de histéresis: si la temperatura baja, amortiguar la bajada
        if current_temp < self._last_evaluated_temp:
            effective_temp = max(current_temp, self._last_evaluated_temp - 0.5)
        else:
            effective_temp = current_temp

        self._last_evaluated_temp = effective_temp

        # Si está por debajo del primer punto
        if effective_temp <= sorted_pts[0]["temp"]:
            target = sorted_pts[0]["pwm"]
        # Si está por encima del último punto
        elif effective_temp >= sorted_pts[-1]["temp"]:
            target = sorted_pts[-1]["pwm"]
        else:
            # Interpolación entre puntos consecutivos
            target = sorted_pts[0]["pwm"]
            for i in range(len(sorted_pts) - 1):
                p1 = sorted_pts[i]
                p2 = sorted_pts[i + 1]
                if p1["temp"] <= effective_temp <= p2["temp"]:
                    t_range = p2["temp"] - p1["temp"]
                    if t_range > 0:
                        factor = (effective_temp - p1["temp"]) / t_range
                        target = int(p1["pwm"] + factor * (p2["pwm"] - p1["pwm"]))
                    else:
                        target = p1["pwm"]
                    break

        self._last_target_pwm = max(0, min(100, target))
        return self._last_target_pwm

    def record_target_pwm(self, pwm_percent: int) -> None:
        """Registra el PWM objetivo calculado, de forma segura y pasiva.

        No realiza escrituras directas a los chips Super I/O / VRM de la placa base
        para evitar conflictos con el microcódigo de la BIOS y protecciones de energía.
        Ver docs/PLAN_X99_Y_LCD.md: acceso hwmon de solo lectura, siempre.
        """
        self._last_target_pwm = max(0, min(100, pwm_percent))

