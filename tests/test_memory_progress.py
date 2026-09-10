import struct
import unittest
from unittest.mock import Mock, patch
from algor.core.lcd_memory import save_captured_image


class MemoryProgressTests(unittest.TestCase):
    def run_progress(self, pages, progress):
        # Transporte simulado para aislar el contador de bloques de la codificación JPEG.
        image = Mock()
        report = bytearray(1024)
        struct.pack_into('<H', report, 6, pages)
        crc = b'abcd'
        image.prepare.return_value = ([bytes(report)], crc)
        device = Mock()
        responses = [b'\x0f'+bytes(31), b'\x0b'+bytes(31)]
        responses += [b'\x0a'+struct.pack('<I', n)+bytes(27) for n in progress]
        responses += [b'\x0f'+crc+bytes(27)]
        device.read_feature.side_effect = responses
        diagnostics = {}
        with patch('algor.core.lcd_memory.time.sleep'):
            result = save_captured_image(device, image, diagnostics=diagnostics)
        return device, diagnostics, result

    def test_41_of_42_is_pending_not_error(self):
        device, diagnostics, result = self.run_progress(42, [41,41,42])
        self.assertEqual(result['outcome'], 'crc_verified')
        self.assertEqual(diagnostics['completed_pages'],42)
        self.assertEqual(len(diagnostics['status_reports']),3)
        device.write_memory_report.assert_called_once()
        self.assertEqual(device.write_feature_report.call_count,2)

    def test_counter_above_255_uses_all_bytes(self):
        # No finalizar prematuramente con 257, cuyo primer byte es 1.
        _, diagnostics, _ = self.run_progress(278,[257,276,277,278])
        self.assertEqual(diagnostics['completed_pages'],278)
        self.assertEqual(len(diagnostics['status_reports']),4)

    def test_capture_53_page_sequence(self):
        _, diagnostics, _ = self.run_progress(53,[51,51,51,51,52,52,53])
        self.assertEqual(diagnostics['completed_pages'],53)
