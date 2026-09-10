import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from algor.core.lcd_worker import LCDWorker, LCDSession
from algor.core.lcd_memory import load_captured_image


class MemoryWorkerTests(unittest.TestCase):
    def test_optional_assets_missing_fails_cleanly(self):
        with patch.object(Path, 'read_bytes', side_effect=FileNotFoundError('optional sample')):
            with self.assertRaises(FileNotFoundError):
                load_captured_image('A')
        with self.assertRaises(ValueError):
            load_captured_image('../A')

    def test_single_request_and_no_session_during_save(self):
        worker = LCDWorker()
        self.assertTrue(worker.request_memory_save('A'))
        self.assertFalse(worker.request_memory_save('B'))
        worker.set_active(True)
        self.assertFalse(worker._active)
        self.assertEqual(worker._memory_pending, 'A')

    def test_active_session_rejects_memory(self):
        worker = LCDWorker()
        worker.set_active(True)
        self.assertFalse(worker.request_memory_save('A'))
        self.assertIsNone(worker._memory_pending)

    def test_failure_is_recorded_and_not_retried(self):
        worker = LCDWorker()
        device = Mock()
        session = LCDSession(device)
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)), patch('algor.core.lcd_worker.load_captured_image', return_value=Mock()), patch('algor.core.lcd_worker.save_captured_image', side_effect=OSError('unplugged')) as save:
            worker._save_memory(session, 'A')
            save.assert_called_once()
            files = list(Path(directory).rglob('*.json'))
            self.assertEqual(len(files), 1)
            record = json.loads(files[0].read_text())
            self.assertEqual(record['outcome'], 'unconfirmed')
            self.assertEqual(record['error'], 'unplugged')
        self.assertFalse(worker._memory_busy)
        self.assertFalse(session.connected)
        device.disconnect.assert_called()

    def test_shutdown_waits_for_in_progress_transaction(self):
        worker = LCDWorker(device_factory=Mock)
        entered, release = threading.Event(), threading.Event()
        def save(*args):
            entered.set()
            self.assertTrue(release.wait(3))
            return dict(outcome='crc_verified')
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)), patch('algor.core.lcd_worker.load_captured_image', return_value=Mock()), patch('algor.core.lcd_worker.save_captured_image', side_effect=save) as writer:
            worker.request_memory_save('A')
            worker.start()
            try:
                self.assertTrue(entered.wait(3))
                stopped = threading.Event()
                closer = threading.Thread(target=lambda: (worker.stop(), stopped.set()))
                closer.start()
                self.assertFalse(stopped.wait(.05))
                release.set()
                closer.join(3)
                self.assertTrue(stopped.is_set())
                self.assertFalse(worker.isRunning())
                writer.assert_called_once()
            finally:
                release.set()
                worker.stop()

    def test_query_does_not_write_or_load_image(self):
        worker = LCDWorker()
        device = Mock()
        device.read_feature.return_value = bytes.fromhex('0f3ee0fd35') + bytes(27)
        session = LCDSession(device)
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, 'home', return_value=Path(directory)), patch('algor.core.lcd_worker.save_captured_image') as save, patch('algor.core.lcd_worker.load_captured_image') as load:
            worker._save_memory(session, 'check')
            save.assert_not_called()
            load.assert_not_called()
            device.read_feature.assert_called_once_with(0x0f)
            device.write_memory_report.assert_not_called()
            device.write_feature_report.assert_not_called()
            record = json.loads(next(Path(directory).rglob('*.json')).read_text())
            self.assertEqual(record['identified_image'], 'A')
            self.assertEqual(record['operation'], 'query')

    def test_query_unknown_crc_does_not_invent_image(self):
        from algor.core.lcd_memory import inspect_stored_image
        device = Mock()
        device.read_feature.return_value = b'\x0f' + bytes(31)
        self.assertIsNone(inspect_stored_image(device)['identified_image'])
        device.read_feature.return_value = b'\x0f'
        with self.assertRaises(ValueError):
            inspect_stored_image(device)
