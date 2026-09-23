#!/usr/bin/env python3
"""
Algor - Corsair Nautilus 360 RS & Linux Hardware Monitoring GUI
"""
import sys
import signal
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtCore import Qt, QTimer
from algor.core.config import config
from algor.core.logging_config import setup_logging
from algor.core.single_instance import SingleInstanceGuard
from algor.ui.main_window import MainWindow
from algor.ui.theme import Theme


def main():
    # Inicializar sistema de logging
    verbose = "--debug" in sys.argv or "--verbose" in sys.argv or "-v" in sys.argv
    setup_logging(verbose=verbose)

    # Configuración de renderizado y escalado HiDPI
    app = QApplication(sys.argv)
    app.setApplicationName("Algor")
    app.setApplicationDisplayName("Algor")
    app.setOrganizationName("OpenHardwareLinux")
    # Sin esto, Qt reporta el WM_CLASS/app_id de la ventana como "python3" (el nombre
    # del intérprete), que es EXACTAMENTE el "StartupWMClass=python3" que declara el
    # .desktop de Vorta — así que KWin confundía las dos ventanas entre sí.
    app.setDesktopFileName("algor")

    # Tamaño de fuente: por defecto Qt ya calculó uno acorde a QT_FONT_DPI y al
    # factor de escala de texto del sistema; si el usuario fijó uno manual en
    # Ajustes, se usa ese en su lugar.
    Theme.set_font_override(config.get("ui_font_point_size"))

    # Ctrl+C y `kill` deben pasar por el cierre limpio (_clean_exit), no terminar
    # abruptamente: si Reactivo dejó algún canal PWM en modo manual, el cierre
    # limpio es lo único que lo restaura a automático. SIG_DFL (el valor previo)
    # no llamaba a ninguna limpieza. El QTimer es necesario porque, con el bucle
    # de eventos de Qt bloqueado en C, Python no llega a procesar la señal.
    def _handle_shutdown_signal(signum, frame):
        QApplication.instance().quit()
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)
    _signal_timer = QTimer()
    _signal_timer.timeout.connect(lambda: None)
    _signal_timer.start(200)

    # Instancia única: si ya hay una corriendo, pedirle que se muestre y
    # salir sin crear una segunda ventana ni un segundo hilo de hardware/USB.
    guard = SingleInstanceGuard()
    if not guard.is_primary:
        return

    # Cargar y asignar icono de la aplicación
    from pathlib import Path
    from PyQt6.QtGui import QIcon
    icon_svg = Path(__file__).resolve().parent / "algor" / "assets" / "icons" / "Algor.svg"
    if icon_svg.exists():
        app.setWindowIcon(QIcon(str(icon_svg)))
    else:
        app.setWindowIcon(QIcon.fromTheme("algor"))

    # Iniciar ventana principal
    window = MainWindow()
    if icon_svg.exists():
        window.setWindowIcon(QIcon(str(icon_svg)))
    guard.activation_requested.connect(window.bring_to_front)

    if "--minimized" in sys.argv and QSystemTrayIcon.isSystemTrayAvailable():
        window.hide()
    else:
        window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

