import re
import unittest
from PyQt6.QtWidgets import QApplication
from algor.ui.theme import Theme

app = QApplication.instance() or QApplication([])


class TestThemeFontScaling(unittest.TestCase):
    def tearDown(self):
        Theme.set_font_override(None)

    def test_default_is_automatic_and_uses_app_font(self):
        Theme.set_font_override(None)
        expected = app.font().pointSize()
        self.assertEqual(Theme.base_pt(), expected)

    def test_manual_override_takes_precedence(self):
        Theme.set_font_override(16)
        self.assertEqual(Theme.base_pt(), 16)

    def test_pt_is_relative_to_base_and_never_below_floor(self):
        Theme.set_font_override(10)
        self.assertEqual(Theme.pt(2), 12)
        self.assertEqual(Theme.pt(-1), 9)
        self.assertEqual(Theme.pt(-100), 7)  # nunca por debajo del piso legible

    def test_build_stylesheet_reflects_current_base(self):
        Theme.set_font_override(20)
        css = Theme.build_stylesheet()
        self.assertIn("font-size: 20pt", css)
        # Ningún font-size debe quedar en px: eso es lo que ignoraba QT_FONT_DPI
        # y el factor de escala de texto del sistema.
        self.assertIsNone(re.search(r"font-size:\s*\d+px", css))


if __name__ == "__main__":
    unittest.main()
