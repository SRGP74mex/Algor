import importlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch


class I18nTests(unittest.TestCase):
    def _fresh_translation(self, language):
        """gettext.translation() se resuelve una sola vez al importar
        algor.core.i18n; para probar varios idiomas en el mismo proceso hay
        que recargar el módulo con la variable de entorno ya puesta."""
        import algor.core.i18n as i18n
        env = {'LANGUAGE': language} if language else {}
        with patch.dict(os.environ, env, clear=False):
            if not language:
                os.environ.pop('LANGUAGE', None)
                os.environ.pop('LC_ALL', None)
                os.environ.pop('LC_MESSAGES', None)
                os.environ.pop('LANG', None)
            importlib.reload(i18n)
            return i18n._

    def test_english_catalog_translates_known_strings(self):
        _ = self._fresh_translation('en')
        self.assertEqual(_('Bomba'), 'Pump')
        self.assertEqual(_('Guardar asignación'), 'Save assignment')
        self.assertEqual(_('CPU Uso: {value:.1f}%').format(value=42.0), 'CPU Usage: {value:.1f}%'.format(value=42.0))

    def test_unsupported_language_falls_back_to_spanish_source(self):
        # fallback=True: sin catálogo para el idioma detectado, devuelve el
        # texto original — español, porque ES el idioma fuente.
        _ = self._fresh_translation('xx')
        self.assertEqual(_('Bomba'), 'Bomba')
        self.assertEqual(_('Guardar asignación'), 'Guardar asignación')

    def test_no_language_env_falls_back_to_spanish_source(self):
        _ = self._fresh_translation(None)
        self.assertEqual(_('Bomba'), 'Bomba')

    def test_compiled_english_catalog_exists(self):
        mo_path = Path(__file__).resolve().parents[1] / 'algor' / 'locale' / 'en' / 'LC_MESSAGES' / 'algor.mo'
        self.assertTrue(mo_path.is_file(), f'Falta compilar: {mo_path} (ver scripts/i18n_compile.sh)')


if __name__ == '__main__':
    unittest.main()
