#!/bin/bash
# Compila cada algor/locale/<código>/LC_MESSAGES/algor.po a su .mo binario,
# el formato que gettext realmente lee en tiempo de ejecución. Correr después
# de traducir o actualizar cualquier .po. Requiere msgfmt (paquete gettext).
set -euo pipefail
cd "$(dirname "$0")/.."

for po in algor/locale/*/LC_MESSAGES/algor.po; do
    [ -f "$po" ] || continue
    mo="${po%.po}.mo"
    msgfmt --check "$po" -o "$mo"
    echo "Compilado: $mo"
done
