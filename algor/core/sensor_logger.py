"""Registro periódico de telemetría a CSV, equivalente al Sensor Logging de iCUE."""
import csv
import time
from pathlib import Path
from typing import Callable, List, Optional

from algor.core.hardware import TelemetryData
from algor.core.sensors import get_sensor_map


class SensorLogger:
    """Escribe una fila CSV por intervalo con los sensores elegidos por el usuario."""

    def __init__(self):
        self.active = False
        self.path: Optional[Path] = None
        self.on_auto_stop: Optional[Callable[[], None]] = None

        self._sensor_ids: List[str] = []
        self._interval_sec = 5.0
        self._duration_sec: Optional[float] = None
        self._start_time = 0.0
        self._last_write = 0.0
        self._file = None
        self._writer = None

    def start(self, directory: str, sensor_ids: List[str], interval_sec: float,
              duration_min: Optional[float], latest_data: Optional[TelemetryData]) -> tuple[bool, str]:
        self.stop()

        sensor_map = get_sensor_map(latest_data)
        chosen = [sensor_map[sid] for sid in sensor_ids if sid in sensor_map]
        if not chosen:
            return False, "Selecciona al menos un sensor para registrar."

        try:
            out_dir = Path(directory).expanduser()
            out_dir.mkdir(parents=True, exist_ok=True)
            self.path = out_dir / f"algor_sensors_{time.strftime('%Y%m%d_%H%M%S')}.csv"
            self._file = open(self.path, "w", newline="", encoding="utf-8")
        except Exception as e:
            return False, f"No se pudo crear el archivo de registro: {e}"

        self._writer = csv.writer(self._file)
        self._writer.writerow(["timestamp"] + [f"{s.label} ({s.unit})" for s in chosen])
        self._file.flush()

        self._sensor_ids = [s.id for s in chosen]
        self._interval_sec = max(0.5, float(interval_sec))
        self._duration_sec = duration_min * 60.0 if duration_min else None
        self._start_time = time.time()
        self._last_write = 0.0
        self.active = True
        return True, str(self.path)

    def feed(self, data: TelemetryData) -> None:
        if not self.active:
            return

        now = time.time()
        if self._duration_sec and (now - self._start_time) >= self._duration_sec:
            self.stop()
            if self.on_auto_stop:
                self.on_auto_stop()
            return

        if now - self._last_write < self._interval_sec:
            return
        self._last_write = now

        sensor_map = get_sensor_map(data)
        row = [time.strftime("%Y-%m-%d %H:%M:%S")]
        for sid in self._sensor_ids:
            sensor = sensor_map.get(sid)
            value = sensor.getter(data) if sensor else None
            row.append("" if value is None else round(value, 2))

        try:
            self._writer.writerow(row)
            self._file.flush()
        except Exception:
            pass

    def stop(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
        self._file = None
        self._writer = None
        self.active = False
