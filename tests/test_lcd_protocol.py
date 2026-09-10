import importlib.util
from io import BytesIO
from pathlib import Path
import struct
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from algor.core.lcd_protocol import jpeg_reports


class TestLcdProtocol(unittest.TestCase):
    def jpeg(self, size=(480, 480)):
        buffer = BytesIO()
        Image.new('RGB', size, 'cyan').save(buffer, format='JPEG')
        return buffer.getvalue()

    def test_reconstruction_preserves_exact_jpeg(self):
        jpeg = self.jpeg()
        reports = jpeg_reports(jpeg)
        restored = bytearray()
        for index, report in enumerate(reports):
            self.assertEqual(len(report), 1024)
            self.assertEqual(report[:3], b'\x02\x05\x03')
            final, sequence, length = struct.unpack_from('<BHH', report, 3)
            self.assertEqual(sequence, index)
            self.assertEqual(final, int(index == len(reports) - 1))
            self.assertLessEqual(length, 1016)
            restored.extend(report[8:8 + length])
            self.assertEqual(report[8 + length:], bytes(1016 - length))
        self.assertEqual(restored, jpeg)

    def test_rejects_wrong_dimensions_and_incomplete_jpeg(self):
        for invalid in (self.jpeg((32, 32)), self.jpeg()[:-2], b'\xff\xd8\xff\xd9'):
            with self.assertRaises((ValueError, OSError)):
                jpeg_reports(invalid)

    def test_transport_restores_kernel_driver_after_short_write(self):
        spec = importlib.util.spec_from_file_location(
            'lcd_probe', Path(__file__).resolve().parents[1] / 'scripts' / 'test_lcd_static.py')
        probe = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probe)
        endpoint = MagicMock(bEndpointAddress=9, bmAttributes=3)
        interface = MagicMock(bInterfaceClass=3)
        interface.__iter__.return_value = iter([endpoint])
        device = MagicMock()
        device.get_active_configuration.return_value.__getitem__.return_value = interface
        device.is_kernel_driver_active.return_value = True
        device.write.return_value = 12
        with patch('usb.core.find', return_value=[device]) as find, \
                patch('usb.util.claim_interface') as claim, \
                patch('usb.util.release_interface') as release, \
                patch('usb.util.dispose_resources') as dispose:
            with self.assertRaisesRegex(RuntimeError, 'parcial'):
                probe.transmit(jpeg_reports(self.jpeg()))
            find.assert_called_once_with(find_all=True, idVendor=0x1b1c, idProduct=0x0c57)
            claim.assert_called_once_with(device, 0)
            release.assert_called_once_with(device, 0)
            device.attach_kernel_driver.assert_called_once_with(0)
            dispose.assert_called_once_with(device)
            device.reset.assert_not_called()
            device.set_configuration.assert_not_called()
            device.ctrl_transfer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
