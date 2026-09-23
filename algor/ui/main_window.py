import sys
import time
from algor.core.alerts import AlertEngine, AlertEvent, EventJournal
from typing import Optional, Tuple
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QEvent, QTimer, QByteArray
from PyQt6.QtGui import QMouseEvent, QIcon, QAction, QColor, QPainter, QPen
from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QTabWidget, QFrame, QSystemTrayIcon, QMenu, QApplication,
                             QGraphicsDropShadowEffect, QSizeGrip)
from algor.core.hardware import HardwareWorker, TelemetryData
from algor.core.i18n import _
from algor.core.lcd_worker import LCDWorker
from algor.core.fan_controller import FanCurveEngine
from algor.core.thermal_response import ThermalResponseMonitor
from algor.core.config import config
from algor.ui.theme import Theme
from algor.ui.views.dashboard_view import DashboardView
from algor.ui.views.curves_view import CurvesView
from algor.ui.views.lcd_view import LCDView
from algor.ui.views.settings_view import SettingsView


class TrafficLightButton(QWidget):
    """Botón semáforo macOS pintado directamente con QPainter (círculo sólido real),
    en vez de QPushButton + QSS — el estilo nativo Breeze no pintaba el relleno
    de forma confiable en botones tan pequeños."""
    clicked = pyqtSignal()

    def __init__(self, color: str, hover_color: str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self._hover_color = QColor(hover_color)
        self._hovered = False
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._hover_color if self._hovered else self._color)
        painter.drawEllipse(self.rect())
        if self._hovered:
            painter.setPen(QPen(QColor(255, 255, 255, 160), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))
        painter.end()


class TitleBar(QFrame):
    """Barra de título personalizada estilo macOS con soporte completo de arrastre y maximizado."""

    def __init__(self, parent_window: QMainWindow):
        super().__init__(parent_window)
        self.parent_window = parent_window
        self.setFixedHeight(48)
        self.setStyleSheet("background: transparent;")
        self._drag_pos = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 16, 0)
        layout.setSpacing(10)

        # Botones Semáforo (Traffic Lights estilo macOS)
        self.btn_close = TrafficLightButton("#ff5f56", "#ff3b30", _("Cerrar (Minimiza a la bandeja)"))
        self.btn_close.clicked.connect(self.parent_window.close)

        self.btn_min = TrafficLightButton("#ffbd2e", "#ffaa00", _("Minimizar"))
        self.btn_min.clicked.connect(self.parent_window.showMinimized)

        self.btn_max = TrafficLightButton("#27c93f", "#24b238", _("Maximizar / Restaurar"))
        self.btn_max.clicked.connect(self.parent_window._toggle_maximize)

        layout.addWidget(self.btn_close)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)

        layout.addStretch()

        # Logo y Título Centrado estilo Custos: marca de la app arriba, modelo
        # del hardware Corsair más discreto debajo (no es el nombre de la app).
        app_badge = QWidget()
        app_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        badge_layout = QVBoxLayout(app_badge)
        badge_layout.setContentsMargins(0, 0, 0, 0)
        badge_layout.setSpacing(0)
        lbl_app = QLabel("❖  Algor")
        lbl_app.setStyleSheet(f"font-weight: 600; font-size: {Theme.pt(0)}pt; color: #c3c7db; letter-spacing: 0.5px;")
        lbl_app.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_app.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        badge_layout.addWidget(lbl_app)
        lbl_hardware = QLabel("Corsair Nautilus 360 RS")
        lbl_hardware.setStyleSheet(f"font-size: {Theme.pt(-4)}pt; color: #6b7280; letter-spacing: 0.3px;")
        lbl_hardware.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_hardware.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        badge_layout.addWidget(lbl_hardware)
        layout.addWidget(app_badge)

        layout.addStretch()

        # Insignia de estado en vivo estilo Custos
        self.lbl_status_pill = QLabel(_("● LCD detenido"))
        self.lbl_status_pill.setStyleSheet(
            "background-color: #122822; color: #10b981; padding: 3px 10px; border-radius: 8px; "
            f"border: 1px solid #1c4b38; font-size: {Theme.pt(-2)}pt; font-weight: 600;"
        )
        self.lbl_status_pill.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        layout.addWidget(self.lbl_status_pill)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.parent_window.frameGeometry().topLeft()
            win_handle = self.parent_window.windowHandle()
            if win_handle and hasattr(win_handle, 'startSystemMove'):
                win_handle.startSystemMove()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.MouseButton.LeftButton and not self._drag_pos.isNull():
            self.parent_window.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = QPoint()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.parent_window._toggle_maximize()
            event.accept()


