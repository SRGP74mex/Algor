import json
from copy import deepcopy
import os
import tempfile
import threading
from pathlib import Path
from algor.core.logging_config import get_logger

logger = get_logger("config")

DEFAULT_CONFIG = {
    "version": 1,
    "theme": "cyber_dark",
    # None = automático (usa el tamaño de fuente por defecto de Qt, que ya
    # respeta QT_FONT_DPI y el factor de escala de texto del sistema).
    # Si no es None, es un entero en puntos (pt) elegido por el usuario en Ajustes.
    "ui_font_point_size": None,
    "polling_interval_ms": 1000,
    "temperature_unit": "C",
    "active_profile": "balanced",
    "profiles": {
        "silent": [
            {"temp": 20, "pwm": 25},
            {"temp": 45, "pwm": 30},
            {"temp": 60, "pwm": 45},
            {"temp": 75, "pwm": 65},
            {"temp": 85, "pwm": 100}
        ],
        "balanced": [
            {"temp": 20, "pwm": 35},
            {"temp": 40, "pwm": 45},
            {"temp": 60, "pwm": 65},
            {"temp": 75, "pwm": 85},
            {"temp": 85, "pwm": 100}
        ],
        "extreme": [
            {"temp": 20, "pwm": 50},
            {"temp": 40, "pwm": 70},
            {"temp": 60, "pwm": 85},
            {"temp": 70, "pwm": 100},
            {"temp": 85, "pwm": 100}
        ],
        "custom": [
            {"temp": 20, "pwm": 30},
            {"temp": 40, "pwm": 40},
            {"temp": 60, "pwm": 60},
            {"temp": 75, "pwm": 80},
            {"temp": 85, "pwm": 100}
        ]
    },
    "hysteresis_c": 2.0,
    "lcd_cap": {
        "enabled": True,
        "brightness": 80,
        "mode": "cpu_temp",
        "show_temperature": True,
        "show_usage": False,
        "accent_color": "#00f0ff",
        "custom_image_path": "",
        "fps": 30,
        "show_clock": True,
        "rotation": 0,  # grados: 0, 90, 180, 270
        "case_color": "Black",  # etiqueta cosmética ('Black' / 'White'), no controla hardware RGB
        # 0-100: tamaño del texto de sensores en el LCD físico. 0 = tamaño original
        # armónico (por defecto); 100 = máximo legible sin desbordar la pantalla redonda.
        "text_scale": 0
    },
    "fan_mappings": {},
    "alerts": {
        "enabled": True,
        "cpu_temp_warn": 80,
        "cpu_temp_crit": 90,
        "gpu_temp_warn": 80,
        "gpu_temp_crit": 88
    },
    "autostart": False,
    "minimize_to_tray": True,
    "dashboard_sensors": ["cpu_temp_package", "gpu_temp", "liquid_temp", "pump_rpm"],
    "sensor_logging": {
        "directory": "",
        "interval_sec": 5,
        "limit_minutes": 0,
        "sensors": ["cpu_temp_package", "gpu_temp", "liquid_temp", "pump_rpm"]
    }
}


