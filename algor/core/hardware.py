import glob
import math
import threading
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING
import psutil
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from algor.core.config import config
from algor.core.logging_config import get_logger
from algor.core.pwm_writer import PwmWriter

logger = get_logger("hardware")

if TYPE_CHECKING:
    from algor.core.fan_controller import FanCurveEngine


@dataclass
class TelemetryData:
    timestamp: float = 0.0
    # CPU
    cpu_temp_package: float = 0.0
    cpu_temp_max: float = 0.0
    cpu_cores_temps: List[float] = field(default_factory=list)
    cpu_usage_available: bool = False
    cpu_usage_total: float = 0.0
    cpu_usage_cores: List[float] = field(default_factory=list)
    cpu_freq_mhz: float = 0.0
    # False si ni 'coretemp' (Intel) ni 'k10temp' (AMD) tienen sensores — cpu_temp_package
    # queda en un valor de relleno (no una lectura real) para no romper la UI.
    cpu_temp_available: bool = False

    # GPU
    gpu_name: str = ""
    gpu_temp_available: bool = False
    gpu_temp: float = 0.0
    gpu_usage: float = 0.0
    gpu_fan_speed: float = 0.0
    gpu_memory_used_mb: float = 0.0
    gpu_memory_total_mb: float = 0.0
    
    # Liquid Cooler / AIO
    liquid_temp: float = 0.0
    pump_rpm: int = 0
    liquid_temp_available: bool = False
    pump_rpm_available: bool = False
    
    # Motherboard Fans & PWM
    fans_rpm: Dict[str, int] = field(default_factory=dict)
    fan_channels: dict = field(default_factory=dict)
    fans_pwm: Dict[str, int] = field(default_factory=dict)
    # Descubrimiento de solo lectura de archivos pwm*/pwm*_enable, indexado por
    # identidad física de PWM (distinta de la identidad del ventilador en
    # fan_channels — nunca se asume que comparten índice). Solo pwm_writer.py
    # escribe en las rutas que aquí se reportan, y solo si el usuario probó y
    # confirmó ese canal explícitamente. Ver docs/PWM_REAL_CONTROL.md.
    pwm_channels: dict = field(default_factory=dict)
    # Descubrimiento de solo lectura de temp*_input, indexado por identidad
    # física (mismo patrón que fan_channels/pwm_channels). No restringido a
    # ningún chip: leer temperatura es seguro en cualquiera. Permite vincular
    # empíricamente una lectura sin etiqueta clara del fabricante a un rol
    # (p. ej. "Líquido / Refrigerante") vía apply_liquid_temp_mapping.
    temp_channels: dict = field(default_factory=dict)
    
    # NVMe / Storage
    nvme_temps: List[float] = field(default_factory=list)
    
    # Status
    corsair_connected: bool = False
    corsair_info: str = ""

    # PWM calculado y aplicado por el hilo de hardware para el perfil activo (ver
    # HardwareWorker.run) — se lleva aquí para que la UI solo lo muestre, sin volver
    # a calcularlo ni escribirlo desde el hilo principal.
    calculated_pwm: int = 0

    # True cuando liquid_temp es una ESTIMACIÓN térmica (no hay Corsair conectado
    # o su lectura de temperatura falló), no una medición real. La UI debe dejarlo
    # claro en vez de mostrarlo igual que un dato real.
    liquid_temp_is_estimated: bool = True


