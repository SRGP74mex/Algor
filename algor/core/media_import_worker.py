"""Importación sin ocupar el hilo GUI ni el propietario del LCD."""
from PyQt6.QtCore import QThread, pyqtSignal
from algor.core.media_library import import_media


class MediaImportWorker(QThread):
    imported = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            details = {}
            path = import_media(self.path, details)
            self.imported.emit(str(path), details["summary"])
        except Exception as exc:
            self.failed.emit(str(exc))
