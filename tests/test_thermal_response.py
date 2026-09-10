"""Monitor de respuesta térmica: solo lectura, nunca sugiere un valor de PWM."""
import unittest

from algor.core.thermal_response import (
    INSUFFICIENT_DATA, NO_RISE, RPM_UNAVAILABLE, RESPONDING, NOT_RESPONDING,
    ThermalResponseMonitor,
)


class ThermalResponseTests(unittest.TestCase):
    def monitor(self, **kwargs):
        defaults = dict(window_seconds=180, min_window_seconds=60, min_samples=6,
                         temp_rise_c=3.0, rpm_rise=150.0, resume_gap_seconds=30)
        defaults.update(kwargs)
        return ThermalResponseMonitor(**defaults)

    def feed(self, monitor, samples):
        for t, temp, rpm in samples:
            monitor.record_sample(temp, rpm, t)

    def test_insufficient_data_before_min_samples(self):
        monitor = self.monitor()
        self.feed(monitor, [(i * 10, 50.0, 1000) for i in range(3)])
        self.assertEqual(monitor.status().state, INSUFFICIENT_DATA)

    def test_insufficient_data_before_min_window(self):
        monitor = self.monitor()
        # 6 muestras pero todas dentro de una ventana temporal muy corta.
        self.feed(monitor, [(i, 50.0, 1000) for i in range(6)])
        self.assertEqual(monitor.status().state, INSUFFICIENT_DATA)

    def test_no_rise_is_neutral_not_a_failure(self):
        monitor = self.monitor()
        self.feed(monitor, [(i * 15, 50.0, 1000) for i in range(8)])
        self.assertEqual(monitor.status().state, NO_RISE)

    def test_responding_when_temp_and_rpm_rise_together(self):
        monitor = self.monitor()
        samples = [(i * 15, 50.0 + i, 1000 + i * 60) for i in range(8)]
        self.feed(monitor, samples)
        status = monitor.status()
        self.assertEqual(status.state, RESPONDING)
        self.assertGreater(status.delta_temp_c, 0)
        self.assertGreater(status.delta_rpm, 0)

    def test_not_responding_when_temp_rises_but_rpm_stays_flat(self):
        monitor = self.monitor()
        samples = [(i * 15, 50.0 + i, 1000) for i in range(8)]
        self.feed(monitor, samples)
        self.assertEqual(monitor.status().state, NOT_RESPONDING)

    def test_rpm_unavailable_distinct_from_not_responding(self):
        monitor = self.monitor()
        samples = [(i * 15, 50.0 + i, None) for i in range(8)]
        self.feed(monitor, samples)
        status = monitor.status()
        self.assertEqual(status.state, RPM_UNAVAILABLE)
        self.assertNotEqual(status.state, NOT_RESPONDING)

    def test_suspend_clock_jump_resets_window_instead_of_false_negative(self):
        monitor = self.monitor()
        # Ventana normal con temperatura subiendo y RPM plano (implicaría NOT_RESPONDING).
        self.feed(monitor, [(i * 15, 50.0 + i, 1000) for i in range(8)])
        self.assertEqual(monitor.status().state, NOT_RESPONDING)
        # Salto de reloj grande (suspensión/reanudación).
        monitor.record_sample(90.0, 1000, 100000)
        self.assertEqual(monitor.status().state, INSUFFICIENT_DATA)

    def test_clock_regression_resets_window(self):
        monitor = self.monitor()
        self.feed(monitor, [(i * 15, 50.0 + i, 1000) for i in range(8)])
        self.assertEqual(monitor.status().state, NOT_RESPONDING)
        monitor.record_sample(90.0, 1000, 5)  # reloj retrocedido
        self.assertEqual(monitor.status().state, INSUFFICIENT_DATA)

    def test_reset_clears_all_samples(self):
        monitor = self.monitor()
        self.feed(monitor, [(i * 15, 50.0 + i, 1000) for i in range(8)])
        monitor.reset()
        self.assertEqual(monitor.status().state, INSUFFICIENT_DATA)


if __name__ == '__main__':
    unittest.main()