class HardwareSampler:
    """Clase de bajo nivel encargada de leer los sensores en Linux."""
    
    def __init__(self):
        self._usage_primed = False
        self._hwmon_map = self._scan_hwmon()
        self._has_nvidia = self._check_nvidia()
        self._amdgpu_hwmon, self._amdgpu_device_dir = self._scan_amdgpu()

    def _scan_hwmon(self) -> Dict[str, str]:
        mapping = {}
        for p in glob.glob('/sys/class/hwmon/hwmon*'):
            name_file = os.path.join(p, 'name')
            if os.path.exists(name_file):
                try:
                    with open(name_file, 'r') as f:
                        name = f.read().strip()
                        mapping[name] = p
                except Exception:
                    pass
        return mapping

    def _check_nvidia(self) -> bool:
        try:
            res = subprocess.run(["which", "nvidia-smi"], capture_output=True, text=True)
            return res.returncode == 0
        except Exception:
            return False

    # Chips validados por el usuario para escritura PWM real (v1). No generalizar
    # a "cualquier chip hwmon": nada fuera de esta lista se ha probado nunca sin
    # causar un apagado. Ver docs/PLAN_X99_Y_LCD.md y docs/PWM_REAL_CONTROL.md.
    PWM_WRITE_CAPABLE_CHIPS = ('it8792', 'it8620')

    def scan_pwm_channels(self) -> Dict[str, dict]:
        """Descubrimiento de solo lectura de pwm*/pwm*_enable, indexado por
        identidad física (distinta de la identidad del ventilador). Reutilizado
        cada ciclo por sample() y una sola vez al arrancar para detectar canales
        huérfanos en modo manual (ver PwmWriter.restore_stale_manual_channels)."""
        from algor.core.fan_mapping import channel_identity
        channels: Dict[str, dict] = {}
        for base_path in glob.glob('/sys/class/hwmon/hwmon*'):
            try:
                with open(os.path.join(base_path, 'name')) as f:
                    chip = f.read().strip()
            except OSError:
                continue
            if chip not in self.PWM_WRITE_CAPABLE_CHIPS:
                continue
            for pwm_file in sorted(glob.glob(os.path.join(base_path, 'pwm[0-9]'))):
                channel = os.path.basename(pwm_file)
                identity = channel_identity(base_path, chip, channel)
                if identity is None:
                    continue
                channels[identity] = {
                    'pwm_path': pwm_file,
                    'enable_path': pwm_file + '_enable',
                    'chip': chip,
                }
        return channels

    def scan_temp_channels(self) -> Dict[str, dict]:
        """Descubrimiento de solo lectura de temp*_input, en CUALQUIER chip (a
        diferencia de scan_pwm_channels: leer temperatura no escribe nada, no
        hay riesgo). Permite que el usuario vincule empíricamente una lectura
        sin etiqueta clara a un rol semántico vía el asistente de Ajustes."""
        from algor.core.fan_mapping import channel_identity
        channels: Dict[str, dict] = {}
        for base_path in glob.glob('/sys/class/hwmon/hwmon*'):
            try:
                with open(os.path.join(base_path, 'name')) as f:
                    chip = f.read().strip()
            except OSError:
                continue
            for temp_file in sorted(glob.glob(os.path.join(base_path, 'temp[0-9]*_input'))):
                channel = os.path.basename(temp_file)[:-len('_input')]
                identity = channel_identity(base_path, chip, channel)
                if identity is None:
                    continue
                label_file = temp_file[:-len('_input')] + '_label'
                label = None
                if os.path.exists(label_file):
                    try:
                        with open(label_file) as f:
                            label = f.read().strip() or None
                    except OSError:
                        pass
                temp_c = None
                try:
                    with open(temp_file) as f:
                        temp_c = int(f.read().strip()) / 1000.0
                except (OSError, ValueError):
                    pass
                channels[identity] = {
                    'label': label or f'{chip} / {channel}',
                    'temp': temp_c,
                }
        return channels

    def _scan_amdgpu(self) -> "tuple[Optional[str], Optional[str]]":
        """Ubica la primera GPU con driver 'amdgpu' vía sysfs (no requiere ROCm
        instalado, solo el driver de kernel de serie). Devuelve (ruta_hwmon,
        ruta_device) o (None, None) si no hay ninguna."""
        try:
            for card_path in sorted(glob.glob('/sys/class/drm/card[0-9]*')):
                driver_link = os.path.join(card_path, 'device', 'driver')
                try:
                    driver_name = os.path.basename(os.readlink(driver_link))
                except OSError:
                    continue
                if driver_name != 'amdgpu':
                    continue
                device_dir = os.path.join(card_path, 'device')
                hwmon_dirs = glob.glob(os.path.join(device_dir, 'hwmon', 'hwmon*'))
                if hwmon_dirs:
                    return hwmon_dirs[0], device_dir
        except Exception:
            pass
        return None, None

    def sample(self, corsair_reader=None) -> TelemetryData:
        data = TelemetryData()
        data.timestamp = time.time()
        
        # 1. CPU Telemetry
        try:
            # CPU Usage
            data.cpu_usage_total = psutil.cpu_percent(interval=None)
            data.cpu_usage_available = self._usage_primed and math.isfinite(data.cpu_usage_total) and 0 <= data.cpu_usage_total <= 100
            self._usage_primed = True
            data.cpu_usage_cores = psutil.cpu_percent(interval=None, percpu=True)
            freq = psutil.cpu_freq()
            if freq:
                data.cpu_freq_mhz = freq.current
        except Exception:
            pass

        # CPU Temperatures via psutil o sysfs.
        # 'coretemp' es Intel; en AMD el driver correspondiente es 'k10temp' y expone
        # etiquetas distintas ('Tdie'/'Tctl' en vez de 'Package'/'Core'), así que hay
        # que intentarlo aparte en vez de asumir que no hay temperatura disponible.
        try:
            temps = psutil.sensors_temperatures() if hasattr(psutil, 'sensors_temperatures') else {}
            coretemp_entries = [e for e in temps.get('coretemp', []) if e.current is not None and math.isfinite(e.current)]
            core_vals = []
            package_val = 0.0
            found_real_reading = False

            for entry in coretemp_entries:
                if 'Package' in entry.label:
                    package_val = entry.current
                elif 'Core' in entry.label:
                    core_vals.append(entry.current)

            if not core_vals and coretemp_entries:
                core_vals = [e.current for e in coretemp_entries]

            if coretemp_entries:
                found_real_reading = True
            else:
                # AMD: k10temp no expone temperaturas por núcleo, solo un par de
                # sensores del die/paquete completo. Se prefiere 'Tdie' (temperatura
                # real del die) sobre 'Tctl' (temperatura de control, con offset del
                # fabricante) si ambos están presentes.
                k10_entries = [e for e in temps.get('k10temp', []) if e.current is not None and math.isfinite(e.current)]
                if k10_entries:
                    found_real_reading = True
                    tdie = next((e.current for e in k10_entries if e.label == 'Tdie'), None)
                    tctl = next((e.current for e in k10_entries if e.label == 'Tctl'), None)
                    package_val = tdie if tdie is not None else (tctl if tctl is not None else k10_entries[0].current)
                    core_vals = [e.current for e in k10_entries]

            data.cpu_cores_temps = core_vals
            data.cpu_temp_package = package_val if package_val > 0 else (max(core_vals) if core_vals else 0.0)
            data.cpu_temp_max = max(core_vals) if core_vals else data.cpu_temp_package
            data.cpu_temp_available = found_real_reading
        except Exception:
            data.cpu_temp_package = 0.0
            data.cpu_temp_max = 0.0
            data.cpu_temp_available = False

        # 2. GPU Telemetry (NVIDIA)
        if self._has_nvidia:
            try:
                cmd = [
                    "nvidia-smi",
                    "--query-gpu=name,temperature.gpu,utilization.gpu,fan.speed,memory.used,memory.total",
                    "--format=csv,noheader,nounits"
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1.0)
                if proc.returncode == 0 and proc.stdout.strip():
                    parts = [p.strip() for p in proc.stdout.strip().split(',')]
                    if len(parts) >= 6:
                        data.gpu_name = parts[0]
                        data.gpu_temp = float(parts[1]) if parts[1].isdigit() else 0.0
                        data.gpu_temp_available = parts[1].isdigit()
                        data.gpu_usage = float(parts[2]) if parts[2].isdigit() else 0.0
                        data.gpu_fan_speed = float(parts[3]) if parts[3].isdigit() else 0.0
                        data.gpu_memory_used_mb = float(parts[4]) if parts[4].replace('.', '').isdigit() else 0.0
                        data.gpu_memory_total_mb = float(parts[5]) if parts[5].replace('.', '').isdigit() else 0.0
            except Exception:
                pass
        elif self._amdgpu_hwmon and self._amdgpu_device_dir:
            # GPU AMD vía sysfs directo (driver amdgpu de serie, sin necesitar ROCm).
            hwmon_dir: str = self._amdgpu_hwmon
            device_dir: str = self._amdgpu_device_dir
            try:
                data.gpu_name = "AMD GPU"
                temp_file = os.path.join(hwmon_dir, 'temp1_input')
                if os.path.exists(temp_file):
                    with open(temp_file, 'r') as f:
                        data.gpu_temp = int(f.read().strip()) / 1000.0
                        data.gpu_temp_available = math.isfinite(data.gpu_temp)

                busy_file = os.path.join(device_dir, 'gpu_busy_percent')
                if os.path.exists(busy_file):
                    with open(busy_file, 'r') as f:
                        data.gpu_usage = float(f.read().strip())

                vram_used_file = os.path.join(device_dir, 'mem_info_vram_used')
                vram_total_file = os.path.join(device_dir, 'mem_info_vram_total')
                if os.path.exists(vram_used_file) and os.path.exists(vram_total_file):
                    with open(vram_used_file, 'r') as f:
                        data.gpu_memory_used_mb = int(f.read().strip()) / (1024 * 1024)
                    with open(vram_total_file, 'r') as f:
                        data.gpu_memory_total_mb = int(f.read().strip()) / (1024 * 1024)

                pwm_file = os.path.join(hwmon_dir, 'pwm1')
                if os.path.exists(pwm_file):
                    with open(pwm_file, 'r') as f:
                        data.gpu_fan_speed = round((int(f.read().strip()) / 255.0) * 100, 1)
            except Exception:
                pass

        # 3. NVMe Temperatures
        try:
            nvme_entries = temps.get('nvme', [])
            data.nvme_temps = [e.current for e in nvme_entries if e.current is not None]
        except Exception:
            pass

        # 4. Motherboard fans: read-only discovery, including stable identities.
        fans_rpm = {}
        fans_pwm = {}
        from algor.core.fan_mapping import channel_identity
        # Rediscover fan chips to handle hwmon renumbering and reconnection.
        for base_path in glob.glob('/sys/class/hwmon/hwmon*'):
            try:
                with open(os.path.join(base_path, 'name')) as f:
                    chip = f.read().strip()
            except OSError:
                continue
            if base_path and os.path.isdir(base_path):
                # Read fan inputs
                for fan_file in sorted(glob.glob(os.path.join(base_path, 'fan*_input'))):
                    channel = os.path.basename(fan_file).split('_')[0]
                    identity = channel_identity(base_path, chip, channel)
                    if identity is not None:
                        data.fan_channels[identity] = {'label': f'{chip} / {channel}', 'rpm': None}
                    try:
                        fan_name = f"{chip}_{channel}"
                        with open(fan_file, 'r') as f:
                            val = int(f.read().strip())
                            if identity is not None:
                                data.fan_channels[identity]['rpm'] = val if val >= 0 else None
                            if val > 0 or fan_name not in fans_rpm:
                                fans_rpm[fan_name] = val
                    except Exception:
                        pass
                # Read PWM values
                for pwm_file in sorted(glob.glob(os.path.join(base_path, 'pwm[0-9]'))):
                    try:
                        pwm_name = f"{chip}_{os.path.basename(pwm_file)}"
                        with open(pwm_file, 'r') as f:
                            val = int(f.read().strip())
                            # Convert 0-255 to 0-100%
                            pct = int(round((val / 255.0) * 100))
                            fans_pwm[pwm_name] = pct
                    except Exception:
                        pass
        
        data.fans_rpm = fans_rpm
        data.fans_pwm = fans_pwm
        data.pwm_channels = self.scan_pwm_channels()
        data.temp_channels = self.scan_temp_channels()

        # Identificar el LCD no identifica sensores de líquido ni asigna la bomba.

        return data


