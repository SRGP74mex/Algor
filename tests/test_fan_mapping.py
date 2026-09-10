import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from algor.core.fan_mapping import (channel_identity, normalize_mapping, apply_pump_mapping,
                                        aggregate_confirmed_fan_rpm, eligible_for_pwm_write,
                                        apply_liquid_temp_mapping, valid_temp)
from algor.core.hardware import TelemetryData
from algor.core.alerts import AlertEngine
from algor.core.config import ConfigManager


class FanMappingTests(unittest.TestCase):
    key = 'it8792@/sys/devices/platform/it87.2656/fan1'

    def mapping(self, **kwargs):
        return {self.key: dict(role='pump', name='Bomba', confirmed=True, alarm=True,
                               minimum=1000, delay=3, **kwargs)}

    def data(self, rpm):
        return TelemetryData(cpu_temp_available=True, cpu_temp_package=40,
                             fan_channels={self.key: {'rpm': rpm, 'label': 'it8792 / fan1'}})

    def events(self, engine, rpm, now, mapping):
        engine.feed(self.data(rpm), now)
        return [e for e in engine.evaluate({}, now, fan_mappings=mapping) if e.key.startswith('rpm::')]

    def test_identity_survives_hwmon_renumber_and_distinguishes_chips(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            physical = root / 'devices/platform/it87.2656'
            physical.mkdir(parents=True)
            paths = []
            for number in (2, 9):
                base = root / f'hwmon{number}'
                base.mkdir()
                (base / 'device').symlink_to(physical, target_is_directory=True)
                paths.append(channel_identity(base, 'it8792', 'fan1'))
            self.assertEqual(*paths)
            other = root / 'hwmon10'
            other.mkdir()
            second = root / 'devices/platform/it87.3000'
            second.mkdir()
            (other / 'device').symlink_to(second, target_is_directory=True)
            self.assertNotEqual(paths[0], channel_identity(other, 'it8792', 'fan1'))

    def test_virtual_channel_without_identity_is_not_mapped(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder) / 'devices/virtual/hwmon/hwmon3'
            base.mkdir(parents=True)
            self.assertIsNone(channel_identity(base, 'virtualfan', 'fan1'))

    def test_confirmed_pump_zero_is_real_missing_is_unavailable(self):
        data = self.data(0)
        apply_pump_mapping(data, self.mapping())
        self.assertTrue(data.pump_rpm_available)
        self.assertEqual(data.pump_rpm, 0)
        data.fan_channels.clear()
        apply_pump_mapping(data, self.mapping())
        self.assertFalse(data.pump_rpm_available)

    def test_multiple_pumps_do_not_choose_arbitrarily(self):
        data = self.data(2200)
        mappings = self.mapping()
        mappings['other'] = mappings[self.key]
        apply_pump_mapping(data, mappings)
        self.assertFalse(data.pump_rpm_available)

    def test_low_rpm_debounce_recovery_margin_and_no_spam(self):
        engine, mapping = AlertEngine(), self.mapping()
        self.assertEqual(self.events(engine, 0, 0, mapping), [])
        event = self.events(engine, 0, 3, mapping)[0]
        self.assertEqual(event.level, 'critical')
        self.assertEqual(self.events(engine, 0, 4, mapping), [])
        self.assertEqual(self.events(engine, 1050, 5, mapping), [])
        self.assertEqual(self.events(engine, 1100, 6, mapping)[0].level, 'ok')

    def test_missing_is_not_reported_as_stopped_and_recovers(self):
        engine, mapping = AlertEngine(), self.mapping()
        self.events(engine, None, 0, mapping)
        event = self.events(engine, None, 3, mapping)[0]
        self.assertEqual(event.level, 'warning')
        self.assertIn('no disponible', event.message)
        self.assertEqual(self.events(engine, 2200, 4, mapping)[0].level, 'ok')

    def test_unused_unconfirmed_and_disabled_channels_never_alert(self):
        for edits in ({'role': 'unused'}, {'role': 'unknown'}, {'confirmed': False}, {'alarm': False}):
            mapping = self.mapping()
            mapping[self.key].update(edits)
            engine = AlertEngine()
            self.events(engine, 0, 0, mapping)
            self.assertEqual(self.events(engine, 0, 20, mapping), [])

    def test_removal_clears_existing_alarm_without_false_recovery(self):
        engine, mapping = AlertEngine(), self.mapping()
        self.events(engine, 0, 0, mapping)
        self.events(engine, 0, 3, mapping)
        event = self.events(engine, 0, 4, {})[0]
        self.assertEqual(event.level, 'disabled')
        self.assertEqual(engine.active_messages(), [])

    def test_stale_telemetry_marks_rpm_missing(self):
        engine, mapping = AlertEngine(), self.mapping()
        self.events(engine, 2200, 0, mapping)
        engine.evaluate({}, 11, fan_mappings=mapping)
        events = engine.evaluate({}, 14, fan_mappings=mapping)
        self.assertTrue(any(e.key.startswith('rpm::') and 'no disponible' in e.message for e in events))

    def test_aggregate_confirmed_fan_rpm_averages_confirmed_non_pump_channels(self):
        data = TelemetryData(fan_channels={
            'radiator1': {'rpm': 1200, 'label': 'Radiador 1'},
            'radiator2': {'rpm': 1400, 'label': 'Radiador 2'},
        })
        mappings = {
            'radiator1': dict(role='radiator', confirmed=True),
            'radiator2': dict(role='radiator', confirmed=True),
        }
        self.assertEqual(aggregate_confirmed_fan_rpm(data, mappings), 1300)

    def test_aggregate_confirmed_fan_rpm_excludes_pump_and_unconfirmed_and_alarm_only_channels(self):
        data = TelemetryData(fan_channels={
            self.key: {'rpm': 2200, 'label': 'Bomba'},
            'radiator1': {'rpm': 1200, 'label': 'Radiador 1'},
            'chassis1': {'rpm': 900, 'label': 'Chasis 1'},
        })
        mappings = {
            self.key: dict(role='pump', confirmed=True),
            'radiator1': dict(role='radiator', confirmed=True),
            'chassis1': dict(role='chassis', confirmed=False),
        }
        self.assertEqual(aggregate_confirmed_fan_rpm(data, mappings), 1200)

    def test_aggregate_confirmed_fan_rpm_returns_none_without_valid_confirmed_reading(self):
        data = TelemetryData(fan_channels={'radiator1': {'rpm': None, 'label': 'Radiador 1'}})
        mappings = {'radiator1': dict(role='radiator', confirmed=True)}
        self.assertIsNone(aggregate_confirmed_fan_rpm(data, mappings))
        self.assertIsNone(aggregate_confirmed_fan_rpm(data, {}))

    def test_pump_never_becomes_pwm_tested_even_if_forged(self):
        # Estructural, no una convención de UI: ni un config.json editado a mano
        # puede volver elegible a la bomba para escritura PWM. Ver docs/PWM_REAL_CONTROL.md.
        forged = dict(role='pump', confirmed=True, pwm_tested=True,
                      pwm_channel='it8792@/x/pwm1')
        value = normalize_mapping(forged)
        self.assertFalse(value['pwm_tested'])
        self.assertEqual(value['pwm_channel'], '')
        self.assertFalse(eligible_for_pwm_write(forged))

    def test_pwm_tested_requires_confirmed_and_valid_role(self):
        base = dict(role='radiator', pwm_tested=True, pwm_channel='it8792@/x/pwm2')
        self.assertFalse(normalize_mapping({**base, 'confirmed': False})['pwm_tested'])
        for role in ('unknown', 'unused'):
            self.assertFalse(normalize_mapping({**base, 'role': role, 'confirmed': True})['pwm_tested'])
        value = normalize_mapping({**base, 'confirmed': True})
        self.assertTrue(value['pwm_tested'])
        self.assertEqual(value['pwm_channel'], 'it8792@/x/pwm2')

    def test_eligible_for_pwm_write_requires_channel_and_tested(self):
        confirmed_radiator = dict(role='radiator', confirmed=True)
        self.assertFalse(eligible_for_pwm_write(confirmed_radiator))
        self.assertFalse(eligible_for_pwm_write({**confirmed_radiator, 'pwm_tested': True}))
        self.assertTrue(eligible_for_pwm_write(
            {**confirmed_radiator, 'pwm_tested': True, 'pwm_channel': 'it8792@/x/pwm2'}))

    def test_valid_temp_rejects_disconnected_diode_and_out_of_range(self):
        # -55°C se observó de verdad en un canal sin usar de este equipo: no es
        # "cero real", es ruido de un diodo desconectado.
        self.assertFalse(valid_temp(-55))
        self.assertFalse(valid_temp(200))
        self.assertFalse(valid_temp(None))
        self.assertTrue(valid_temp(0))
        self.assertTrue(valid_temp(45.5))
        self.assertTrue(valid_temp(125))

    def test_apply_liquid_temp_mapping_single_confirmed_channel(self):
        data = TelemetryData(temp_channels={'it8620@/x/temp2': {'label': 'it8620 / temp2', 'temp': 31.0}})
        mappings = {'it8620@/x/temp2': dict(role='liquid_temp', confirmed=True)}
        apply_liquid_temp_mapping(data, mappings)
        self.assertTrue(data.liquid_temp_available)
        self.assertEqual(data.liquid_temp, 31.0)
        self.assertFalse(data.liquid_temp_is_estimated)

    def test_apply_liquid_temp_mapping_never_guesses_between_multiple(self):
        data = TelemetryData(temp_channels={
            'it8620@/x/temp2': {'label': 'a', 'temp': 31.0},
            'it8792@/x/temp1': {'label': 'b', 'temp': 22.0},
        })
        mappings = {
            'it8620@/x/temp2': dict(role='liquid_temp', confirmed=True),
            'it8792@/x/temp1': dict(role='liquid_temp', confirmed=True),
        }
        apply_liquid_temp_mapping(data, mappings)
        self.assertFalse(data.liquid_temp_available)

    def test_apply_liquid_temp_mapping_ignores_unconfirmed_and_implausible(self):
        data = TelemetryData(temp_channels={'it8620@/x/temp3': {'label': 'c', 'temp': -55.0}})
        mappings = {'it8620@/x/temp3': dict(role='liquid_temp', confirmed=True)}
        apply_liquid_temp_mapping(data, mappings)
        self.assertFalse(data.liquid_temp_available)
        mappings = {'it8620@/x/temp3': dict(role='liquid_temp', confirmed=False)}
        apply_liquid_temp_mapping(data, mappings)
        self.assertFalse(data.liquid_temp_available)

    def test_mapping_persists_and_invalid_options_are_sanitized(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(Path, 'home', return_value=Path(folder)):
            config = ConfigManager()
            config.set('fan_mappings', self.mapping())
            self.assertEqual(ConfigManager().get('fan_mappings'), self.mapping())
        value = normalize_mapping(dict(role='unused', alarm=True, confirmed=True, minimum=-1, delay='bad'))
        self.assertFalse(value['alarm'])
        self.assertEqual(value['minimum'], 1)
        self.assertEqual(value['delay'], 5)
