import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from PIL import Image
from algor.core.media_library import import_media
from algor.core.lcd_renderer import LCDRenderer


class MediaTests(unittest.TestCase):
    def gif(self, folder):
        path = Path(folder)/'source.gif'
        a, b = Image.new('RGB', (32, 32), 'red'), Image.new('RGB', (32, 32), 'blue')
        a.save(path, save_all=True, append_images=[b], duration=[200,800], loop=0, disposal=2)
        return path

    def test_import_survives_source_removal_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Path, 'home', return_value=Path(folder)):
            source = self.gif(folder)
            original = source.read_bytes()
            saved = import_media(source)
            self.assertEqual(saved, import_media(source))
            source.unlink()
            self.assertEqual(saved.read_bytes(), original)
            self.assertEqual(saved.parent.name, 'media')

    def test_timing_loop_and_shared_jpeg(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self.gif(folder)
            renderer = LCDRenderer()
            config = dict(mode='custom_image', custom_image_path=str(path))
            first = renderer.render(config, None, now=10)
            self.assertEqual(first, renderer.render(config, None, now=10.15))
            second = renderer.render(config, None, now=10.3)
            self.assertNotEqual(first, second)
            self.assertEqual(second, renderer.render(config, None, now=10.9))
            self.assertEqual(first, renderer.render(config, None, now=11.1))
            self.assertEqual(Image.open(BytesIO(second)).size, (480,480))

    def test_static_gif_accepted_and_oversized_animation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'static.gif'
            Image.new('RGB',(20,20),'red').save(path)
            renderer=LCDRenderer()
            self.assertTrue(renderer.render(dict(mode='custom_image',custom_image_path=str(path)),None))
            with patch('algor.core.media_library.MAX_FRAMES', 1), self.assertRaises(ValueError):
                renderer.render(dict(mode='custom_image',custom_image_path=str(self.gif(folder))),None)

    def test_invalid_import_does_not_create_library(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Path,'home',return_value=Path(folder)):
            source=Path(folder)/'bad.gif';source.write_bytes(b'bad')
            with self.assertRaises(Exception):
                import_media(source)
            self.assertFalse((Path(folder)/'.local/share/algor/media').exists())
