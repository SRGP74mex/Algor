#!/bin/bash
# Acceso de la sesión local al LCD Cap; no habilita control PWM de la placa.
set -euo pipefail

# PATH fijo: el instalador se ejecuta con privilegios administrativos.
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
RULE_FILE="/etc/udev/rules.d/70-corsair-algor.rules"

print_rules() {
    cat <<'RULES'
# Algor: solo CORSAIR Nautilus LCD Cap 1b1c:0c57.
# PyUSB usa usb_device; no se concede acceso hidraw ni a otros productos Corsair.
# uaccess asigna ACL a la sesión local activa mediante systemd-logind.
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="1b1c", ATTR{idProduct}=="0c57", OWNER="root", GROUP="root", MODE="0660", TAG+="uaccess"
RULES
}

if [[ "${1:-}" == "--print-rules" && $# -eq 1 ]]; then
    print_rules
    exit 0
fi
if [[ $# -ne 0 ]]; then
    echo "Uso: sudo bash ./setup_udev.sh | bash ./setup_udev.sh --print-rules" >&2
    exit 2
fi
if [[ $EUID -ne 0 ]]; then
    echo "Ejecuta: sudo bash ./setup_udev.sh (o usa el botón de la aplicación)." >&2
    exit 1
fi
command -v udevadm >/dev/null

# Reemplazo atómico del archivo anterior, incluidas sus reglas amplias.
# No seguir enlaces simbólicos ni sobrescribir un archivo especial.
if [[ -L "$RULE_FILE" || ( -e "$RULE_FILE" && ! -f "$RULE_FILE" ) ]]; then
    echo "Destino no regular; revisa $RULE_FILE antes de instalar." >&2
    exit 1
fi
install -d -o root -g root -m 0755 /etc/udev/rules.d
TEMP_RULE=$(mktemp /etc/udev/rules.d/.algor-rules.XXXXXX)
trap 'rm -f -- "$TEMP_RULE"' EXIT
print_rules > "$TEMP_RULE"
chown root:root "$TEMP_RULE"
chmod 0644 "$TEMP_RULE"
mv -fT -- "$TEMP_RULE" "$RULE_FILE"

if ! udevadm control --reload-rules; then
    echo "Regla guardada, pero udev no pudo recargarla. Reinicia el equipo para aplicarla." >&2
    exit 1
fi
# No disparar eventos globales ni desconectar/reconfigurar dispositivos activos.
echo "Regla instalada para el LCD Cap 1b1c:0c57. No habilita PWM, voltajes ni control de bomba."
echo "Reinicia el equipo para aplicar permisos y retirar los permisos amplios anteriores"
echo "de los nodos USB/hidraw ya existentes. No desconectes cables internos con el equipo encendido."
echo "El acceso corresponde a la sesión local activa; no se habilita acceso remoto ni servicios."
