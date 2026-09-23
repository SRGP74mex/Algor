"""Único módulo del proyecto que escribe archivos pwm*/pwm*_enable de hwmon.

Todo lo demás en la app es lectura o simulación (ver fan_controller.py). Esto
existe porque el usuario verificó manualmente, canal por canal y con el equipo
a la vista, que un canal específico responde sin causar apagados — ver
docs/PWM_REAL_CONTROL.md. La elegibilidad (fan_mapping.eligible_for_pwm_write)
es la barrera real; el permiso udev es deliberadamente más amplio que lo que
esta clase realmente usa.

Límite honesto: nada aquí protege contra un `kill -9` combinado con corte de
energía en el instante exacto, ni contra un OOM-kill del kernel. El piso de
protección acota el peor caso a "ventilador a velocidad moderada", no lo
elimina — ver PROTECTION_FLOOR_PERCENT.
"""
import atexit
import json
from pathlib import Path
from typing import Callable, Dict, Optional

from algor.core.fan_mapping import eligible_for_pwm_write, normalize_mapping
from algor.core.logging_config import get_logger

logger = get_logger("pwm_writer")

# Nunca escribir menos que esto en operación continua (curvas), sin importar el
# perfil activo. Cercano a lo que la propia BIOS de este equipo ya usa en reposo
# (~27%, visto como pwm=70/255 antes de cualquier prueba). No es configurable
# por el usuario: es un límite de diseño, no una preferencia.
PROTECTION_FLOOR_PERCENT = 30

AUTO_ENABLE_VALUE = 2
MANUAL_ENABLE_VALUE = 1


def percent_to_raw(percent: float) -> int:
    return max(0, min(255, round(percent / 100.0 * 255)))


def raw_to_percent(raw: int) -> float:
    return max(0.0, min(100.0, round((raw / 255.0) * 100, 1)))


def _default_write(path: str, value: str) -> None:
    with open(path, "w") as f:
        f.write(str(value))


def _default_read(path: str) -> Optional[str]:
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except OSError:
        return None


