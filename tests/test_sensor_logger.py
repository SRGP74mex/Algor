import os
import tempfile
import unittest
from pathlib import Path
from algor.core.hardware import TelemetryData
from algor.core.sensor_logger import SensorLogger


class TestSensorLogger(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.logger = SensorLogger()

    def tearDown(self):
        self.logger.stop()

    def test_logger_lifecycle(self):
        data = TelemetryData(
            cpu_temp_package=35.0,
            gpu_temp=50.0,
            liquid_temp=28.0,
            pump_rpm=1500
        )
        sensor_ids = ["cpu_temp_package", "gpu_temp"]
        ok, res = self.logger.start(
            directory=self.tmp_dir,
            sensor_ids=sensor_ids,
            interval_sec=0.1,
            duration_min=None,
            latest_data=data
        )
        self.assertTrue(ok)
        self.assertTrue(self.logger.active)
        self.assertTrue(os.path.exists(res))

        # Escribir fila
        self.logger.feed(data)
        self.logger.stop()
        self.assertFalse(self.logger.active)

        # Verificar contenido CSV
        with open(res, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertGreaterEqual(len(lines), 1)
            self.assertIn("timestamp", lines[0])
            self.assertIn("CPU Package", lines[0])


if __name__ == "__main__":
    unittest.main()

