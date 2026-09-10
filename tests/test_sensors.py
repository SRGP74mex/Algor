import unittest
from algor.core.hardware import TelemetryData
from algor.core.sensors import build_sensor_list, get_sensor_map, STATIC_SENSORS


class TestSensors(unittest.TestCase):
    def test_static_sensors_defined(self):
        self.assertGreater(len(STATIC_SENSORS), 0)
        sensor_ids = [s.id for s in STATIC_SENSORS]
        self.assertIn("cpu_temp_package", sensor_ids)
        self.assertIn("gpu_temp", sensor_ids)
        self.assertIn("liquid_temp", sensor_ids)
        self.assertIn("pump_rpm", sensor_ids)

    def test_dynamic_sensors_discovery(self):
        mock_data = TelemetryData()
        mock_data.fans_rpm = {"it8620_fan2": 1650, "it8792_fan2": 1450}
        mock_data.fans_pwm = {"it8620_pwm1": 35}
        mock_data.nvme_temps = [27.0, 31.0]

        sensors = build_sensor_list(mock_data)
        sensor_map = get_sensor_map(mock_data)

        self.assertIn("fan_rpm::it8620_fan2", sensor_map)
        self.assertIn("fan_pwm::it8620_pwm1", sensor_map)
        self.assertIn("nvme_temp::0", sensor_map)

        # Probar getter
        rpm_val = sensor_map["fan_rpm::it8620_fan2"].getter(mock_data)
        self.assertEqual(rpm_val, 1650)


if __name__ == "__main__":
    unittest.main()