class ConfigManager:
    """Administrador de configuración persistente para la aplicación.

    Se lee y escribe tanto desde el hilo de la interfaz como desde el hilo de
    hardware (HardwareWorker); el lock evita que una lectura vea un diccionario
    a medio modificar mientras el otro hilo lo está actualizando.
    """
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "algor"
        self.config_file = self.config_dir / "config.json"
        self.data = deepcopy(DEFAULT_CONFIG)
        self._lock = threading.Lock()
        self.load()

    def load(self):
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Retirar el perfil antiguo antes de combinar la configuración.
                    migrated = loaded.get("active_profile") == "zero_rpm" or "zero_rpm" in loaded.get("profiles", {})
                    if loaded.get("active_profile") == "zero_rpm":
                        loaded["active_profile"] = "balanced"
                    loaded.get("profiles", {}).pop("zero_rpm", None)
                    # Combinación recursiva básica con los defaults
                    with self._lock:
                        merged = self._merge_dicts(DEFAULT_CONFIG, loaded)
                        self.data, sanitized = self._sanitize(merged)
                if migrated or sanitized:
                    self.save()
            else:
                self.save()
        except Exception as e:
            logger.error("Error cargando configuración: %s", e)
            with self._lock:
                self.data = deepcopy(DEFAULT_CONFIG)

    def save(self):
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self._lock:
                snapshot = json.dumps(self.data, indent=4, ensure_ascii=False)
            # Escritura atómica: nunca dejar config.json truncado tras un corte
            # de luz o un cierre abrupto a mitad de escritura.
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.config_dir, delete=False
            ) as tmp:
                tmp.write(snapshot)
                temporary = Path(tmp.name)
            try:
                os.chmod(temporary, 0o600)
                os.replace(temporary, self.config_file)
            finally:
                temporary.unlink(missing_ok=True)
        except Exception as e:
            logger.error("Error guardando configuración: %s", e)

    def get(self, key, default=None):
        with self._lock:
            return self.data.get(key, default)

    def set(self, key, value):
        if key == "active_profile" and value == "zero_rpm":
            value = "balanced"
        if key == "profiles":
            value = {k: v for k, v in value.items() if k != "zero_rpm"}
        with self._lock:
            self.data[key] = value
        self.save()

    def get_curve(self, profile_name=None):
        if profile_name == "zero_rpm":
            profile_name = "balanced"
        with self._lock:
            if profile_name is None:
                profile_name = self.data.get("active_profile", "balanced")
            return self.data.get("profiles", {}).get(profile_name, DEFAULT_CONFIG["profiles"]["balanced"])

    def set_curve(self, profile_name, points):
        if profile_name == "zero_rpm":
            raise ValueError("El perfil Cero RPM fue retirado.")
        with self._lock:
            if "profiles" not in self.data:
                self.data["profiles"] = {}
            self.data["profiles"][profile_name] = points
        self.save()

    def _merge_dicts(self, default, custom):
        merged = deepcopy(default)
        for k, v in custom.items():
            if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
                merged[k] = self._merge_dicts(merged[k], v)
            else:
                merged[k] = v
        return merged

    @staticmethod
    def _is_valid_curve(curve) -> bool:
        """Una curva válida es una lista no vacía de puntos {temp, pwm} numéricos."""
        if not isinstance(curve, list) or not curve:
            return False
        for point in curve:
            if not isinstance(point, dict):
                return False
            temp, pwm = point.get("temp"), point.get("pwm")
            if isinstance(temp, bool) or not isinstance(temp, (int, float)):
                return False
            if isinstance(pwm, bool) or not isinstance(pwm, (int, float)):
                return False
        return True

    def _sanitize(self, data):
        """Corrige campos con forma inválida (config.json editado a mano o
        corrompido) devolviendo sus valores por defecto, sin descartar el
        resto de la configuración del usuario. Devuelve (data, changed)."""
        changed = False

        profiles = data.get("profiles")
        if not isinstance(profiles, dict):
            logger.warning("Sección 'profiles' inválida en config.json; restaurando valores por defecto.")
            profiles = deepcopy(DEFAULT_CONFIG["profiles"])
            data["profiles"] = profiles
            changed = True
        else:
            for name, curve in list(profiles.items()):
                if not self._is_valid_curve(curve):
                    logger.warning("Perfil de curva '%s' inválido en config.json; restaurando valores por defecto.", name)
                    profiles[name] = deepcopy(DEFAULT_CONFIG["profiles"].get(name) or DEFAULT_CONFIG["profiles"]["balanced"])
                    changed = True
            for name, curve in DEFAULT_CONFIG["profiles"].items():
                if name not in profiles:
                    profiles[name] = deepcopy(curve)
                    changed = True

        if data.get("active_profile") not in profiles:
            data["active_profile"] = "balanced"
            changed = True

        font_pt = data.get("ui_font_point_size")
        if font_pt is not None and (isinstance(font_pt, bool) or not isinstance(font_pt, int) or not 7 <= font_pt <= 32):
            logger.warning("Tamaño de fuente '%s' inválido en config.json; restaurando automático.", font_pt)
            data["ui_font_point_size"] = None
            changed = True

        alerts = data.get("alerts")
        if not isinstance(alerts, dict):
            logger.warning("Sección 'alerts' inválida en config.json; restaurando valores por defecto.")
            data["alerts"] = deepcopy(DEFAULT_CONFIG["alerts"])
            changed = True
        else:
            for key, default_val in DEFAULT_CONFIG["alerts"].items():
                if key.endswith("_warn") or key.endswith("_crit"):
                    value = alerts.get(key)
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        logger.warning("Umbral de alerta '%s' inválido en config.json; restaurando valor por defecto.", key)
                        alerts[key] = default_val
                        changed = True

        return data, changed


# Singleton
config = ConfigManager()

