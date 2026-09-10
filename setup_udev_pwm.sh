#!/bin/bash
# Permiso de escritura PWM real, SOLO para it8792/it8620 (los chips de este
# equipo, los únicos alguna vez probados sin causar un apagado). Grupo
# dedicado, no chmod 0666: ningún otro proceso del sistema queda con acceso.
# El alcance de este permiso es más amplio que lo que Algor realmente usa —
# la barrera real es la elegibilidad por canal en el propio código
# (fan_mapping.eligible_for_pwm_write). Ver docs/PWM_REAL_CONTROL.md.
set -euo pipefail

export PATH=/usr/sbin:/usr/bin:/sbin:/bin
RULE_FILE="/etc/udev/rules.d/71-algor-pwm.rules"
GROUP_NAME="algor-pwm"

PWM_CHANNELS_IT8792="pwm1 pwm1_enable pwm2 pwm2_enable pwm3 pwm3_enable"
PWM_CHANNELS_IT8620="pwm1 pwm1_enable pwm2 pwm2_enable pwm3 pwm3_enable pwm4 pwm4_enable pwm5 pwm5_enable"

print_rules() {
    local it8792_paths it8620_paths
    it8792_paths=""
    for f in $PWM_CHANNELS_IT8792; do it8792_paths+=" /sys%p/$f"; done
    it8620_paths=""
    for f in $PWM_CHANNELS_IT8620; do it8620_paths+=" /sys%p/$f"; done
    cat <<RULES
# Algor: escritura PWM solo para it8792/it8620, solo grupo ${GROUP_NAME}.
# Más amplio que lo que la app usa; la elegibilidad real vive en su código.
SUBSYSTEM=="hwmon", ACTION=="add", ATTR{name}=="it8792", RUN+="/bin/chgrp ${GROUP_NAME}${it8792_paths}", RUN+="/bin/chmod g+w${it8792_paths}"
SUBSYSTEM=="hwmon", ACTION=="add", ATTR{name}=="it8620", RUN+="/bin/chgrp ${GROUP_NAME}${it8620_paths}", RUN+="/bin/chmod g+w${it8620_paths}"
RULES
}

if [[ "${1:-}" == "--print-rules" && $# -eq 1 ]]; then
    print_rules
    exit 0
fi
if [[ $# -ne 0 ]]; then
    echo "Uso: sudo bash ./setup_udev_pwm.sh | bash ./setup_udev_pwm.sh --print-rules" >&2
    exit 2
fi
if [[ $EUID -ne 0 ]]; then
    echo "Ejecuta: sudo bash ./setup_udev_pwm.sh (o usa el botón de la aplicación)." >&2
    exit 1
fi
command -v udevadm >/dev/null

# Determinar el usuario real que invocó (pkexec/sudo), no root.
TARGET_USER="${PKEXEC_UID:+$(id -un "$PKEXEC_UID" 2>/dev/null || true)}"
if [[ -z "$TARGET_USER" ]]; then
    TARGET_USER="${SUDO_USER:-}"
fi
if [[ -z "$TARGET_USER" ]]; then
    TARGET_USER="$(logname 2>/dev/null || true)"
fi
if [[ -z "$TARGET_USER" ]]; then
    echo "No se pudo determinar el usuario a añadir al grupo ${GROUP_NAME}." >&2
    exit 1
fi

if ! getent group "$GROUP_NAME" >/dev/null; then
    groupadd --system "$GROUP_NAME"
fi
usermod -aG "$GROUP_NAME" "$TARGET_USER"

if [[ -L "$RULE_FILE" || ( -e "$RULE_FILE" && ! -f "$RULE_FILE" ) ]]; then
    echo "Destino no regular; revisa $RULE_FILE antes de instalar." >&2
    exit 1
fi
install -d -o root -g root -m 0755 /etc/udev/rules.d
TEMP_RULE=$(mktemp /etc/udev/rules.d/.algor-pwm-rules.XXXXXX)
trap 'rm -f -- "$TEMP_RULE"' EXIT
print_rules > "$TEMP_RULE"
chown root:root "$TEMP_RULE"
chmod 0644 "$TEMP_RULE"
mv -fT -- "$TEMP_RULE" "$RULE_FILE"

if ! udevadm control --reload-rules; then
    echo "Regla guardada, pero udev no pudo recargarla. Reinicia el equipo para aplicarla." >&2
    exit 1
fi
# Reaplica sin reiniciar: los hwmon ya existentes no reciben ACTION=="add" de nuevo
# salvo que se les vuelva a disparar explícitamente.
udevadm trigger --action=add --subsystem-match=hwmon || true

echo "Permiso de grupo ${GROUP_NAME} instalado para pwm*/pwm*_enable de it8792/it8620."
echo "Usuario ${TARGET_USER} añadido al grupo. Cierra sesión y vuelve a entrar para que"
echo "se aplique tu pertenencia al grupo. Esto NO activa Reactivo por sí solo."
