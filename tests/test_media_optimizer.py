import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from algor.core.lcd_memory import prepare_custom_media
from algor.core.media_library import import_media


class OptimizerTests(unittest.TestCase):
    def make_gif(self, folder):
        path = Path(folder)/'original.gif'
        frames = [Image.new('RGB',(16,16),(i % 256, i//256*120, 255-i%256)) for i in range(300)]
        frames[0].save(path,save_all=True,append_images=frames[1:],duration=[30,30,40]*100,loop=0)
        return path

    def test_300_frames_reduced_without_changing_original_or_duration(self):
        with tempfile.TemporaryDirectory() as d:
            path = self.make_gif(d);original = path.read_bytes()
            asset = prepare_custom_media(path)
            self.assertEqual(len(asset.frames),150)
            self.assertEqual(sum(asset.source_durations),10000)
            self.assertEqual(asset.interval_field,67)
            self.assertIn('300 → 150',asset.optimization_summary)
            self.assertEqual(path.read_bytes(),original)
            asset.prepare()

    def test_import_oversized_gif_keeps_ten_second_duration(self):
        with tempfile.TemporaryDirectory() as d,patch.object(Path,'home',return_value=Path(d)):
            path=self.make_gif(d);original=path.read_bytes()
            target=import_media(path)
            self.assertNotEqual(target,path)
            self.assertEqual(path.read_bytes(),original)
            with Image.open(target) as image:
                self.assertLessEqual(image.n_frames,150)
                total=0
                for index in range(image.n_frames):
                    image.seek(index);total+=image.info.get('duration',0)
                self.assertEqual(total,10000)

    def test_sampling_respects_time_not_only_frame_index(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'timing.gif'
            frames=[Image.new('RGB',(16,16),color) for color in ('red','blue','green','yellow')]
            frames[0].save(path,save_all=True,append_images=frames[1:],duration=[700,100,100,100],loop=0)
            with patch('algor.core.lcd_memory.MAX_FRAMES',2):
                asset=prepare_custom_media(path)
            self.assertEqual(asset.frames[0],asset.frames[1])
            self.assertEqual(sum(asset.source_durations),1000)

    def test_compression_still_refuses_impossible_budget(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'one.png';Image.new('RGB',(16,16),'red').save(path)
            with patch('algor.core.lcd_memory.MAX_MEMORY_BYTES',32),self.assertRaises(ValueError):
                prepare_custom_media(path)
