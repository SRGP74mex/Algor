import unittest
from PyQt6.QtWidgets import QApplication
from algor.core.hardware import TelemetryData
from algor.ui.components.circular_gauge import CircularGauge
from algor.ui.views.fan_quick_control_dialog import FanQuickControlDialog

app = QApplication.instance() or QApplication([])


class FakeWorker:
    def __init__(self):
        self.manual_calls = []
        self.auto_calls = []
        self.restore_all_calls = 0
        self.sampler = None
        self.corsair_reader = None

    def request_channel_manual_pwm(self, identity, percent, enforce_floor=True):
        self.manual_calls.append((identity, percent, enforce_floor))
        return True

    def request_channel_auto(self, identity):
        self.auto_calls.append(identity)
        return True

    def request_restore_all_auto(self):
        self.restore_all_calls += 1
        return ['it8792@/x/pwm2']


class FanQuickControlDialogTests(unittest.TestCase):
    def setUp(self):
        self.worker = FakeWorker()
        self.data = TelemetryData()
        self.data.pwm_channels = {
            'it8792@/devices/pci0000:00/pwm2': {'pwm_path': '/fake/pwm2', 'enable_path': '/fake/pwm2_enable', 'chip': 'it8792'}
        }

    def test_pump_dialog_protects_pump(self):
        dialog = FanQuickControlDialog("pump_rpm", self.data, worker=self.worker)
        self.assertTrue(dialog.is_pump)
        # Verify that manual slider or preset buttons were not created for pump
        self.assertFalse(hasattr(dialog, 'slider'))

    def test_fan_dialog_manual_preset_and_restore(self):
        dialog = FanQuickControlDialog("fan_channel::it8792@/devices/pci0000:00/fan2", self.data, worker=self.worker)
        self.assertFalse(dialog.is_pump)
        self.assertEqual(dialog.pwm_identity, 'it8792@/devices/pci0000:00/pwm2')

        # Test applying 100%
        dialog._apply_percentage(100)
        self.assertEqual(len(self.worker.manual_calls), 1)
        self.assertEqual(self.worker.manual_calls[0], ('it8792@/devices/pci0000:00/pwm2', 100, False))

        # Test applying 27%
        dialog._apply_percentage(27)
        self.assertEqual(self.worker.manual_calls[1], ('it8792@/devices/pci0000:00/pwm2', 27, False))

        # Test restoring to auto
        dialog._restore_auto()
        self.assertEqual(len(self.worker.auto_calls), 1)
        self.assertEqual(self.worker.auto_calls[0], 'it8792@/devices/pci0000:00/pwm2')

    def test_circular_gauge_double_click_signal(self):
        gauge = CircularGauge(title="FAN", sensor_id="fan_channel::test", unit="RPM")
        emitted = []
        gauge.double_clicked.connect(lambda sid: emitted.append(sid))

        # Trigger double clicked
        gauge.double_clicked.emit(gauge.sensor_id)
        self.assertEqual(emitted, ["fan_channel::test"])


if __name__ == '__main__':
    unittest.main()