class HardwareWorker(QThread):
    """Hilo de fondo en Qt que muestrea periódicamente la telemetría del sistema."""
    telemetry_updated = pyqtSignal(object)
    # Emitida cuando, al arrancar, se encuentra un canal probado que quedó en
    # modo manual por una sesión anterior que murió sin limpiar (ver
    # PwmWriter.restore_stale_manual_channels).
    stale_channel_restored = pyqtSignal(str)

    def __init__(self, corsair_reader=None, interval_ms: int = 1000,
                 fan_engine: Optional["FanCurveEngine"] = None,
                 pwm_writer: Optional["PwmWriter"] = None):
        super().__init__()
        self.sampler = HardwareSampler()
        self.corsair_reader = corsair_reader
        self.fan_engine = fan_engine
        self.pwm_writer = pwm_writer if pwm_writer is not None else PwmWriter()
        self.interval_sec = max(0.2, interval_ms / 1000.0)
        self._running = True
        self._stop_event = threading.Event()
        self._startup_pwm_checked = False
        self._pending_manual_pwm: Optional[int] = None

    def set_interval(self, interval_ms: int):
        self.interval_sec = max(0.2, interval_ms / 1000.0)

    def request_manual_pwm(self, value: int) -> None:
        """Pedido desde el hilo de la interfaz (botón "Aplicar" de Curvas); se
        aplica en el siguiente ciclo de este hilo, nunca desde la UI directamente."""
        self._pending_manual_pwm = value

    def request_channel_manual_pwm(self, pwm_identity: str, percent: float, enforce_floor: bool = True) -> bool:
        """Ajusta un canal específico de forma inmediata."""
        channels = self.sampler.scan_pwm_channels()
        ch = channels.get(pwm_identity)
        if ch:
            return self.pwm_writer.set_channel_manual(pwm_identity, ch, percent, enforce_floor=enforce_floor)
        return False

    def request_channel_auto(self, pwm_identity: str) -> bool:
        """Restaura un canal específico a automático."""
        channels = self.sampler.scan_pwm_channels()
        ch = channels.get(pwm_identity)
        if ch:
            return self.pwm_writer.set_channel_auto(pwm_identity, ch)
        return False

    def request_restore_all_auto(self) -> list:
        """Restaura todos los canales del sistema a automático de inmediato."""
        channels = self.sampler.scan_pwm_channels()
        return self.pwm_writer.restore_all_system_channels(channels)

    def run(self):
        while self._running:
            try:
                data = self.sampler.sample(self.corsair_reader)
                if not self._startup_pwm_checked:
                    self._startup_pwm_checked = True
                    restored = self.pwm_writer.restore_stale_manual_channels(
                        config.get('fan_mappings', {}), data.pwm_channels)
                    # Cubre también los canales que el Ajuste Rápido dejó en manual
                    # sin pasar por fan_mappings, si la sesión anterior murió sin
                    # avisar (ver PwmWriter.recover_from_previous_session).
                    for identity in self.pwm_writer.recover_from_previous_session():
                        if identity not in restored:
                            restored.append(identity)
                    if restored:
                        self.stale_channel_restored.emit(', '.join(restored))
                # Calcular y, si corresponde, aplicar el PWM aquí (hilo de hardware),
                # no en el hilo de la interfaz: es I/O de archivos bloqueante y no
                # tiene nada que hacer compitiendo con el dibujado de la ventana.
                if self.fan_engine is not None:
                    data.calculated_pwm = self.fan_engine.calculate_pwm(data.cpu_temp_package)
                    if getattr(self.fan_engine, 'real_control_enabled', False):
                        self.pwm_writer.apply(data.calculated_pwm, config.get('fan_mappings', {}), data.pwm_channels)
                if self._pending_manual_pwm is not None:
                    value, self._pending_manual_pwm = self._pending_manual_pwm, None
                    self.pwm_writer.apply_manual_override(value, config.get('fan_mappings', {}), data.pwm_channels)
                self.telemetry_updated.emit(data)
            except Exception as e:
                logger.error("Error en muestreo de telemetría: %s", e)
            self._stop_event.wait(self.interval_sec)

    def stop(self):
        self._running = False
        self._stop_event.set()
        self.wait()

