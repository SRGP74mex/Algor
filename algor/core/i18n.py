"""Internacionalización con gettext (biblioteca estándar, sin dependencias
nuevas). El idioma se detecta por el locale del sistema (LANGUAGE/LC_ALL/
LC_MESSAGES/LANG, en ese orden — el mismo mecanismo que usa cualquier
programa Unix), sin selector manual por ahora.

El español es el idioma fuente: no existe catálogo es.po porque no hace
falta — con fallback=True, gettext devuelve el texto original tal cual
cuando no encuentra un catálogo para el idioma detectado.

Uso en cada archivo de UI: `from algor.core.i18n import _`, nunca instalar
`_` como builtin global (mantiene explícito de dónde viene, como el resto
del proyecto).
"""
import gettext
from pathlib import Path

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"

_translation = gettext.translation(
    "algor", localedir=str(_LOCALE_DIR), languages=None, fallback=True
)

_ = _translation.gettext
