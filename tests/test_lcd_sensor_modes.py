import unittest
from types import SimpleNamespace
from unittest.mock import patch
from algor.core.lcd_renderer import LCDRenderer, normalize_settings, cpu_usage_reading


class SensorModeTests(unittest.TestCase):
    def test_modes_both_and_none(self):
        renderer=LCDRenderer()
        with patch('algor.core.lcd_renderer.ImageDraw.ImageDraw.text') as text:
            renderer.render({'show_temperature':True,'show_usage':True},42,cpu_usage=73)
            written=[call.args[1] for call in text.call_args_list]
            self.assertIn('42.0 °C',written);self.assertIn('73 %',written)
        with patch('algor.core.lcd_renderer.ImageDraw.ImageDraw.text') as text:
            renderer.render({'show_temperature':False,'show_usage':True},42,cpu_usage=73)
            written=[call.args[1] for call in text.call_args_list]
            self.assertNotIn('42.0 °C',written);self.assertIn('73 %',written)
        with patch('algor.core.lcd_renderer.ImageDraw.ImageDraw.text') as text:
            renderer.render({'show_temperature':False,'show_usage':False},42,cpu_usage=73)
            self.assertIn('Sensores ocultos',[call.args[1] for call in text.call_args_list])

    def test_missing_load_is_not_zero(self):
        renderer=LCDRenderer()
        with patch('algor.core.lcd_renderer.ImageDraw.ImageDraw.text') as text:
            renderer.render({'show_temperature':False,'show_usage':True},None,cpu_usage=None)
            self.assertIn('N/D',[call.args[1] for call in text.call_args_list])
        reading=SimpleNamespace(cpu_usage_total=0,cpu_usage_available=True)
        self.assertEqual(cpu_usage_reading(reading,10,11),0)
        self.assertIsNone(cpu_usage_reading(reading,10,16))
        reading.cpu_usage_available=False
        self.assertIsNone(cpu_usage_reading(reading,10,11))

    def test_migration_and_color_change(self):
        defaults=normalize_settings({'mode':'cpu_temp'})
        self.assertTrue(defaults['show_temperature']);self.assertFalse(defaults['show_usage'])
        renderer=LCDRenderer()
        self.assertNotEqual(renderer.render({'accent_color':'#ff0000'},42),renderer.render({'accent_color':'#0000ff'},42))
