import json
import tempfile
import unittest
from pathlib import Path
from algor.core.pwm_writer import (PwmWriter, PROTECTION_FLOOR_PERCENT, AUTO_ENABLE_VALUE,
                                    MANUAL_ENABLE_VALUE, percent_to_raw, raw_to_percent)


class FakeSysfs:
    """Sustituto en memoria de sysfs: nunca toca archivos reales."""

    def __init__(self, initial=None):
        self.files = dict(initial or {})
        self.write_log = []

    def write(self, path, value):
        self.write_log.append((path, value))
        self.files[path] = str(value)

    def read(self, path):
        return self.files.get(path)


def make_channel(fs, pwm_path='pwm2', enable_path='pwm2_enable', chip='it8792', enable='2', pwm='70'):
    fs.files[pwm_path] = pwm
    fs.files[enable_path] = enable
    return {'pwm_path': pwm_path, 'enable_path': enable_path, 'chip': chip}


class PercentConversionTests(unittest.TestCase):
    def test_round_trip_bounds(self):
        self.assertEqual(percent_to_raw(0), 0)
        self.assertEqual(percent_to_raw(100), 255)
        self.assertEqual(percent_to_raw(150), 255)
        self.assertEqual(percent_to_raw(-10), 0)
        self.assertEqual(raw_to_percent(0), 0.0)
        self.assertEqual(raw_to_percent(255), 100.0)


class PwmWriterApplyTests(unittest.TestCase):
    def setUp(self):
        self.fs = FakeSysfs()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        state_path = Path(self._tmpdir.name) / "manual_pwm_state.json"
        self.writer = PwmWriter(write_file=self.fs.write, read_file=self.fs.read, state_path=state_path)
        self.channel = make_channel(self.fs)
        self.pwm_channels = {'it8792@/x/pwm2': self.channel}

    def eligible_mapping(self, **overrides):
        base = dict(role='radiator', confirmed=True, pwm_tested=True, pwm_channel='it8792@/x/pwm2')
        base.update(overrides)
        return base

    def test_apply_never_writes_below_protection_floor(self):
        self.writer.apply(5, {'fan2': self.eligible_mapping()}, self.pwm_channels)
        self.assertEqual(self.fs.read('pwm2'), str(percent_to_raw(PROTECTION_FLOOR_PERCENT)))

    def test_apply_writes_requested_value_above_floor(self):
        self.writer.apply(80, {'fan2': self.eligible_mapping()}, self.pwm_channels)
        self.assertEqual(self.fs.read('pwm2'), str(percent_to_raw(80)))

    def test_apply_clamps_above_100(self):
        self.writer.apply(500, {'fan2': self.eligible_mapping()}, self.pwm_channels)
        self.assertEqual(self.fs.read('pwm2'), str(percent_to_raw(100)))

    def test_apply_ignores_pump_even_if_forged_tested(self):
        pump = self.eligible_mapping(role='pump')
        self.writer.apply(80, {'fan1': pump}, self.pwm_channels)
        self.assertEqual(self.fs.read('pwm2'), '70')  # sin cambios
        self.assertEqual(self.fs.read('pwm2_enable'), '2')  # nunca tomó control

    def test_apply_ignores_untested_channel(self):
        untested = dict(role='radiator', confirmed=True)
        self.writer.apply(80, {'fan2': untested}, self.pwm_channels)
        self.assertEqual(self.fs.read('pwm2_enable'), '2')

    def test_apply_ignores_unknown_pwm_channel_identity(self):
        mapping = self.eligible_mapping(pwm_channel='it8792@/x/pwm9-no-existe')
        self.writer.apply(80, {'fan2': mapping}, self.pwm_channels)
        self.assertEqual(self.fs.read('pwm2_enable'), '2')

    def test_apply_takes_manual_control_once_then_reuses(self):
        self.writer.apply(80, {'fan2': self.eligible_mapping()}, self.pwm_channels)
        self.assertEqual(self.fs.read('pwm2_enable'), str(MANUAL_ENABLE_VALUE))
        enable_writes = [w for w in self.fs.write_log if w[0] == 'pwm2_enable']
        self.writer.apply(90, {'fan2': self.eligible_mapping()}, self.pwm_channels)
        self.assertEqual(len([w for w in self.fs.write_log if w[0] == 'pwm2_enable']), len(enable_writes))

    def test_apply_skips_rewrite_of_identical_value(self):
        self.writer.apply(80, {'fan2': self.eligible_mapping()}, self.pwm_channels)
        writes_before = len(self.fs.write_log)
        self.writer.apply(80, {'fan2': self.eligible_mapping()}, self.pwm_channels)
        self.assertEqual(len(self.fs.write_log), writes_before)


