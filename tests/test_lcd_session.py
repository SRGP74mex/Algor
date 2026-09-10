import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
from algor.core.lcd_worker import LCDSession
from algor.core.lcd_renderer import LCDRenderer, cpu_reading
from algor.core.corsair_usb import CorsairNautilusDevice


class LCDSessionTests(unittest.TestCase):
    def test_idle_never_claims_usb(self):
        device = Mock()
        self.assertEqual(LCDSession(device).tick(b'image', 33, False, 0)[0], 'idle')
        device.connect.assert_not_called()
        device.send_jpeg.assert_not_called()

    def test_static_frame_heartbeat_brightness_and_stop(self):
        device = Mock()
        session = LCDSession(device)
        self.assertEqual(session.tick(b'image', 33, True, 0)[0], 'active')
        session.tick(b'image', 33, True, 3)
        device.send_jpeg.assert_called_once()
        device.keep_alive.assert_called_once()
        session.tick(b'image', 66, True, 4)
        self.assertEqual(device.keep_alive.call_count, 2)
        device.set_brightness.assert_called_with(66)
        session.tick(b'image', 66, False, 5)
        device.disconnect.assert_called_once()
        session.tick(b'image', 66, True, 6)
        self.assertEqual(device.send_jpeg.call_count, 2)

    def test_failure_releases_and_retries_with_backoff(self):
        device = Mock()
        device.send_jpeg.side_effect = OSError(19, 'desconectado')
        session = LCDSession(device)
        self.assertEqual(session.tick(b'image', 33, True, 0)[0], 'error')
        device.disconnect.assert_called_once()
        session.tick(b'image', 33, True, 0.5)
        device.connect.assert_called_once()
        device.send_jpeg.side_effect = None
        self.assertEqual(session.tick(b'image', 33, True, 1)[0], 'active')
        self.assertEqual(device.connect.call_count, 2)

    def test_cancel_prevents_frame(self):
        device = Mock()
        self.assertEqual(LCDSession(device).tick(b'image', 33, True, 0, lambda: True)[0], 'idle')
        device.send_jpeg.assert_not_called()
        device.disconnect.assert_called_once()

    def test_stale_and_absent_cpu_are_unavailable(self):
        sample = SimpleNamespace(cpu_temp_package=42, cpu_temp_available=True)
        self.assertEqual(cpu_reading(sample, 0, 1), 42)
        self.assertIsNone(cpu_reading(sample, 0, 6))
        sample.cpu_temp_available = False
        self.assertIsNone(cpu_reading(sample, 0, 1))
        renderer = LCDRenderer()
        missing = renderer.render({}, None)
        self.assertNotEqual(missing, renderer.render({}, 42))
        self.assertEqual(Image.open(BytesIO(missing)).size, (480, 480))

    def test_usb_discovery_is_limited_to_verified_device(self):
        with patch('usb.core.find', return_value=[]) as find:
            with self.assertRaises(RuntimeError):
                CorsairNautilusDevice().connect()
            find.assert_called_once_with(find_all=True, idVendor=0x1b1c, idProduct=0x0c57)

    def test_brightness_report_and_short_write(self):
        device = CorsairNautilusDevice()
        device.dev = Mock()
        device._claimed = True
        device.dev.ctrl_transfer.return_value = 32
        device.set_brightness(33)
        device.dev.ctrl_transfer.assert_called_once_with(0x21, 9, 0x0303, 0, bytes([3, 11, 33, 1]) + bytes(28), timeout=500)
        device.dev.ctrl_transfer.return_value = 12
        with self.assertRaises(RuntimeError):
            device.keep_alive()
        with self.assertRaises(ValueError):
            device.set_brightness(-1)

    def test_resume_resends_same_frame_and_brightness_without_memory(self):
        device = Mock()
        events = []
        session = LCDSession(device, events.append)
        session.tick(b'image', 33, True, 0, lifecycle_now=0)
        # monotonic scarcely advances during suspend; boottime does.
        session.tick(b'image', 33, True, 1, lifecycle_now=120)
        self.assertEqual(device.connect.call_count, 2)
        self.assertEqual(device.send_jpeg.call_count, 2)
        self.assertEqual(device.set_brightness.call_count, 2)
        device.write_memory_report.assert_not_called()
        self.assertTrue(any('pausa' in event for event in events))

    def test_resume_while_idle_does_not_activate(self):
        device = Mock()
        session = LCDSession(device)
        session.tick(b'image', 33, False, 0, lifecycle_now=0)
        session.tick(b'image', 33, False, 1, lifecycle_now=120)
        device.connect.assert_not_called()

    def test_start_missing_device_then_arrives(self):
        device = Mock()
        device.connect.side_effect = [OSError(19, 'ausente'), None]
        session = LCDSession(device)
        self.assertEqual(session.tick(b'image', 44, True, 0)[0], 'error')
        self.assertEqual(session.tick(b'image', 44, True, 0.5)[0], 'error')
        device.send_jpeg.assert_not_called()
        self.assertEqual(session.tick(b'image', 44, True, 1)[0], 'active')
        device.set_brightness.assert_called_once_with(44)
