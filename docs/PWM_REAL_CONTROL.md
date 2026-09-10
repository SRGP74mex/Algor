# Control real de PWM (Reactivo)

## Base física

El 2026-09-09 el usuario verificó manualmente, con el equipo a la vista y en
tres pasos (100% → 15% → automático, 15 s cada tramo, vía `sudo tee` directo a
sysfs), que el canal `it8792/pwm2` de su Gigabyte X99 UD5 controla el grupo de
ventiladores del radiador **sin causar ningún apagado**. Es el primer y único
canal de esta placa alguna vez confirmado seguro para escritura PWM real —
ver la enmienda en [PLAN_X99_Y_LCD.md](PLAN_X99_Y_LCD.md) y el hallazgo
original en [FAN_MAPPING.md](FAN_MAPPING.md).

Importante: el radiador tiene 5 ventiladores compartiendo una sola lectura de
RPM a través de un distribuidor. Confirmar visualmente que uno responde no
confirma automáticamente que los 5 lo hagan — solo que el canal, como grupo,
está bajo control real.

## Qué hace Reactivo y qué no

- **Automático** (por defecto, siempre al arrancar): exactamente el comportamiento
  histórico de Algor — las curvas se calculan y se muestran, nunca se escriben.
- **Reactivo** (opt-in, nunca persiste entre reinicios): aplica la curva activa
  (Silencioso/Equilibrado/Extremo/Personalizado) a los canales que hayas probado
  y confirmado uno por uno en **Ajustes → Identificar bomba y ventiladores**.
- **La bomba nunca es candidata**, en ningún modo. La exclusión vive en
  `fan_mapping.normalize_mapping()` — es estructural, no una casilla que se
  pueda desmarcar por error.
- Solo los chips `it8792`/`it8620` son elegibles en esta versión — los únicos
  de este equipo, el único hardware alguna vez probado. No se generaliza a
  "cualquier chip hwmon".

## Piso de protección: 30%

Ningún canal gestionado por Reactivo recibe nunca menos de 30% de PWM,
sin importar la curva activa ni un error al editarla — cercano a lo que la
propia BIOS de este equipo ya usa en reposo (~27%). Vive en un único punto
(`algor/core/pwm_writer.py:PROTECTION_FLOOR_PERCENT`), nunca en el cálculo de
la curva en sí, para que Automático siga mostrando la simulación real sin
recortar.

## Prueba guiada

`Ajustes → Identificar bomba y ventiladores → 🧪 Probar control PWM real`
formaliza exactamente la secuencia que el usuario ya validó a mano: 100% por
15 s, 15% por 15 s, restauración garantizada al valor original en un `finally`
(alcanzado también al abortar o cerrar el diálogo). Un canal a la vez, nunca
automático al abrir, nunca en lote. Deshabilitada por completo para la bomba.

## Permisos

Grupo dedicado del sistema (`algor-pwm`), no `chmod 0666` — instalado vía
`setup_udev_pwm.sh` con el mismo patrón de `pkexec` que el permiso USB del
LCD. Requiere cerrar sesión una vez tras instalarlo. El alcance de este
permiso (escritura sobre *todos* los `pwm*`/`pwm*_enable` de `it8792`/`it8620`)
es intencionalmente más amplio que lo que Algor realmente usa — la barrera
real es la elegibilidad por canal en el código
(`fan_mapping.eligible_for_pwm_write`), no el permiso del sistema operativo.

## Red de seguridad y su límite honesto

Hasta esta función, el proyecto no tenía ningún manejador de señal ni
`atexit` — un `kill -9` no ejecutaba ninguna limpieza. Ahora:

- `main.py` maneja `SIGINT`/`SIGTERM` llamando a `QApplication.quit()`, que
  dispara el cierre limpio existente (`_clean_exit`).
- `_clean_exit` restaura a automático todo canal gestionado antes de detener
  el hilo de hardware.
- `pwm_writer.py` registra un `atexit` a nivel de módulo como última red,
  independiente de que Qt siga vivo.
- Al arrancar, si un canal probado aparece en modo manual (`pwm_enable=1`),
  se asume que la sesión anterior murió sin limpiar y se restaura a automático
  antes de hacer cualquier otra cosa (`PwmWriter.restore_stale_manual_channels`).

**Lo que esto NO cubre, declarado sin rodeos**: un `kill -9` combinado con un
corte de energía en el instante exacto, o un OOM-kill del kernel, pueden dejar
un canal en modo manual hasta el próximo arranque de Algor (que lo detecta y
corrige) o hasta reiniciar el equipo. El piso de 30% acota ese peor caso a
"ventilador a velocidad moderada" — no lo elimina. Esta limitación es
deliberadamente visible aquí, no oculta.

## Alcance de las pruebas automatizadas

Las pruebas unitarias (`tests/test_pwm_writer.py`, `tests/test_hardware.py`,
extensiones a `tests/test_fan_mapping.py` y `tests/test_fan_controller.py`)
cubren elegibilidad, piso, restauración y orquestación del hilo de hardware
— todas contra sysfs simulado, nunca contra hardware real. Ninguna prueba
automatizada certifica que un canal específico sea seguro de escribir en una
placa física: esa certificación solo la da la prueba guiada, hecha por una
persona, con el equipo a la vista.