class PwmWriterRestoreTests(unittest.TestCase):
    def setUp(self):
        self.fs = FakeSysfs()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.state_path = Path(self._tmpdir.name) / "manual_pwm_state.json"
        self.writer = PwmWriter(write_file=self.fs.write, read_file=self.fs.read, state_path=self.state_path)
        self.channel = make_channel(self.fs)
        self.pwm_channels = {'it8792@/x/pwm2': self.channel}
        self.mapping = {'fan2': dict(role='radiator', confirmed=True, pwm_tested=True,
                                      pwm_channel='it8792@/x/pwm2')}

    def test_restore_all_returns_to_auto_and_is_idempotent(self):
        self.writer.apply(80, self.mapping, self.pwm_channels)
        self.writer.restore_all()
        self.assertEqual(self.fs.read('pwm2_enable'), str(AUTO_ENABLE_VALUE))
        # Segunda llamada no debe fallar ni volver a escribir nada.
        writes_before = len(self.fs.write_log)
        self.writer.restore_all()
        self.assertEqual(len(self.fs.write_log), writes_before)

    def test_restore_stale_manual_channels_fixes_orphan_from_prior_crash(self):
        # Simula una sesión anterior que murió a mitad de una escritura manual.
        self.fs.files['pwm2_enable'] = str(MANUAL_ENABLE_VALUE)
        restored = self.writer.restore_stale_manual_channels(self.mapping, self.pwm_channels)
        self.assertEqual(restored, ['it8792@/x/pwm2'])
        self.assertEqual(self.fs.read('pwm2_enable'), str(AUTO_ENABLE_VALUE))

    def test_restore_stale_manual_channels_ignores_already_automatic(self):
        restored = self.writer.restore_stale_manual_channels(self.mapping, self.pwm_channels)
        self.assertEqual(restored, [])

    def test_restore_stale_manual_channels_never_touches_pump(self):
        self.fs.files['pwm2_enable'] = str(MANUAL_ENABLE_VALUE)
        pump_mapping = {'fan1': dict(role='pump', confirmed=True, pwm_tested=True,
                                      pwm_channel='it8792@/x/pwm2')}
        restored = self.writer.restore_stale_manual_channels(pump_mapping, self.pwm_channels)
        self.assertEqual(restored, [])
        self.assertEqual(self.fs.read('pwm2_enable'), str(MANUAL_ENABLE_VALUE))

    def test_set_channel_manual_and_auto(self):
        ok = self.writer.set_channel_manual('it8792@/x/pwm2', self.channel, 100)
        self.assertTrue(ok)
        self.assertEqual(self.fs.read('pwm2_enable'), str(MANUAL_ENABLE_VALUE))
        self.assertEqual(self.fs.read('pwm2'), str(percent_to_raw(100)))

        # Manual with floor bypass (e.g. 27%)
        ok = self.writer.set_channel_manual('it8792@/x/pwm2', self.channel, 27, enforce_floor=False)
        self.assertTrue(ok)
        self.assertEqual(self.fs.read('pwm2'), str(percent_to_raw(27)))

        # Restore single channel to auto
        ok = self.writer.set_channel_auto('it8792@/x/pwm2', self.channel)
        self.assertTrue(ok)
        self.assertEqual(self.fs.read('pwm2_enable'), str(AUTO_ENABLE_VALUE))

    def test_restore_all_system_channels(self):
        channel2 = make_channel(self.fs, pwm_path='pwm3', enable_path='pwm3_enable', chip='it8620')
        all_channels = {
            'it8792@/x/pwm2': self.channel,
            'it8620@/y/pwm3': channel2,
        }
        # Set both to manual
        self.fs.files['pwm2_enable'] = str(MANUAL_ENABLE_VALUE)
        self.fs.files['pwm3_enable'] = str(MANUAL_ENABLE_VALUE)

        restored = self.writer.restore_all_system_channels(all_channels)
        self.assertEqual(len(restored), 2)
        self.assertEqual(self.fs.read('pwm2_enable'), str(AUTO_ENABLE_VALUE))
        self.assertEqual(self.fs.read('pwm3_enable'), str(AUTO_ENABLE_VALUE))

    def test_manual_channel_is_recovered_after_simulated_crash(self):
        # Igual que haría el Ajuste Rápido: fija manual sin pasar por fan_mappings.
        self.writer.set_channel_manual('it8792@/x/pwm2', self.channel, 100)
        self.assertEqual(self.fs.read('pwm2_enable'), str(MANUAL_ENABLE_VALUE))
        persisted = json.loads(self.state_path.read_text(encoding='utf-8'))
        self.assertEqual(persisted, {'it8792@/x/pwm2': 'pwm2_enable'})

        # "Crash": una instancia nueva (sin _managed en memoria) apunta al mismo
        # archivo de estado, simulando el próximo arranque de Algor.
        fresh_writer = PwmWriter(write_file=self.fs.write, read_file=self.fs.read, state_path=self.state_path)
        restored = fresh_writer.recover_from_previous_session()
        self.assertEqual(restored, ['it8792@/x/pwm2'])
        self.assertEqual(self.fs.read('pwm2_enable'), str(AUTO_ENABLE_VALUE))
        self.assertFalse(self.state_path.exists())

    def test_recovery_is_noop_when_channel_was_cleanly_restored(self):
        self.writer.set_channel_manual('it8792@/x/pwm2', self.channel, 100)
        ok = self.writer.set_channel_auto('it8792@/x/pwm2', self.channel)
        self.assertTrue(ok)
        # El archivo puede seguir existiendo (con {} vacío) tras la limpieza normal;
        # lo que importa es que ya no queda ningún canal pendiente de recuperar.
        self.assertEqual(json.loads(self.state_path.read_text(encoding='utf-8')), {})

        fresh_writer = PwmWriter(write_file=self.fs.write, read_file=self.fs.read, state_path=self.state_path)
        self.assertEqual(fresh_writer.recover_from_previous_session(), [])

    def test_recovery_never_touches_channels_it_never_set_manual(self):
        # Otro canal, en manual por una herramienta ajena a Algor: nunca debe tocarse.
        other_channel = make_channel(self.fs, pwm_path='pwm9', enable_path='pwm9_enable', chip='otro')
        self.fs.files['pwm9_enable'] = str(MANUAL_ENABLE_VALUE)

        self.writer.set_channel_manual('it8792@/x/pwm2', self.channel, 100)
        fresh_writer = PwmWriter(write_file=self.fs.write, read_file=self.fs.read, state_path=self.state_path)
        fresh_writer.recover_from_previous_session()

        self.assertEqual(self.fs.read('pwm9_enable'), str(MANUAL_ENABLE_VALUE))

    def test_no_unscoped_system_wide_sweep_on_module_exit(self):
        """La red de seguridad a nivel de módulo debe seguir acotada a lo que esta
        instancia gestionó; nunca a un barrido de todo /sys/class/hwmon del sistema
        (eso pisaba configuraciones manuales de otras herramientas)."""
        import algor.core.pwm_writer as pwm_writer_module
        self.assertFalse(hasattr(pwm_writer_module, '_global_cleanup'))


if __name__ == '__main__':
    unittest.main()
