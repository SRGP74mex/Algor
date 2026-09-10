#!/bin/bash
# Regenera algor/locale/algor.pot desde todos los _("...") del código, y
# fusiona los mensajes nuevos/eliminados en cada traducción existente sin
# perder el trabajo ya hecho. Correr después de agregar o cambiar textos
# visibles. Requiere xgettext y msgmerge (paquete gettext, sin dependencias
# nuevas — ver docs/CONTRIBUTING.md).
set -euo pipefail
cd "$(dirname "$0")/.."

POT="algor/locale/algor.pot"
mkdir -p algor/locale

find algor -name '*.py' -print0 | sort -z | xargs -0 xgettext \
    --from-code=UTF-8 --language=Python --keyword=_ \
    --package-name=Algor --no-location --sort-output \
    -o "$POT"

for po in algor/locale/*/LC_MESSAGES/algor.po; do
    [ -f "$po" ] || continue
    msgmerge --update --backup=off --quiet "$po" "$POT"
    echo "Actualizado: $po"
done

echo "Plantilla regenerada: $POT"
echo "Para un idioma nuevo: mkdir -p algor/locale/<código>/LC_MESSAGES && cp $POT algor/locale/<código>/LC_MESSAGES/algor.po"
