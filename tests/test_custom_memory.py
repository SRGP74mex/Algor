import tempfile
import unittest
import struct
import zlib
from pathlib import Path
from PIL import Image
from algor.core.lcd_memory import prepare_custom_media, memory_reports, PreparedMemoryMedia


class CustomMemoryTests(unittest.TestCase):
    def test_file_snapshot_crc_and_length_table(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'own.gif'
            Image.new('RGB',(32,32),'red').save(path,save_all=True,append_images=[Image.new('RGB',(32,32),'blue')],duration=[200,800],loop=0)
            asset=prepare_custom_media(path,90)
            path.unlink()
            self.assertEqual(asset.source_durations,(200,800))
            reports,crc=asset.prepare()
            content=b''.join(r[16:16+int.from_bytes(r[12:14],'little')] for r in reports[1:])
            self.assertEqual(struct.unpack_from('<HHHH',content,1),(480,480,2,500))
            self.assertEqual(struct.unpack_from('<II',content,9),tuple(map(len,asset.frames)))
            self.assertEqual(content[17:],b''.join(asset.frames))
            self.assertEqual(crc,struct.pack('<I',zlib.crc32(content[17:])))

    def test_page_boundary_no_lost_bytes(self):
        content=b'x'*(131072+2500)
        reports=memory_reports(content)
        self.assertEqual(reports[131][10:12],b'\x01\x00')
        self.assertEqual(reports[131][12:16],struct.pack('<HH',32,130))
        self.assertEqual(reports[132][6:8],b'\x02\x00')
        self.assertEqual(reports[132][14:16],b'\x00\x00')
        self.assertEqual(reports[-1][10:12],b'\x01\x01')
        rebuilt=b''.join(r[16:16+int.from_bytes(r[12:14],'little')] for r in reports[1:])
        self.assertEqual(rebuilt,content)
        with self.assertRaises(ValueError):memory_reports(b'x'*(12*1024*1024+1))

    def test_static_and_invalid_rotation(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'own.png';Image.new('RGB',(50,70),'green').save(path)
            asset=prepare_custom_media(path)
            self.assertEqual(len(asset.frames),1)
            with self.assertRaises(ValueError):prepare_custom_media(path,45)


    def test_ten_second_gif_uses_167_ms_not_fixed_37(self):
        asset = PreparedMemoryMedia('own', (b'jpeg',) * 60, (170, 160, 170) * 20, 0)
        self.assertEqual(asset.interval_field, 167)
        self.assertEqual(asset.interval_field * len(asset.frames), 10020)

    def test_invalid_durations_are_rejected(self):
        for durations in [(0, 100), (100,), (100, 70000)]:
            asset = PreparedMemoryMedia('own', (b'jpeg',) * 2, durations, 0)
            with self.assertRaises(ValueError):
                asset.prepare()

    def test_same_jpeg_crc_still_updates_gif_timing_once(self):
        from unittest.mock import Mock, patch
        from algor.core.lcd_memory import save_captured_image
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'own.gif'
            Image.new('RGB',(32,32),'red').save(path,save_all=True,append_images=[Image.new('RGB',(32,32),'blue')],duration=[200,800],loop=0)
            asset = prepare_custom_media(path)
            reports, crc = asset.prepare()
            device = Mock()
            device.read_feature.side_effect = [b'\x0f'+crc+bytes(27), b'\x0b'+bytes(31), b'\x0a\x01'+bytes(30), b'\x0f'+crc+bytes(27)]
            diagnostics = {}
            with patch('algor.core.lcd_memory.time.sleep'):
                result = save_captured_image(device, asset, diagnostics=diagnostics)
            self.assertEqual(result['outcome'], 'crc_verified')
            self.assertTrue(diagnostics['timing_update_requested'])
            self.assertEqual(device.write_memory_report.call_count, len(reports))
            self.assertEqual(device.write_feature_report.call_count, 2)

    def test_150_frames_accepted_and_151_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'one.png'
            Image.new('RGB',(16,16),'red').save(path)
            frame = prepare_custom_media(path).frames[0]
            asset = PreparedMemoryMedia('150', (frame,)*150, (70,60,70)*50, 0)
            reports, _ = asset.prepare()
            self.assertEqual(asset.interval_field,67)
            self.assertTrue(reports)
            with self.assertRaises(ValueError):
                PreparedMemoryMedia('151',(frame,)*151,(70,)*151,0).prepare()
