import unittest
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
        self.writer = PwmWriter(write_file=self.fs.write, read_file=self.fs.read)
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
        self.writer = PwmWriter(write_file=self.fs.write, read_file=self.fs.read)
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


if __name__ == '__main__':
    unittest.main()