class PwmWriter:
    """Escribe PWM real solo en canales elegibles, con piso de protección y
    restauración garantizada. `write_file`/`read_file` son inyectables para que
    los tests nunca toquen sysfs real (mismo patrón que HardwareSampler)."""

    def __init__(self, write_file: Callable[[str, str], None] = _default_write,
                 read_file: Callable[[str], Optional[str]] = _default_read,
                 state_path: Optional[Path] = None):
        self._write = write_file
        self._read = read_file
        # identity -> {'enable_path', 'pwm_path', 'original_enable', 'original_pwm', 'last_value'}
        self._managed: Dict[str, dict] = {}
        # Espejo en disco de qué identidades están en _managed ahora mismo, para
        # poder recuperarlas en el próximo arranque si el proceso muere sin
        # avisar (crash, kill -9) — ver recover_from_previous_session().
        self._state_path = state_path or (Path.home() / ".config" / "algor" / "manual_pwm_state.json")

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            payload = {identity: state['enable_path'] for identity, state in self._managed.items()}
            tmp = self._state_path.with_suffix(self._state_path.suffix + '.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(payload, f)
            tmp.replace(self._state_path)
        except OSError as e:
            logger.error("No se pudo guardar el estado de canales manuales: %s", e)

    def _take_control(self, identity: str, channel: dict) -> Optional[dict]:
        state = self._managed.get(identity)
        if state is not None:
            return state
        pwm_path = channel.get('pwm_path')
        enable_path = channel.get('enable_path')
        if not pwm_path or not enable_path:
            return None
        original_enable = self._read(enable_path)
        original_pwm = self._read(pwm_path)
        try:
            self._write(enable_path, str(MANUAL_ENABLE_VALUE))
        except OSError as e:
            logger.error("No se pudo tomar control manual de %s: %s", enable_path, e)
            return None
        state = dict(enable_path=enable_path, pwm_path=pwm_path,
                     original_enable=original_enable, original_pwm=original_pwm,
                     last_value=None)
        self._managed[identity] = state
        self._save_state()
        return state

    def _write_clamped(self, state: dict, percent: float) -> None:
        target = max(PROTECTION_FLOOR_PERCENT, min(100, percent))
        raw = percent_to_raw(target)
        if state['last_value'] == raw:
            return
        try:
            self._write(state['pwm_path'], str(raw))
            state['last_value'] = raw
        except OSError as e:
            logger.error("Fallo al escribir %s: %s", state['pwm_path'], e)

    def apply(self, calculated_pwm: int, fan_mappings: dict, pwm_channels: dict) -> None:
        """Aplica la curva activa a todo canal elegible. Nunca toca nada que no
        haya pasado eligible_for_pwm_write — ni la bomba, ni un canal sin probar.

        `pwm_channels` está indexado por identidad de PWM (p. ej. 'it8792@.../pwm2'),
        NUNCA se asume igual a la identidad del ventilador (fan_mappings está
        indexado por identidad de ventilador) — la correspondencia la fija
        explícitamente el usuario en la prueba guiada, vía mapping['pwm_channel']."""
        for fan_identity, raw_mapping in fan_mappings.items():
            if not eligible_for_pwm_write(raw_mapping):
                continue
            pwm_identity = normalize_mapping(raw_mapping)['pwm_channel']
            channel = pwm_channels.get(pwm_identity)
            if channel is None:
                continue
            state = self._take_control(pwm_identity, channel)
            if state is not None:
                self._write_clamped(state, calculated_pwm)

    def apply_manual_override(self, pwm_percent: int, fan_mappings: dict, pwm_channels: dict) -> None:
        """Escritura puntual (botón "Aplicar" de Curvas), mismas reglas que apply()."""
        self.apply(pwm_percent, fan_mappings, pwm_channels)

    def set_channel_manual(self, identity: str, channel: dict, percent: float, enforce_floor: bool = True) -> bool:
        """Fija directamente un valor de PWM en modo manual para un canal específico."""
        state = self._take_control(identity, channel)
        if state is None:
            return False
        floor = PROTECTION_FLOOR_PERCENT if enforce_floor else 0
        target = max(floor, min(100, percent))
        raw = percent_to_raw(target)
        try:
            self._write(state['pwm_path'], str(raw))
            state['last_value'] = raw
            return True
        except OSError as e:
            logger.error("Fallo al escribir %s: %s", state['pwm_path'], e)
            return False

    def set_channel_auto(self, identity: str, channel: dict) -> bool:
        """Devuelve un canal específico al modo automático de la BIOS (enable=2)."""
        enable_path = channel.get('enable_path')
        if not enable_path:
            return False
        try:
            self._write(enable_path, str(AUTO_ENABLE_VALUE))
            self._managed.pop(identity, None)
            self._save_state()
            return True
        except OSError as e:
            logger.error("No se pudo restaurar canal %s a automático: %s", enable_path, e)
            return False

    def restore_all(self, pwm_channels: Optional[dict] = None) -> None:
        """Restaura a automático todo canal que esta instancia haya gestionado.
        Best-effort e idempotente: seguro de llamar desde _clean_exit, un manejador
        de señal, o atexit, cuantas veces haga falta."""
        if pwm_channels:
            for identity, channel in pwm_channels.items():
                enable_path = channel.get('enable_path')
                if enable_path:
                    try:
                        self._write(enable_path, str(AUTO_ENABLE_VALUE))
                    except OSError:
                        pass
        for identity, state in list(self._managed.items()):
            try:
                self._write(state['enable_path'], str(AUTO_ENABLE_VALUE))
            except OSError as e:
                logger.error("No se pudo restaurar %s a automático: %s", state['enable_path'], e)
            finally:
                self._managed.pop(identity, None)
        self._save_state()

    def restore_all_system_channels(self, pwm_channels: Optional[dict] = None) -> list:
        """Barrido incondicional: devuelve a automático (pwm_enable=2) TODOS los canales
        descubiertos en el sistema, no solo los que estén en _managed. Idempotente y seguro."""
        restored = []
        if pwm_channels:
            for identity, channel in pwm_channels.items():
                enable_path = channel.get('enable_path')
                if not enable_path:
                    continue
                try:
                    self._write(enable_path, str(AUTO_ENABLE_VALUE))
                    restored.append(identity)
                except OSError as e:
                    logger.error("No se pudo restaurar canal %s a automático: %s", enable_path, e)
        # Limpiar también cualquier registro remanente en _managed
        self.restore_all()
        return restored

    def restore_stale_manual_channels(self, fan_mappings: dict, pwm_channels: dict) -> list:
        """Al arrancar: si un canal ya probado quedó en modo manual (pwm_enable=1)
        porque la sesión anterior murió sin limpiar, lo regresa a automático antes
        de que la app haga cualquier otra cosa. Devuelve las identidades restauradas."""
        restored = []
        for fan_identity, raw_mapping in fan_mappings.items():
            if not eligible_for_pwm_write(raw_mapping):
                continue
            pwm_identity = normalize_mapping(raw_mapping)['pwm_channel']
            channel = pwm_channels.get(pwm_identity)
            if channel is None:
                continue
            enable_path = channel.get('enable_path')
            if not enable_path:
                continue
            current = self._read(enable_path)
            if current is not None and current.strip() == str(MANUAL_ENABLE_VALUE):
                try:
                    self._write(enable_path, str(AUTO_ENABLE_VALUE))
                    restored.append(pwm_identity)
                except OSError as e:
                    logger.error("No se pudo restaurar canal huérfano %s: %s", enable_path, e)
        return restored

    def recover_from_previous_session(self) -> list:
        """Al arrancar: si el proceso anterior murió sin avisar (crash, `kill -9`)
        mientras tenía canales en modo manual, los devuelve a automático — incluidos
        los que el Ajuste Rápido puso en manual sin pasar por fan_mappings, que
        restore_stale_manual_channels() no puede ver.

        Solo actúa sobre identidades que ESTE programa recuerda haber puesto él
        mismo en manual (leídas de _state_path, escrito por _save_state() en cada
        cambio de _managed) — nunca sobre hwmon de otras herramientas, a
        diferencia de un barrido incondicional del sistema."""
        restored = []
        try:
            if not self._state_path.exists():
                return restored
            with open(self._state_path, 'r', encoding='utf-8') as f:
                pending = json.load(f)
        except (OSError, ValueError) as e:
            logger.error("No se pudo leer el estado de canales manuales previo: %s", e)
            return restored
        for identity, enable_path in pending.items():
            current = self._read(enable_path)
            if current is not None and current.strip() == str(MANUAL_ENABLE_VALUE):
                try:
                    self._write(enable_path, str(AUTO_ENABLE_VALUE))
                    restored.append(identity)
                except OSError as e:
                    logger.error("No se pudo restaurar canal huérfano %s: %s", enable_path, e)
        try:
            self._state_path.unlink(missing_ok=True)
        except OSError:
            pass
        return restored


# Red de seguridad a nivel de módulo: corre aunque Qt ya no exista al salir del
# intérprete. En tests, si nunca se llamó apply()/apply_manual_override(),
# _managed está vacío y esto es un no-op seguro. Deliberadamente acotado a lo
# que ESTA instancia gestionó — nunca un barrido de todo hwmon del sistema,
# que pisaría configuraciones manuales de otras herramientas ajenas a Algor.
_global_writer = PwmWriter()
atexit.register(_global_writer.restore_all)
