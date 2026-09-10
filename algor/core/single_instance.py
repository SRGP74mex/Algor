"""Instancia única de la app: evita que un doble clic o un segundo lanzamiento
abran dos sesiones de hardware/USB en paralelo. Usa un socket local con
nombre (no un pidfile): si el proceso anterior murió sin limpiar, el socket
queda huérfano y Qt lo retira antes de escuchar de nuevo."""
import os

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from algor.core.logging_config import get_logger

logger = get_logger("single_instance")

_CONNECT_TIMEOUT_MS = 500
_ACTIVATE_MESSAGE = b"activate"


def server_name(uid=None) -> str:
    """Nombre del socket local, aislado por usuario del sistema (una máquina
    multiusuario no debe cruzar instancias entre sesiones distintas)."""
    return f"algor-{uid if uid is not None else os.getuid()}"


class SingleInstanceGuard(QObject):
    """Al construirse, `is_primary` indica si esta es la única instancia.
    Si no lo es, ya se le pidió a la instancia existente que se muestre y
    este proceso debe salir sin crear la ventana principal ni el hardware.
    Si lo es, `activation_requested` se emite cada vez que un lanzamiento
    posterior intenta abrir la app de nuevo."""
    activation_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = None
        self.is_primary = self._claim_or_notify()

    def _claim_or_notify(self) -> bool:
        name = server_name()
        probe = QLocalSocket(self)
        probe.connectToServer(name)
        if probe.waitForConnected(_CONNECT_TIMEOUT_MS):
            probe.write(_ACTIVATE_MESSAGE)
            probe.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
            probe.disconnectFromServer()
            logger.info("Ya hay una instancia de Algor en ejecución; se le pidió mostrarse.")
            return False
        # Nadie respondió: si quedó un socket huérfano de un cierre abrupto,
        # retirarlo antes de escuchar, para no fallar por "dirección en uso".
        QLocalServer.removeServer(name)
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        if not self._server.listen(name):
            logger.warning("No se pudo crear el socket de instancia única (%s); "
                            "continuando sin protección contra duplicados.",
                            self._server.errorString())
        return True

    def _on_new_connection(self):
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._on_ready_read(socket))
        socket.disconnected.connect(socket.deleteLater)

    def _on_ready_read(self, socket: QLocalSocket):
        socket.readAll()  # el contenido no importa hoy: cualquier mensaje activa
        self.activation_requested.emit()
