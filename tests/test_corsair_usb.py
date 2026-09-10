"""Cobertura directa de CorsairNautilusDevice (sin sustituir la clase por un Mock),
ejerciendo la validación de longitud/prefijo y las rutas de error físicas que
antes solo se probaban vía Mock() genérico en otros módulos."""
import unittest
from io import BytesIO
from unittest.mock import Mock, patch

from PIL import Image

from algor.core.corsair_usb import CorsairNautilusDevice
from algor.core.lcd_protocol import jpeg_reports


def jpeg(size=(480, 480), color='cyan'):
    buffer = BytesIO()
    Image.new('RGB', size, color).save(buffer, format='JPEG')
    return buffer.getvalue()


def make_device():
    device = CorsairNautilusDevice()
    device.dev = Mock()
    device._claimed = True
    return device


class WriteMemoryReportTests(unittest.TestCase):
    def test_valid_report_is_written_once(self):
        device = make_device()
        device.dev.write.return_value = 1024
        report = b'\x02\x06' + bytes(1022)
        device.write_memory_report(report)
        device.dev.write.assert_called_once_with(0x09, report, timeout=500)

    def test_short_write_raises_without_leaving_ambiguous_state(self):
        device = make_device()
        device.dev.write.return_value = 500
        with self.assertRaisesRegex(RuntimeError, 'incierto'):
            device.write_memory_report(b'\x02\x06' + bytes(1022))

    def test_wrong_length_or_prefix_never_reaches_usb(self):
        device = make_device()
        with self.assertRaises(ValueError):
            device.write_memory_report(b'\x02\x06' + bytes(10))
        with self.assertRaises(ValueError):
            device.write_memory_report(b'\x99\x99' + bytes(1022))
        device.dev.write.assert_not_called()

    def test_requires_claimed_interface(self):
        device = make_device()
        device._claimed = False
        with self.assertRaises(ValueError):
            device.write_memory_report(b'\x02\x06' + bytes(1022))
        device.dev.write.assert_not_called()


class WriteFeatureReportTests(unittest.TestCase):
    def test_valid_completion_reports_are_written(self):
        device = make_device()
        device.dev.ctrl_transfer.return_value = 32
        for prefix in (b'\x03\x1c', b'\x03\x1b'):
            report = prefix + bytes(30)
            device.write_feature_report(report)
            device.dev.ctrl_transfer.assert_called_with(0x21, 9, 0x0303, 0, report, timeout=500)

    def test_short_write_raises(self):
        device = make_device()
        device.dev.ctrl_transfer.return_value = 12
        with self.assertRaisesRegex(RuntimeError, 'incierto'):
            device.write_feature_report(b'\x03\x1c' + bytes(30))

    def test_unrecognized_prefix_never_reaches_usb(self):
        device = make_device()
        with self.assertRaises(ValueError):
            device.write_feature_report(b'\x00\x00' + bytes(30))
        device.dev.ctrl_transfer.assert_not_called()


class SendJpegTests(unittest.TestCase):
    def test_full_transfer_updates_tail_from_last_report(self):
        device = make_device()
        data = jpeg()
        reports = jpeg_reports(data)
        device.dev.write.side_effect = [len(r) for r in reports]
        device.send_jpeg(data)
        self.assertEqual(device.dev.write.call_count, len(reports))
        self.assertEqual(device._tail, reports[-1][4:32])

    def test_cancellation_stops_before_any_write(self):
        device = make_device()
        with self.assertRaises(InterruptedError):
            device.send_jpeg(jpeg(), cancelled=lambda: True)
        device.dev.write.assert_not_called()

    def test_short_write_raises_incomplete_transfer(self):
        device = make_device()
        data = jpeg()
        device.dev.write.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'incompleta'):
            device.send_jpeg(data)

    def test_exceeded_deadline_raises_timeout(self):
        device = make_device()
        data = jpeg()
        reports = jpeg_reports(data)
        self.assertGreater(len(reports), 1, 'la muestra debe producir varios reportes para probar el timeout')
        device.dev.write.side_effect = [len(reports[0])]
        # deadline, primera comprobación (a tiempo), segunda comprobación (vencida)
        with patch('algor.core.corsair_usb.time.monotonic', side_effect=[0.0, 0.0, 10.0]):
            with self.assertRaises(TimeoutError):
                device.send_jpeg(data)
        self.assertEqual(device.dev.write.call_count, 1)

    def test_requires_claimed_interface(self):
        device = make_device()
        device._claimed = False
        with self.assertRaises(RuntimeError):
            device.send_jpeg(jpeg())
        device.dev.write.assert_not_called()


class DisconnectTests(unittest.TestCase):
    def test_no_device_is_a_silent_no_op(self):
        device = CorsairNautilusDevice()
        device.disconnect()  # no debe lanzar

    def test_releases_interface_reattaches_driver_and_resets_state(self):
        device = make_device()
        device._detached = True
        raw = device.dev
        with patch('usb.util.release_interface') as release, \
                patch('usb.util.dispose_resources') as dispose:
            device.disconnect()
        release.assert_called_once_with(raw, 0)
        raw.attach_kernel_driver.assert_called_once_with(0)
        dispose.assert_called_once_with(raw)
        self.assertIsNone(device.dev)
        self.assertFalse(device._claimed)
        self.assertFalse(device._detached)
        self.assertEqual(device._tail, bytes(28))

    def test_release_failure_still_attempts_reattach_and_dispose(self):
        device = make_device()
        device._detached = True
        raw = device.dev
        with patch('usb.util.release_interface', side_effect=OSError('desconectado')), \
                patch('usb.util.dispose_resources') as dispose, \
                patch('algor.core.logging_config.get_logger') as get_logger:
            device.disconnect()
        raw.attach_kernel_driver.assert_called_once_with(0)
        dispose.assert_called_once_with(raw)
        get_logger.return_value.warning.assert_called_once()
        self.assertIsNone(device.dev)

    def test_reattach_failure_does_not_prevent_dispose_or_raise(self):
        device = make_device()
        device._detached = True
        raw = device.dev
        raw.attach_kernel_driver.side_effect = OSError('desconectado')
        with patch('usb.util.release_interface') as release, \
                patch('usb.util.dispose_resources') as dispose:
            device.disconnect()  # no debe propagar la excepción
        release.assert_called_once_with(raw, 0)
        dispose.assert_called_once_with(raw)


if __name__ == '__main__':
    unittest.main()