class MainWindow(QMainWindow):
    """Ventana principal moderna con estilo macOS / Dark Glassmorphism."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Algor - Corsair Nautilus 360 RS")
        self.resize(1020, 680)
        self.setMinimumSize(880, 580)

        # Activar ventana sin marco para controles estilo macOS
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # Motores de Hardware y Control
        self._exiting = False
        self._lcd_status = ("idle", _("LCD detenido"))
        self.fan_engine = FanCurveEngine()
        self.thermal_response = ThermalResponseMonitor()
        self.worker = HardwareWorker(
            corsair_reader=None,
            interval_ms=config.get("polling_interval_ms", 1000),
            fan_engine=self.fan_engine
        )
        self.worker.telemetry_updated.connect(self._on_telemetry_updated)

        self._init_ui()
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.setInterval(500)
        self._geometry_timer.timeout.connect(self._save_window_geometry)
        geometry = config.get('window_geometry', '')
        if isinstance(geometry, str) and geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode('ascii')))
            except (ValueError, UnicodeError):
                pass
        self._init_tray()
        self.alert_engine = AlertEngine(time.monotonic())
        self.event_journal = EventJournal()
        self.event_journal.record(AlertEvent('app', 'info', _('Algor iniciado.')))
        self.settings_view.btn_test_alert.clicked.connect(self._test_alert)
        self.settings_view.slider_poll.valueChanged.connect(self.worker.set_interval)
        self.alert_banner = QLabel(_('Esperando lecturas de sensores…'))
        self.alert_banner.setWordWrap(True)
        self.alert_banner.setContentsMargins(16, 4, 16, 4)
        self.glass.layout().insertWidget(1, self.alert_banner)
        self._alert_timer = QTimer(self)
        self._alert_timer.setInterval(1000)
        self._alert_timer.timeout.connect(self._evaluate_alerts)
        self._alert_timer.start()

        # Iniciar hilo de monitoreo en segundo plano
        self.lcd_worker = LCDWorker(self.lcd_view.lcd_cfg)
        self.lcd_view.settings_changed.connect(self.lcd_worker.configure)
        self.lcd_view.session_requested.connect(self.lcd_worker.set_active)
        self.lcd_view.memory_query_requested.connect(lambda: self.lcd_worker.request_memory_save('check'))
        self.lcd_view.memory_prepare_requested.connect(self.lcd_worker.request_memory_prepare)
        self.lcd_worker.memory_prepared.connect(self.lcd_view.set_prepared_memory)
        self.lcd_view.memory_requested.connect(self.lcd_worker.request_memory_save)
        self.lcd_worker.memory_status.connect(self.lcd_view.set_memory_status)
        self.lcd_worker.preview_ready.connect(self.lcd_view.lcd_preview.set_jpeg)
        self.lcd_worker.status_changed.connect(self._on_lcd_status)
        self.lcd_worker.lifecycle_event.connect(lambda text: self.event_journal.record(
            AlertEvent('lcd_session', 'info', text)))
        self.settings_view.real_control_toggled.connect(self.fan_engine.set_real_control_enabled)
        self.worker.stale_channel_restored.connect(self._on_stale_pwm_restored)
        self.dashboard_view.worker = self.worker
        self.settings_view.worker = self.worker
        QApplication.instance().aboutToQuit.connect(self._clean_exit)
        self.lcd_worker.start()
        self.worker.start()
        if self.lcd_view.chk_autostart.isChecked():
            self.lcd_view.set_session_requested(True)

    def _init_ui(self):
        self.setStyleSheet(Theme.build_stylesheet())

        # Widget raíz transparente: deja ver el escritorio en los márgenes/esquinas
        root = QWidget()
        root.setObjectName("Root")
        outer_layout = QVBoxLayout(root)
        outer_layout.setContentsMargins(14, 14, 14, 14)
        outer_layout.setSpacing(0)

        # Tarjeta "glass" que contiene toda la interfaz, con sombra difusa flotante
        self.glass = glass = QFrame()
        glass.setObjectName("Glass")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(48)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 160))
        glass.setGraphicsEffect(shadow)
        outer_layout.addWidget(glass)

        # Manija de redimensionamiento (la ventana es "frameless": sin ella no hay
        # forma de arrastrar los bordes para agrandarla, como sí permite Custos).
        # OJO: se debe llamar a raise_() otra vez DESPUÉS de agregar las pestañas
        # (más abajo) — si no, el QTabWidget queda por encima y la tapa por completo,
        # dejándola invisible e inutilizable aunque exista.
        self.size_grip = QSizeGrip(glass)
        self.size_grip.setStyleSheet("background: transparent;")
        self.size_grip.setFixedSize(16, 16)
        self.size_grip.setToolTip(_("Arrastra para redimensionar la ventana"))

        central_layout = QVBoxLayout(glass)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 1. Barra de Título Superior personalizada
        self.titlebar = TitleBar(self)
        central_layout.addWidget(self.titlebar)

        # 2. Pestañas de Navegación (Tabs)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.dashboard_view = DashboardView()
        self.dashboard_view.profile_requested.connect(self._on_profile_switched)

        self.curves_view = CurvesView()
        self.curves_view.manual_pwm_requested.connect(self._on_manual_pwm)

        self.lcd_view = LCDView()
        self.settings_view = SettingsView()

        self.tabs.addTab(self.dashboard_view, _("📊 Panel General"))
        self.tabs.addTab(self.curves_view, _("🎛️ Simulación de curvas"))
        self.tabs.addTab(self.lcd_view, _("🖥️ Pantalla LCD Cap"))
        self.tabs.addTab(self.settings_view, _("⚙️ Ajustes"))

        central_layout.addWidget(self.tabs)
        self.setCentralWidget(root)

        # Habilitar seguimiento del ratón e instalar filtros de evento para
        # redimensionar la ventana desde cualquier borde o esquina
        self.setMouseTracking(True)
        root.setMouseTracking(True)
        glass.setMouseTracking(True)
        root.installEventFilter(self)
        glass.installEventFilter(self)

        # Ahora sí: todos los hermanos (titlebar, tabs) ya existen, así que esto
        # la deja realmente al frente, encima de cualquier contenido de las pestañas.
        self.size_grip.raise_()

    def _get_resize_edges(self, global_pos: QPoint) -> Tuple[Optional[Qt.Edge], Optional[Qt.CursorShape]]:
        """Calcula si el cursor está sobre un borde o esquina para redimensionar."""
        pos = self.mapFromGlobal(global_pos)
        w = self.width()
        h = self.height()
        margin = 18  # Área de captura de borde en píxeles

        left = pos.x() <= margin
        right = pos.x() >= w - margin
        top = pos.y() <= margin
        bottom = pos.y() >= h - margin

        if top and left:
            return (Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.CursorShape.SizeFDiagCursor)
        if top and right:
            return (Qt.Edge.TopEdge | Qt.Edge.RightEdge, Qt.CursorShape.SizeBDiagCursor)
        if bottom and left:
            return (Qt.Edge.BottomEdge | Qt.Edge.LeftEdge, Qt.CursorShape.SizeBDiagCursor)
        if bottom and right:
            return (Qt.Edge.BottomEdge | Qt.Edge.RightEdge, Qt.CursorShape.SizeFDiagCursor)
        if left:
            return (Qt.Edge.LeftEdge, Qt.CursorShape.SizeHorCursor)
        if right:
            return (Qt.Edge.RightEdge, Qt.CursorShape.SizeHorCursor)
        if top:
            return (Qt.Edge.TopEdge, Qt.CursorShape.SizeVerCursor)
        if bottom:
            return (Qt.Edge.BottomEdge, Qt.CursorShape.SizeVerCursor)

        return (None, None)

    def eventFilter(self, obj, event):
        """Filtro de eventos para interceptar hover y clic en los bordes de la ventana."""
        if event.type() == QEvent.Type.MouseMove:
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                edges, cursor_shape = self._get_resize_edges(event.globalPosition().toPoint())
                if cursor_shape is not None:
                    self.setCursor(cursor_shape)
                else:
                    self.unsetCursor()
        elif event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                edges, _unused = self._get_resize_edges(event.globalPosition().toPoint())
                if edges is not None:
                    win_handle = self.windowHandle()
                    if win_handle and hasattr(win_handle, 'startSystemResize'):
                        win_handle.startSystemResize(edges)
                        return True
        elif event.type() == QEvent.Type.Leave:
            self.unsetCursor()

        return super().eventFilter(obj, event)

    def _init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        from pathlib import Path
        icon_path = Path(__file__).resolve().parent.parent.parent / "algor" / "assets" / "icons" / "Algor.svg"
        if icon_path.exists():
            app_icon = QIcon(str(icon_path))
        else:
            app_icon = QIcon.fromTheme("algor", self.style().standardIcon(self.style().StandardPixmap.SP_ComputerIcon))
        self.tray_icon.setIcon(app_icon)
        self.setWindowIcon(app_icon)

        tray_menu = QMenu()
        tray_menu.setStyleSheet(f"""
            QMenu {{ background-color: {Theme.BG_PANEL}; color: {Theme.TEXT_WHITE}; border: 1px solid {Theme.BORDER_SUBTLE}; padding: 4px; }}
            QMenu::item:selected {{ background-color: {Theme.BG_CARD_HOVER}; color: {Theme.CYAN}; }}
        """)

        action_show = QAction(_("🖥️ Abrir Algor"), self)
        action_show.triggered.connect(self._show_from_tray)
        tray_menu.addAction(action_show)

        tray_menu.addSeparator()

        # Perfiles rápidos en el Tray
        prof_menu = tray_menu.addMenu(_("⚡ Perfil de simulación"))
        for p_key, p_name in [("silent", _("Silencioso")), ("balanced", _("Equilibrado")), ("extreme", _("Extremo"))]:
            act = QAction(p_name, self)
            act.triggered.connect(lambda chk, k=p_key: self._on_profile_switched(k))
            prof_menu.addAction(act)

        tray_menu.addSeparator()
        action_quit = QAction(_("❌ Salir"), self)
        action_quit.triggered.connect(self._clean_exit)
        tray_menu.addAction(action_quit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.size_grip.move(
            self.glass.width() - self.size_grip.width() - 4,
            self.glass.height() - self.size_grip.height() - 4,
        )
        self.size_grip.raise_()
        self._schedule_geometry_save()

    def _schedule_geometry_save(self):
        if hasattr(self, '_geometry_timer') and not self.isMinimized():
            self._last_window_geometry = (bytes(self.saveGeometry().toBase64()).decode('ascii'), self.isMaximized())
            self._geometry_timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._schedule_geometry_save()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._schedule_geometry_save()

    def _save_window_geometry(self):
        if not self.isMinimized():
            self._last_window_geometry = (bytes(self.saveGeometry().toBase64()).decode('ascii'), self.isMaximized())
        if hasattr(self, '_last_window_geometry'):
            geometry, maximized = self._last_window_geometry
            config.set('window_geometry', geometry)
            config.set('window_maximized', maximized)

    def bring_to_front(self):
        """Restaura y enfoca la ventana, sin importar si está minimizada u
        oculta en la bandeja. Usado por el menú de bandeja y por
        SingleInstanceGuard cuando un segundo lanzamiento pide activarse."""
        if self.isMinimized():
            if config.get('window_maximized', False):
                self.showMaximized()
            else:
                self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _show_from_tray(self):
        self.bring_to_front()

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _on_profile_switched(self, profile_name: str):
        self.fan_engine.set_profile(profile_name)
        self.curves_view.set_active_profile(profile_name)

    def _on_manual_pwm(self, pwm_percent: int):
        self.fan_engine.record_target_pwm(pwm_percent)
        self.worker.request_manual_pwm(pwm_percent)

    def _on_stale_pwm_restored(self, identities: str):
        """Un canal probado quedó en modo manual porque una sesión anterior murió
        sin limpiar (kill -9, cuelgue). Se restauró a automático antes de hacer
        cualquier otra cosa — ver PwmWriter.restore_stale_manual_channels."""
        text = _('Canal PWM restaurado a automático (sesión anterior sin cierre limpio): {channels}').format(channels=identities)
        self.event_journal.record(AlertEvent('pwm', 'warning', text))
        self.tray_icon.showMessage('Algor · PWM', text, QSystemTrayIcon.MessageIcon.Warning, 8000)

    def _on_telemetry_updated(self, data: TelemetryData):
        from algor.core.fan_mapping import (apply_pump_mapping, apply_liquid_temp_mapping,
                                             aggregate_confirmed_fan_rpm, eligible_for_pwm_write)
        mappings = config.get("fan_mappings", {})
        apply_pump_mapping(data, mappings)
        apply_liquid_temp_mapping(data, mappings)
        self.curves_view.set_pwm_eligible(any(eligible_for_pwm_write(m) for m in mappings.values()))
        self.settings_view.set_pwm_eligible(mappings)
        # Comparación solo-lectura: ¿el RPM confirmado responde cuando sube la
        # temperatura que mueve la curva simulada? Ver docs/PLAN_X99_Y_LCD.md.
        observed_rpm = aggregate_confirmed_fan_rpm(data, mappings)
        control_temp = data.cpu_temp_package if data.cpu_temp_available else None
        self.thermal_response.record_sample(control_temp, observed_rpm, data.timestamp)
        response_status = self.thermal_response.status()
        self.alert_engine.feed(data, time.monotonic(), thermal_response=response_status)
        self._evaluate_alerts()
        # El cálculo del PWM simulado ya ocurrió en HardwareWorker (hilo de
        # hardware, no el de la interfaz) — aquí solo se distribuye lo ya calculado.

        # Distribuir a vistas
        data.corsair_connected = self._lcd_status[0] == "active"
        data.corsair_info = self._lcd_status[1]
        self.dashboard_view.update_telemetry(data)
        self.curves_view.update_telemetry(data, data.calculated_pwm)
        self.curves_view.update_thermal_response(response_status)
        self.lcd_worker.update_telemetry(data)
        self.settings_view.feed_telemetry(data)

        # Tooltip del System Tray
        na = _('N/D')
        self.tray_icon.setToolTip(
            f"Algor: CPU {str(round(data.cpu_temp_package, 1)) + '°C' if data.cpu_temp_available else na} | {self._lcd_status[1]}"
        )

    def _on_lcd_status(self, state, message):
        if state != self._lcd_status[0]:
            self.event_journal.record(AlertEvent('lcd_session', state, message))
        self._lcd_status = (state, message)
        self.lcd_view.set_status(state, message)
        self.titlebar.lbl_status_pill.setText(
            {"active": _("● LCD activo"), "error": _("● Revisar LCD")}.get(state, _("● LCD detenido")))
        self.titlebar.lbl_status_pill.setToolTip(message)

    def _notify_alert(self, event):
        self.event_journal.record(event)
        icon = (QSystemTrayIcon.MessageIcon.Critical if event.level == 'critical' else
                QSystemTrayIcon.MessageIcon.Warning if event.level == 'warning' else
                QSystemTrayIcon.MessageIcon.Information)
        self.tray_icon.showMessage(_('Algor · supervisión'), event.message, icon, 10000)

    def _test_alert(self):
        self._notify_alert(AlertEvent('test', 'info', _('Prueba de notificación; no es una alarma real.')))
        self.settings_view.lbl_alert_status.setText(
            _('Prueba enviada y registrada. La notificación depende de los ajustes del escritorio.'))

    def _evaluate_alerts(self):
        cfg = config.get('alerts', {})
        for event in self.alert_engine.evaluate(cfg, time.monotonic(), self._lcd_status[0], config.get('fan_mappings', {})):
            self._notify_alert(event)
        messages = self.alert_engine.active_messages()
        status = (' | '.join(messages) if messages else
                  _('Sin alertas activas en los sensores supervisados.') if self.alert_engine.received is not None
                  else _('Esperando lecturas de sensores…'))
        if not cfg.get('enabled', True):
            status = _('Supervisión de alertas desactivada.')
        if self.event_journal.error:
            status += _(' No se pudo escribir el historial: ') + self.event_journal.error
        self.settings_view.lbl_alert_status.setText(status)
        self.alert_banner.setText(status)
        self.alert_banner.setStyleSheet('color: #ffbd69;' if messages or self.event_journal.error else 'color: #9ba9bb;')

    def closeEvent(self, event):
        self._save_window_geometry()
        if config.get("minimize_to_tray", True) and QSystemTrayIcon.isSystemTrayAvailable():
            event.ignore()
            self.hide()
            self.tray_icon.showMessage(
                "Algor",
                _("La aplicación sigue ejecutándose en segundo plano manteniendo el LCD y monitoreando sensores."),
                QSystemTrayIcon.MessageIcon.Information,
                2000
            )
        else:
            self._clean_exit()

    def _clean_exit(self):
        if self._exiting:
            return
        self._exiting = True
        self._alert_timer.stop()
        self._geometry_timer.stop()
        self._save_window_geometry()
        self.lcd_view.stop_import()
        self.lcd_worker.stop()
        try:
            self.worker.pwm_writer.restore_all_system_channels(self.worker.sampler.scan_pwm_channels())
        except Exception:
            pass
        self.worker.stop()
        self.settings_view.logger.stop()
        self.event_journal.record(AlertEvent("app", "info", _("Algor cerrado.")))
        self.event_journal.close()
        QApplication.quit()
