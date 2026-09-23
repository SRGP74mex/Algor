import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from algor.core.config import DEFAULT_CONFIG, ConfigManager


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        # Aislado del ~/.config/algor real: sin esto, cada corrida de la suite
        # leía y escribía la configuración real de quien ejecuta los tests.
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        patcher = patch.object(Path, "home", return_value=Path(self._tmpdir.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.config_mgr = ConfigManager()

    def test_default_profiles_exist(self):
        profiles = self.config_mgr.get("profiles")
        self.assertIsNotNone(profiles)
        self.assertIn("silent", profiles)
        self.assertIn("balanced", profiles)
        self.assertIn("extreme", profiles)
        self.assertNotIn("zero_rpm", profiles)
        self.assertIn("custom", profiles)

    def test_get_and_set_value(self):
        self.config_mgr.set("temperature_unit", "C")
        self.assertEqual(self.config_mgr.get("temperature_unit"), "C")

    def test_curve_retrieval(self):
        curve = self.config_mgr.get_curve("balanced")
        self.assertIsInstance(curve, list)
        self.assertGreater(len(curve), 0)
        self.assertIn("temp", curve[0])
        self.assertIn("pwm", curve[0])

    def test_legacy_zero_rpm_is_removed_and_saved(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            config_file = Path(directory) / ".config" / "algor" / "config.json"
            config_file.parent.mkdir(parents=True)
            config_file.write_text(json.dumps({
                "active_profile": "zero_rpm",
                "profiles": {"zero_rpm": [{"temp": 20, "pwm": 0}]},
                "polling_interval_ms": 1500,
            }))
            manager = ConfigManager()
            self.assertEqual(manager.get("active_profile"), "balanced")
            self.assertNotIn("zero_rpm", manager.get("profiles"))
            saved = json.loads(config_file.read_text())
            self.assertEqual(saved["active_profile"], "balanced")
            self.assertNotIn("zero_rpm", saved["profiles"])
            self.assertEqual(saved["polling_interval_ms"], 1500)
            with self.assertRaises(ValueError):
                manager.set_curve("zero_rpm", [{"temp": 20, "pwm": 0}])

    def test_merge_dicts_preserves_new_keys(self):
        default = {"a": 1, "nested": {"k1": "v1", "k2": "v2"}}
        custom = {"a": 2, "nested": {"k1": "modified"}}
        merged = self.config_mgr._merge_dicts(default, custom)
        self.assertEqual(merged["a"], 2)
        self.assertEqual(merged["nested"]["k1"], "modified")
        self.assertEqual(merged["nested"]["k2"], "v2")

    def test_save_survives_truncated_write(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            manager = ConfigManager()
            manager.set("temperature_unit", "F")
            config_file = Path(directory) / ".config" / "algor" / "config.json"
            config_file.write_text('{"temperature_unit": "F", "profiles":')  # truncado a mitad de escritura
            restarted = ConfigManager()
            self.assertEqual(restarted.get("temperature_unit"), "C")
            self.assertEqual(restarted.get("profiles"), DEFAULT_CONFIG["profiles"])

    def test_save_is_atomic_no_temp_file_left_behind(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            manager = ConfigManager()
            manager.set("temperature_unit", "F")
            config_dir = Path(directory) / ".config" / "algor"
            leftovers = [p for p in config_dir.iterdir() if p.name != "config.json"]
            self.assertEqual(leftovers, [])
            self.assertEqual(json.loads((config_dir / "config.json").read_text())["temperature_unit"], "F")

    def test_config_dir_and_file_get_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            manager = ConfigManager()
            manager.save()
            config_dir = Path(directory) / ".config" / "algor"
            self.assertEqual(config_dir.stat().st_mode & 0o777, 0o700)
            self.assertEqual((config_dir / "config.json").stat().st_mode & 0o777, 0o600)

    def test_invalid_curve_shape_falls_back_to_default_profile(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            config_file = Path(directory) / ".config" / "algor" / "config.json"
            config_file.parent.mkdir(parents=True)
            config_file.write_text(json.dumps({
                "profiles": {"balanced": "no-es-una-curva", "silent": [{"temp": "caliente", "pwm": 10}]},
            }))
            manager = ConfigManager()
            self.assertEqual(manager.get_curve("balanced"), DEFAULT_CONFIG["profiles"]["balanced"])
            self.assertEqual(manager.get_curve("silent"), DEFAULT_CONFIG["profiles"]["silent"])
            self.assertEqual(manager.get("profiles")["extreme"], DEFAULT_CONFIG["profiles"]["extreme"])

    def test_invalid_active_profile_falls_back_to_balanced(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            config_file = Path(directory) / ".config" / "algor" / "config.json"
            config_file.parent.mkdir(parents=True)
            config_file.write_text(json.dumps({"active_profile": "inexistente"}))
            manager = ConfigManager()
            self.assertEqual(manager.get("active_profile"), "balanced")

    def test_non_numeric_alert_threshold_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            config_file = Path(directory) / ".config" / "algor" / "config.json"
            config_file.parent.mkdir(parents=True)
            config_file.write_text(json.dumps({
                "alerts": {"cpu_temp_warn": "alto", "cpu_temp_crit": True, "gpu_temp_warn": 70},
            }))
            manager = ConfigManager()
            alerts = manager.get("alerts")
            self.assertEqual(alerts["cpu_temp_warn"], DEFAULT_CONFIG["alerts"]["cpu_temp_warn"])
            self.assertEqual(alerts["cpu_temp_crit"], DEFAULT_CONFIG["alerts"]["cpu_temp_crit"])
            self.assertEqual(alerts["gpu_temp_warn"], 70)  # el valor válido del usuario se conserva

    def test_ui_font_point_size_defaults_to_automatic(self):
        self.assertIsNone(self.config_mgr.get("ui_font_point_size"))

    def test_valid_ui_font_point_size_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            config_file = Path(directory) / ".config" / "algor" / "config.json"
            config_file.parent.mkdir(parents=True)
            config_file.write_text(json.dumps({"ui_font_point_size": 14}))
            manager = ConfigManager()
            self.assertEqual(manager.get("ui_font_point_size"), 14)

    def test_invalid_ui_font_point_size_falls_back_to_automatic(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            config_file = Path(directory) / ".config" / "algor" / "config.json"
            config_file.parent.mkdir(parents=True)
            config_file.write_text(json.dumps({"ui_font_point_size": "grande"}))
            manager = ConfigManager()
            self.assertIsNone(manager.get("ui_font_point_size"))

    def test_out_of_range_ui_font_point_size_falls_back_to_automatic(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(Path, "home", return_value=Path(directory)):
            config_file = Path(directory) / ".config" / "algor" / "config.json"
            config_file.parent.mkdir(parents=True)
            config_file.write_text(json.dumps({"ui_font_point_size": 200}))
            manager = ConfigManager()
            self.assertIsNone(manager.get("ui_font_point_size"))


if __name__ == "__main__":
    unittest.main()

