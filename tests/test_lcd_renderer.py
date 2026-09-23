import math
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from algor.core.lcd_renderer import (
    LCDRenderer, normalize_settings, scaled_font_size, LCD_CANVAS_SIZE,
    LCD_TITLE_FONT_SIZE_DUAL_MIN, LCD_TITLE_FONT_SIZE_DUAL_MAX,
    LCD_VALUE_FONT_SIZE_DUAL_MIN, LCD_VALUE_FONT_SIZE_DUAL_MAX,
    LCD_TITLE_FONT_SIZE_SINGLE_MIN, LCD_TITLE_FONT_SIZE_SINGLE_MAX,
    LCD_VALUE_FONT_SIZE_SINGLE_MIN, LCD_VALUE_FONT_SIZE_SINGLE_MAX,
)

FONT_PATH = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
# Mismo círculo que dibuja el renderer: ellipse((25,25,455,455), width=8).
RING_RADIUS = (455 - 25) / 2
SAFE_MARGIN_PX = 20  # separación mínima deseada contra el borde físico de la pantalla


def max_safe_text_width(dy: float) -> float:
    """Ancho máximo (cuerda) disponible en la fila a distancia vertical `dy`
    del centro del círculo, con margen de seguridad contra el borde físico."""
    return 2 * math.sqrt(max(0, RING_RADIUS ** 2 - dy ** 2)) - SAFE_MARGIN_PX


class ScaledFontSizeTests(unittest.TestCase):
    def test_zero_scale_returns_minimum(self):
        self.assertEqual(scaled_font_size(21, 27, 0), 21)

    def test_full_scale_returns_maximum(self):
        self.assertEqual(scaled_font_size(21, 27, 100), 27)

    def test_midpoint_interpolates(self):
        self.assertEqual(scaled_font_size(20, 40, 50), 30)


class NormalizeSettingsTextScaleTests(unittest.TestCase):
    def test_defaults_to_original_harmonic_size(self):
        self.assertEqual(normalize_settings({})['text_scale'], 0)

    def test_out_of_range_values_are_clamped(self):
        self.assertEqual(normalize_settings({'text_scale': 500})['text_scale'], 100)
        self.assertEqual(normalize_settings({'text_scale': -50})['text_scale'], 0)

    def test_invalid_value_falls_back_to_default(self):
        self.assertEqual(normalize_settings({'text_scale': 'grande'})['text_scale'], 0)


class LCDRendererSmokeTests(unittest.TestCase):
    def test_render_dual_reading_produces_valid_square_jpeg(self):
        renderer = LCDRenderer()
        settings = dict(mode='cpu_temp', show_temperature=True, show_usage=True, text_scale=100)
        jpeg = renderer.render(settings, cpu_temp=100.0, cpu_usage=100)
        image = Image.open(BytesIO(jpeg))
        self.assertEqual(image.size, (LCD_CANVAS_SIZE, LCD_CANVAS_SIZE))

    def test_render_single_reading_produces_valid_square_jpeg(self):
        renderer = LCDRenderer()
        settings = dict(mode='cpu_temp', show_temperature=True, show_usage=False, text_scale=50)
        jpeg = renderer.render(settings, cpu_temp=-10.0)
        image = Image.open(BytesIO(jpeg))
        self.assertEqual(image.size, (LCD_CANVAS_SIZE, LCD_CANVAS_SIZE))

    def test_render_no_readings_still_produces_valid_jpeg(self):
        renderer = LCDRenderer()
        settings = dict(mode='cpu_temp', show_temperature=False, show_usage=False)
        jpeg = renderer.render(settings, cpu_temp=None)
        image = Image.open(BytesIO(jpeg))
        self.assertEqual(image.size, (LCD_CANVAS_SIZE, LCD_CANVAS_SIZE))


@unittest.skipUnless(FONT_PATH.exists(), "DejaVu Sans no está instalada en este entorno")
class LCDRendererFontFitTests(unittest.TestCase):
    """El extremo superior del rango de tamaño (text_scale=100) es deliberadamente
    el más grande que cabe sin recortarse contra el borde redondo real — ver el
    comentario junto a las constantes LCD_*_MAX en lcd_renderer.py. Estas pruebas
    evitan que alguien suba ese máximo sin darse cuenta de que empieza a recortar."""

    def setUp(self):
        self._probe = ImageDraw.Draw(Image.new('RGB', (1, 1)))

    def _width(self, text: str, size: int) -> float:
        font = ImageFont.truetype(str(FONT_PATH), size)
        bbox = self._probe.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    def test_dual_reading_worst_case_strings_fit_at_max_scale(self):
        # Fila inferior (y=295 título, y=342 valor) es la más ajustada: dy=55/102.
        for text in ('TEMPERATURA CPU', 'CARGA CPU'):
            self.assertLess(self._width(text, LCD_TITLE_FONT_SIZE_DUAL_MAX), max_safe_text_width(55))
        for text in ('105.0 °C', '-99.9 °C', '100 %'):
            self.assertLess(self._width(text, LCD_VALUE_FONT_SIZE_DUAL_MAX), max_safe_text_width(102))

    def test_single_reading_worst_case_strings_fit_at_max_scale(self):
        # título y=178 (dy=62), valor y=255 (dy=15).
        for text in ('TEMPERATURA CPU', 'CARGA CPU'):
            self.assertLess(self._width(text, LCD_TITLE_FONT_SIZE_SINGLE_MAX), max_safe_text_width(62))
        for text in ('105.0 °C', '-99.9 °C', '100 %'):
            self.assertLess(self._width(text, LCD_VALUE_FONT_SIZE_SINGLE_MAX), max_safe_text_width(15))

    def test_minimum_is_not_larger_than_maximum(self):
        self.assertLessEqual(LCD_TITLE_FONT_SIZE_DUAL_MIN, LCD_TITLE_FONT_SIZE_DUAL_MAX)
        self.assertLessEqual(LCD_VALUE_FONT_SIZE_DUAL_MIN, LCD_VALUE_FONT_SIZE_DUAL_MAX)
        self.assertLessEqual(LCD_TITLE_FONT_SIZE_SINGLE_MIN, LCD_TITLE_FONT_SIZE_SINGLE_MAX)
        self.assertLessEqual(LCD_VALUE_FONT_SIZE_SINGLE_MIN, LCD_VALUE_FONT_SIZE_SINGLE_MAX)


if __name__ == '__main__':
    unittest.main()
