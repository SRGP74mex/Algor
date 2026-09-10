import unittest
from algor.core.fan_controller import FanCurveEngine


class TestFanCurveEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FanCurveEngine()

    def test_calculate_pwm_boundary_low(self):
        # Con temperatura muy baja (ej. 10°C), debe devolver el PWM del primer punto
        self.engine.set_profile("balanced")
        pwm = self.engine.calculate_pwm(10.0)
        self.assertGreaterEqual(pwm, 0)
        self.assertLessEqual(pwm, 100)

    def test_calculate_pwm_boundary_high(self):
        # Con temperatura muy alta (ej. 95°C), debe devolver el PWM máximo
        self.engine.set_profile("balanced")
        pwm = self.engine.calculate_pwm(95.0)
        self.assertEqual(pwm, 100)

    def test_removed_profile_falls_back_to_balanced(self):
        self.engine.set_profile("zero_rpm")
        self.assertEqual(self.engine.active_profile, "balanced")
        self.assertGreater(self.engine.calculate_pwm(30.0), 0)

    def test_hysteresis_dampening(self):
        self.engine.set_profile("balanced")
        # Subir a 70°C
        pwm_hot = self.engine.calculate_pwm(70.0)
        # Bajar bruscamente a 69.5°C -> histéresis amortigua la caída
        pwm_cool = self.engine.calculate_pwm(69.5)
        self.assertGreaterEqual(pwm_cool, 0)
        self.assertLessEqual(pwm_cool, pwm_hot)

    def test_no_leftover_pwm_write_scaffolding(self):
        # Regresión: el motor nunca debe volver a fingir soporte de escritura
        # hwmon real (ver docs/PLAN_X99_Y_LCD.md: solo lectura, siempre).
        self.assertFalse(hasattr(self.engine, 'pwm_files_found'))
        self.assertFalse(hasattr(self.engine, 'permission_denied'))

    def test_record_target_pwm_only_clamps_and_stores(self):
        self.engine.record_target_pwm(-10)
        self.assertEqual(self.engine._last_target_pwm, 0)
        self.engine.record_target_pwm(150)
        self.assertEqual(self.engine._last_target_pwm, 100)
        self.engine.set_profile("balanced")
        self.assertGreaterEqual(self.engine.calculate_pwm(50.0), 0)

    def test_real_control_always_starts_disabled_regardless_of_config(self):
        # Decisión deliberada (no un descuido): dado el historial de apagones del
        # usuario, Reactivo nunca sobrevive un reinicio. Ver docs/PWM_REAL_CONTROL.md.
        self.assertFalse(self.engine.real_control_enabled)
        self.assertFalse(FanCurveEngine().real_control_enabled)

    def test_set_real_control_enabled_does_not_persist_to_config(self):
        from algor.core.config import config
        before = config.get('fan_control_mode', 'auto')
        self.engine.set_real_control_enabled(True)
        self.assertTrue(self.engine.real_control_enabled)
        self.assertEqual(config.get('fan_control_mode', 'auto'), before)
        self.assertFalse(FanCurveEngine().real_control_enabled)


if __name__ == "__main__":
    unittest.main()

