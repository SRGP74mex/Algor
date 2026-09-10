#!/bin/bash
# Instalación local de Algor: dependencias de sistema, entorno virtual,
# paquetes Python y acceso de escritorio — automatiza exactamente los pasos
# manuales que ya documenta el README, nada más. No detecta "cualquier
# distro": los nombres de paquete abajo están confirmados en Debian/Ubuntu
# (ya probado) y son un ESTIMADO por confirmar en el resto — precisamente lo
# que este script existe para validar en Ubuntu, Mint, Zorin, Manjaro y
# Fedora antes de anunciar soporte real en ningún doc público.
#
# No instala Python en sí (se asume 3.10–3.13 ya presente, como en el resto
# del proyecto) ni ejecuta nada como root salvo el propio paso de paquetes
# de sistema, que sí requiere sudo.
set -euo pipefail
cd "$(dirname "$0")"

log() { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[1;31mFalló: %s\033[0m\n' "$1" >&2; exit 1; }

if [[ $EUID -eq 0 ]]; then
    fail "No ejecutes este script como root; te pedirá sudo solo para el paso que lo necesita."
fi

# ---------------------------------------------------------------------------
# 1. Detección de distro y paquetes de sistema
# ---------------------------------------------------------------------------
DISTRO_ID=""
DISTRO_LIKE=""
if [[ -r /etc/os-release ]]; then
    . /etc/os-release
    DISTRO_ID="${ID:-}"
    DISTRO_LIKE="${ID_LIKE:-}"
fi

PKG_MANAGER=""
SYSTEM_PACKAGES=()
STATUS_NOTE=""

case "$DISTRO_ID $DISTRO_LIKE" in
    *debian*|*ubuntu*)
        # Confirmado en Debian 13. Ubuntu/Mint/Zorin comparten apt y este mismo
        # árbol de paquetes — por confirmar en esta corrida.
        PKG_MANAGER="apt"
        SYSTEM_PACKAGES=(python3-venv libusb-1.0-0 libegl1 libopengl0 libxcb-cursor0)
        STATUS_NOTE="confirmado en Debian 13; Ubuntu/Mint/Zorin por confirmar"
        ;;
    *fedora*)
        # ESTIMADO, sin confirmar todavía: Fedora ya incluye el módulo venv en
        # python3 (no separa el paquete como Debian), libusb se llama libusbx.
        PKG_MANAGER="dnf"
        SYSTEM_PACKAGES=(python3-pip libusbx mesa-libEGL mesa-libGL xcb-util-cursor)
        STATUS_NOTE="ESTIMADO, sin confirmar — repórtalo si algún nombre de paquete falla"
        ;;
    *arch*|*manjaro*)
        # ESTIMADO, sin confirmar todavía: Arch/Manjaro también traen venv
        # integrado en el paquete python.
        PKG_MANAGER="pacman"
        SYSTEM_PACKAGES=(python-pip libusb libxcb xcb-util-cursor)
        STATUS_NOTE="ESTIMADO, sin confirmar — repórtalo si algún nombre de paquete falla"
        ;;
    *)
        PKG_MANAGER=""
        ;;
esac

log "Distro detectada: ID=${DISTRO_ID:-desconocido} ID_LIKE=${DISTRO_LIKE:-ninguno}"

if [[ -z "$PKG_MANAGER" ]]; then
    echo "No se reconoció el gestor de paquetes. Instala manualmente el equivalente a:"
    echo "  python3-venv (o venv integrado), libusb 1.0, EGL/OpenGL de Mesa, xcb-util-cursor"
    echo "y vuelve a ejecutar este script — seguirá con el venv y las dependencias Python."
else
    echo "Gestor de paquetes: $PKG_MANAGER ($STATUS_NOTE)"
    echo "Paquetes a instalar: ${SYSTEM_PACKAGES[*]}"
    log "Instalando dependencias de sistema (pedirá sudo)"
    case "$PKG_MANAGER" in
        apt)
            sudo apt update && sudo apt install -y "${SYSTEM_PACKAGES[@]}" \
                || fail "apt install — revisa si algún nombre de paquete cambió en esta versión"
            ;;
        dnf)
            sudo dnf install -y "${SYSTEM_PACKAGES[@]}" \
                || fail "dnf install — nombres de paquete Fedora sin confirmar, corrige y reporta"
            ;;
        pacman)
            sudo pacman -S --needed --noconfirm "${SYSTEM_PACKAGES[@]}" \
                || fail "pacman -S — nombres de paquete Arch/Manjaro sin confirmar, corrige y reporta"
            ;;
    esac
fi

# ---------------------------------------------------------------------------
# 2. Entorno virtual y dependencias Python (nunca como root)
# ---------------------------------------------------------------------------
log "Creando entorno virtual (.venv)"
if [[ -d .venv ]]; then
    echo ".venv ya existe, se reutiliza."
else
    python3 -m venv .venv || fail "python3 -m venv .venv — ¿falta el paquete venv de tu distro?"
fi

log "Instalando dependencias Python"
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt || fail "pip install -r requirements.txt"
.venv/bin/python -m pip check || fail "pip check — dependencias inconsistentes"

# ---------------------------------------------------------------------------
# 3. Acceso de escritorio (usa el intérprete del venv recién creado)
# ---------------------------------------------------------------------------
log "Instalando acceso de escritorio"
.venv/bin/python scripts/install_desktop.py || fail "scripts/install_desktop.py"

log "Instalación completa"
echo "Prueba primero sin hardware:  .venv/bin/python scripts/smoke_test.py"
echo "Luego ejecuta la app:         .venv/bin/python main.py"
echo "Permisos del LCD Cap: Ajustes → Instalar permisos del LCD Cap (dentro de la app)."
