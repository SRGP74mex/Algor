import glob as glob_module
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from algor.core.hardware import HardwareSampler, HardwareWorker, TelemetryData


def run_one_iteration(worker):
    """Ejecuta run() exactamente una vez: el primer .wait() del hilo apaga
    _running, así el bucle termina solo sin necesitar un hilo real."""
    def wait_once(timeout):
        worker._running = False
        return True
    worker._stop_event.wait = wait_once
    worker.run()


class ScanPwmChannelsTests(unittest.TestCase):
    def test_only_write_capable_chips_are_discovered(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def make_chip(name, index, pwm_numbers):
                base = root / f'hwmon{index}'
                base.mkdir()
                (base / 'name').write_text(name)
                physical = root / f'devices/chip{index}'
                physical.mkdir(parents=True)
                (base / 'device').symlink_to(physical, target_is_directory=True)
                for n in pwm_numbers:
                    (base / f'pwm{n}').write_text('70')
                    (base / f'pwm{n}_enable').write_text('2')

            make_chip('it8792', 4, [1, 2, 3])
            make_chip('it8620', 3, [1, 2, 3, 4, 5])
            make_chip('coretemp', 2, [1])  # sin capacidad de escritura: nunca debe aparecer

            original_glob = glob_module.glob

            def fake_glob(pattern):
                if pattern == '/sys/class/hwmon/hwmon*':
                    return sorted(str(p) for p in root.glob('hwmon*'))
                return original_glob(pattern)

            sampler = HardwareSampler.__new__(HardwareSampler)  # evita __init__ (no toca hardware real)
            with patch('algor.core.hardware.glob.glob', side_effect=fake_glob):
                channels = sampler.scan_pwm_channels()

            chips_found = {ch['chip'] for ch in channels.values()}
            self.assertEqual(chips_found, {'it8792', 'it8620'})
            self.assertEqual(sum(1 for ch in channels.values() if ch['chip'] == 'it8792'), 3)
            self.assertEqual(sum(1 for ch in channels.values() if ch['chip'] == 'it8620'), 5)
            for identity, ch in channels.items():
                self.assertTrue(identity.startswith(ch['chip'] + '@'))
                self.assertTrue(ch['enable_path'].endswith('_enable'))


class ScanTempChannelsTests(unittest.TestCase):
    def test_discovers_any_chip_not_only_pwm_capable_ones(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)

            def make_chip(name, index, temps):
                base = root / f'hwmon{index}'
                base.mkdir()
                (base / 'name').write_text(name)
                physical = root / f'devices/chip{index}'
                physical.mkdir(parents=True)
                (base / 'device').symlink_to(physical, target_is_directory=True)
                for n, millideg, label in temps:
                    (base / f'temp{n}_input').write_text(str(millideg))
                    if label is not None:
                        (base / f'temp{n}_label').write_text(label)

            make_chip('it8620', 3, [(1, 31000, None), (3, -55000, None)])
            make_chip('coretemp', 2, [(1, 40000, 'Package id 0')])  # sin capacidad PWM, igual debe aparecer

            original_glob = glob_module.glob

            def fake_glob(pattern):
                if pattern == '/sys/class/hwmon/hwmon*':
                    return sorted(str(p) for p in root.glob('hwmon*'))
                return original_glob(pattern)

            sampler = HardwareSampler.__new__(HardwareSampler)
            with patch('algor.core.hardware.glob.glob', side_effect=fake_glob):
                channels = sampler.scan_temp_channels()

            temps = {round(ch['temp'], 1) for ch in channels.values() if ch['temp'] is not None}
            self.assertIn(31.0, temps)
            self.assertIn(-55.0, temps)  # descubrimiento no filtra; el filtro vive en la UI/valid_temp
            self.assertIn(40.0, temps)
            labels = {ch['label'] for ch in channels.values()}
            self.assertIn('Package id 0', labels)  # usa el label del chip cuando existe


class HardwareWorkerPwmTests(unittest.TestCase):
    def setUp(self):
        self.data = TelemetryData(
            cpu_temp_available=True, cpu_temp_package=40.0,
            pwm_channels={'it8792@/x/pwm2': {'pwm_path': '/x/pwm2', 'enable_path': '/x/pwm2_enable', 'chip': 'it8792'}},
        )
        self.fan_engine = MagicMock()
        self.fan_engine.calculate_pwm.return_value = 55
        self.pwm_writer = MagicMock()
        self.pwm_writer.restore_stale_manual_channels.return_value = []
        self.worker = HardwareWorker(fan_engine=self.fan_engine, pwm_writer=self.pwm_writer)
        self.worker.sampler = MagicMock(sample=MagicMock(return_value=self.data))
        self.worker.telemetry_updated = MagicMock()  # nunca depender del bucle de eventos de Qt aquí

    def test_apply_not_called_when_real_control_disabled(self):
        self.fan_engine.real_control_enabled = False
        run_one_iteration(self.worker)
        self.pwm_writer.apply.assert_not_called()

    def test_apply_called_once_per_cycle_when_real_control_enabled(self):
        self.fan_engine.real_control_enabled = True
        run_one_iteration(self.worker)
        self.pwm_writer.apply.assert_called_once()
        self.assertEqual(self.pwm_writer.apply.call_args[0][0], 55)

    def test_startup_stale_check_runs_exactly_once(self):
        self.fan_engine.real_control_enabled = False
        run_one_iteration(self.worker)
        self.assertTrue(self.worker._startup_pwm_checked)
        self.pwm_writer.restore_stale_manual_channels.assert_called_once()
        # Un segundo ciclo no debe repetir el chequeo de arranque.
        run_one_iteration(self.worker)
        self.pwm_writer.restore_stale_manual_channels.assert_called_once()

    def test_stale_channel_restored_signal_emits_when_something_was_fixed(self):
        self.pwm_writer.restore_stale_manual_channels.return_value = ['it8792@/x/pwm2']
        self.fan_engine.real_control_enabled = False
        self.worker.stale_channel_restored = MagicMock()
        run_one_iteration(self.worker)
        self.worker.stale_channel_restored.emit.assert_called_once_with('it8792@/x/pwm2')

    def test_manual_override_applied_once_and_cleared(self):
        self.fan_engine.real_control_enabled = False
        self.worker.request_manual_pwm(42)
        run_one_iteration(self.worker)
        self.pwm_writer.apply_manual_override.assert_called_once()
        self.assertEqual(self.pwm_writer.apply_manual_override.call_args[0][0], 42)
        self.assertIsNone(self.worker._pending_manual_pwm)


if __name__ == '__main__':
    unittest.main()
