#!/usr/bin/env python3
"""Open/close the UI with simulated workers and temporary preferences; no hardware I/O."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _check_single_instance_guard(app):
    from algor.core.single_instance import SingleInstanceGuard
    primary = SingleInstanceGuard()
    assert primary.is_primary, 'la primera instancia debe reclamar el socket'
    activated = []
    primary.activation_requested.connect(lambda: activated.append(True))

    secondary = SingleInstanceGuard()
    assert not secondary.is_primary, 'una segunda instancia no debe reclamar el socket'

    for _ in range(20):
        app.processEvents()
        if activated:
            break
    assert activated, 'la instancia primaria debe recibir la solicitud de activación'
    if primary._server:
        primary._server.close()


def main():
    from PyQt6.QtWidgets import QApplication
    app = QApplication([])
    with tempfile.TemporaryDirectory(prefix='algor-smoke-') as folder, patch.object(Path, 'home', return_value=Path(folder)):
        _check_single_instance_guard(app)
        from algor.ui.main_window import MainWindow
        from algor.core.hardware import TelemetryData
        with patch('algor.core.hardware.HardwareSampler'), patch('algor.core.hardware.HardwareWorker.start'), patch('algor.core.lcd_worker.LCDWorker.start'):
            window = MainWindow()
            window.show()
            window._on_telemetry_updated(TelemetryData(cpu_temp_available=True, cpu_temp_package=42))
            app.processEvents()
            assert window.lcd_view.combo_memory.findData('custom') >= 0
            window.settings_view._open_fan_mapping()
            app.processEvents()
            window.settings_view.fan_mapping_dialog.close()
            window.bring_to_front()
            window._clean_exit()
    print('GUI smoke test passed; workers simulated, no USB/PWM writes.')


if __name__ == '__main__':
    main()
