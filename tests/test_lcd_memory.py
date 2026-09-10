import importlib.util
import hashlib
from io import BytesIO
from PIL import Image
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock, patch
from algor.core.lcd_memory import CapturedMemoryImage, save_captured_image, CAPTURED_IMAGES

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / 'captures/20260908T225405_780878Z_memory'


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.original_captured = dict(CAPTURED_IMAGES)
        buffer = BytesIO()
        Image.new('RGB', (480, 480), (20, 80, 140)).save(buffer, 'JPEG')
        # Synthetic JPEG of the same byte length exercises the same packet boundaries.
        self.jpeg = buffer.getvalue().ljust(21007, b'\0')
        replacement = dict(CAPTURED_IMAGES)
        replacement['A'] = (hashlib.sha256(self.jpeg).hexdigest(), replacement['A'][1])
        patcher = patch.dict(CAPTURED_IMAGES, replacement, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def asset(self, letter='A'):
        return CapturedMemoryImage(letter, self.jpeg)

    def test_reject_changed_image_before_usb(self):
        device = Mock()
        with self.assertRaises(ValueError):
            save_captured_image(device, CapturedMemoryImage('A', b'invalid'))
        self.assertEqual(device.mock_calls, [])

    @unittest.skipUnless((CAPTURE / "lcd.pcapng").exists(), "Optional local USB capture is not distributed")
    def test_reports_match_capture_meaningful_bytes(self):
        spec = importlib.util.spec_from_file_location('capture_parser', ROOT/'scripts/analyze_lcd_capture.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        observed = []
        stats = dict(packets=0, truncated_packets=0, short_payloads=0)
        for _, _, event, _, ep, _, _, _, _, data, _ in module.packets(CAPTURE/'lcd.pcapng', stats):
            if event == 'S' and ep == 9 and data[:2] == b'\x02\x06':
                observed.append(data)
        with patch.dict(CAPTURED_IMAGES, self.original_captured, clear=True):
            prepared = [r for letter in 'ABC' for r in CapturedMemoryImage(letter,
                (CAPTURE/'memory_analysis'/f'memory_{"ABC".index(letter):02d}.jpg').read_bytes()).prepare()[0]]
        self.assertEqual(len(prepared), len(observed))
        for generated, captured in zip(prepared, observed):
            useful = 32 if captured[6] == 0 else 16 + struct.unpack_from('<H', captured, 12)[0]
            self.assertEqual(generated[:useful], captured[:useful])
            self.assertEqual(generated[useful:], bytes(1024-useful))

    def device(self, state=1):
        device = Mock()
        crc = self.asset().prepare()[1]
        values = iter([b'\x0f'+bytes(31), b'\x0b'+bytes(31), bytes([0x0a, state])+bytes(30), b'\x0f'+crc+bytes(27)])
        device.read_feature.side_effect = lambda _: next(values)
        return device

    def test_success_accepts_immediately_ready_and_verifies_crc(self):
        device = self.device()
        with patch('algor.core.lcd_memory.time.sleep'):
            result = save_captured_image(device, self.asset())
        self.assertEqual(result['outcome'], 'crc_verified')
        self.assertEqual(device.write_memory_report.call_count, 22)
        self.assertEqual(device.write_feature_report.call_count, 2)
        self.assertEqual(device.write_feature_report.call_args_list[0].args[0][2:6], self.asset().prepare()[1])

    def test_already_stored_never_writes(self):
        device = Mock()
        device.read_feature.return_value = b'\x0f'+self.asset().prepare()[1]+bytes(27)
        self.assertEqual(save_captured_image(device, self.asset())['outcome'], 'already_stored')
        device.write_memory_report.assert_not_called()

    def test_transfer_failure_never_finalizes_or_retries(self):
        device = self.device()
        device.write_memory_report.side_effect = OSError('disconnected')
        with self.assertRaises(OSError):
            save_captured_image(device, self.asset())
        device.write_memory_report.assert_called_once()
        device.write_feature_report.assert_not_called()

    def test_unknown_status_does_not_finalize(self):
        device = self.device(state=2)
        with patch('algor.core.lcd_memory.time.sleep'), self.assertRaises(RuntimeError):
            save_captured_image(device, self.asset())
        device.write_feature_report.assert_not_called()

    def test_crc_mismatch_is_not_reported_as_success(self):
        device = self.device()
        values = iter([b'\x0f'+bytes(31), b'\x0b'+bytes(31), b'\x0a\x01'+bytes(30), b'\x0f'+bytes(31)])
        device.read_feature.side_effect = lambda _: next(values, b'\x0f'+bytes(31))
        with patch('algor.core.lcd_memory.time.sleep'), self.assertRaises(RuntimeError):
            save_captured_image(device, self.asset())
        self.assertEqual(device.write_memory_report.call_count, 22)

    def test_pending_timeout_does_not_finalize(self):
        device = Mock()
        device.read_feature.side_effect = lambda report: bytes([report])+bytes(31)
        times = iter([0]*24 + [6, 7, 13])
        with patch('algor.core.lcd_memory.time.sleep'), patch('algor.core.lcd_memory.time.monotonic', side_effect=lambda: next(times)), self.assertRaises(TimeoutError):
            save_captured_image(device, self.asset())
        device.write_feature_report.assert_not_called()


    def test_delayed_crc_reads_again_without_rewriting(self):
        device = self.device()
        crc = self.asset().prepare()[1]
        values = iter([b'\x0f'+bytes(31), b'\x0b'+bytes(31), b'\x0a\x01'+bytes(30),
                       b'\x0f'+bytes(31), b'\x0f'+crc+bytes(27)])
        device.read_feature.side_effect = lambda _: next(values)
        diagnostics = {}
        with patch('algor.core.lcd_memory.time.sleep'):
            result = save_captured_image(device, self.asset(), diagnostics=diagnostics)
        self.assertEqual(result['outcome'], 'crc_verified')
        self.assertEqual(len(diagnostics['verification_reports']), 2)
        self.assertEqual(device.write_memory_report.call_count, 22)
        self.assertEqual(device.write_feature_report.call_count, 2)
