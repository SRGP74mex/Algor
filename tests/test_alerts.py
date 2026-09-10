import json
import tempfile
import unittest
from pathlib import Path
from algor.core.alerts import AlertEngine, AlertEvent, EventJournal
from algor.core.hardware import TelemetryData
from algor.core.thermal_response import (
    ThermalResponseStatus, INSUFFICIENT_DATA, NO_RISE, RESPONDING, NOT_RESPONDING,
)


class AlertTests(unittest.TestCase):
    def sample(self, temp=60, **kwargs):
        return TelemetryData(cpu_temp_available=True, cpu_temp_package=temp, **kwargs)

    def test_critical_immediate_hysteresis_no_spam_and_recovery(self):
        engine = AlertEngine()
        engine.feed(self.sample(91), 0)
        self.assertEqual(engine.evaluate({}, 0)[0].level, 'critical')
        self.assertEqual(engine.evaluate({}, 1), [])
        engine.feed(self.sample(88), 2)
        self.assertEqual(engine.evaluate({}, 2), [])
        engine.feed(self.sample(85), 3)
        self.assertEqual(engine.evaluate({}, 3)[0].level, 'warning')
        engine.feed(self.sample(78), 4)
        self.assertEqual(engine.evaluate({}, 4), [])
        engine.feed(self.sample(76), 5)
        self.assertEqual(engine.evaluate({}, 5)[0].level, 'ok')

    def test_warning_requires_duration_and_resets_on_short_spike(self):
        engine = AlertEngine()
        engine.feed(self.sample(81), 0)
        self.assertEqual(engine.evaluate({}, 0), [])
        engine.feed(self.sample(60), 1)
        self.assertEqual(engine.evaluate({}, 1), [])
        engine.feed(self.sample(81), 2)
        self.assertEqual(engine.evaluate({}, 2), [])
        self.assertEqual(engine.evaluate({}, 4)[0].level, 'warning')

    def test_stalled_worker_and_missing_temperature_do_not_clear_critical(self):
        engine = AlertEngine()
        engine.feed(self.sample(95), 0)
        engine.evaluate({}, 0)
        events = engine.evaluate({}, 11)
        self.assertIn('telemetry', [e.key for e in events])
        self.assertEqual(engine.states['cpu_temperature'][0], 'critical')
        engine.feed(TelemetryData(), 12)
        engine.evaluate({}, 12)
        events = engine.evaluate({}, 21)
        self.assertIn('cpu_sensor', [e.key for e in events])
        self.assertEqual(engine.states['cpu_temperature'][0], 'critical')
        engine.feed(self.sample(), 22)
        self.assertIn('cpu_temperature', [e.key for e in engine.evaluate({}, 22)])

    def test_gpu_absence_is_not_alarm_but_loss_after_detection_is(self):
        engine = AlertEngine()
        engine.feed(self.sample(), 0)
        engine.evaluate({}, 0)
        self.assertFalse(any(k.startswith('gpu') for k in engine.states))
        engine.feed(self.sample(gpu_temp=95, gpu_temp_available=True), 1)
        self.assertIn('gpu_temperature', [e.key for e in engine.evaluate({}, 1)])
        engine.feed(self.sample(), 2)
        engine.evaluate({}, 2)
        engine.feed(self.sample(), 12)
        self.assertIn('gpu_sensor', [e.key for e in engine.evaluate({}, 12)])

    def test_invalid_numeric_sensor_is_missing(self):
        engine = AlertEngine()
        engine.feed(self.sample(float('nan')), 0)
        engine.evaluate({}, 0)
        engine.feed(self.sample(float('inf')), 10)
        self.assertIn('cpu_sensor', [e.key for e in engine.evaluate({}, 10)])

    def test_lcd_transient_failure_stop_recovery_and_disable(self):
        engine = AlertEngine()
        engine.feed(self.sample(), 0)
        self.assertEqual(engine.evaluate({}, 0, 'error'), [])
        self.assertEqual(engine.evaluate({}, 3, 'active'), [])
        engine.evaluate({}, 4, 'error')
        engine.feed(self.sample(), 14)
        self.assertIn('lcd', [e.key for e in engine.evaluate({}, 14, 'error')])
        events = engine.evaluate({}, 15, 'idle')
        self.assertEqual(events[0].message, 'LCD: sesión detenida.')
        engine.feed(self.sample(99), 16)
        engine.evaluate({}, 16)
        self.assertEqual(engine.evaluate({'enabled': False}, 17)[0].level, 'disabled')
        self.assertEqual(engine.active_messages(), [])
        self.assertEqual(engine.evaluate({'enabled': False}, 18), [])

    def test_non_numeric_thresholds_fall_back_instead_of_raising(self):
        engine = AlertEngine()
        engine.feed(self.sample(95), 0)
        # cfg con umbrales corruptos (config.json editado a mano): no debe lanzar
        # ValueError y debe seguir evaluando con los valores por defecto (crit=90).
        events = engine.evaluate({'cpu_temp_warn': 'alto', 'cpu_temp_crit': None}, 0)
        self.assertEqual(events[0].level, 'critical')

    def test_thermal_response_alert_fires_after_sustained_not_responding_while_hot(self):
        engine = AlertEngine()
        status = ThermalResponseStatus(NOT_RESPONDING, delta_temp_c=5.0, delta_rpm=0.0)
        for t in (0, 8):
            engine.feed(self.sample(91), t, thermal_response=status)
            events = [e for e in engine.evaluate({}, t) if e.key == 'thermal_response']
            self.assertEqual(events, [])
        engine.feed(self.sample(91), 16, thermal_response=status)
        events = [e for e in engine.evaluate({}, 16) if e.key == 'thermal_response']
        self.assertEqual(events[0].level, 'warning')

    def test_thermal_response_alert_does_not_fire_when_temperature_is_ok(self):
        engine = AlertEngine()
        status = ThermalResponseStatus(NOT_RESPONDING)
        for t in (0, 8, 16, 24):
            engine.feed(self.sample(60), t, thermal_response=status)
            events = [e for e in engine.evaluate({}, t) if e.key == 'thermal_response']
            self.assertEqual(events, [])

    def test_thermal_response_alert_does_not_fire_on_insufficient_data_or_no_rise(self):
        for status in (None, ThermalResponseStatus(INSUFFICIENT_DATA), ThermalResponseStatus(NO_RISE, delta_temp_c=1.0)):
            engine = AlertEngine()
            for t in (0, 8, 16, 24):
                engine.feed(self.sample(91), t, thermal_response=status)
                events = [e for e in engine.evaluate({}, t) if e.key == 'thermal_response']
                self.assertEqual(events, [])

    def test_thermal_response_alert_recovers_when_responding_resumes(self):
        engine = AlertEngine()
        not_responding = ThermalResponseStatus(NOT_RESPONDING)
        events = []
        for t in (0, 8, 16):
            engine.feed(self.sample(91), t, thermal_response=not_responding)
            events = [e for e in engine.evaluate({}, t) if e.key == 'thermal_response']
        self.assertEqual(events[0].level, 'warning')
        responding = ThermalResponseStatus(RESPONDING, delta_temp_c=5.0, delta_rpm=300.0)
        engine.feed(self.sample(91), 20, thermal_response=responding)
        events = [e for e in engine.evaluate({}, 20) if e.key == 'thermal_response']
        self.assertEqual(events[0].level, 'ok')

    def test_journal_rotates_and_records_utc_json(self):
        with tempfile.TemporaryDirectory() as folder:
            journal = EventJournal(folder)
            journal.handler.maxBytes = 200
            for _ in range(20):
                journal.record(AlertEvent('cpu', 'warning', 'Temperatura elevada'))
            journal.close()
            paths = list(Path(folder).glob('events.jsonl*'))
            self.assertEqual(len(paths), 4)
            record = json.loads((Path(folder) / 'events.jsonl').read_text().splitlines()[0])
            self.assertEqual(record['level'], 'warning')
            self.assertTrue(record['time'].endswith('+00:00'))
