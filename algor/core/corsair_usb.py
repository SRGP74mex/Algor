"""Transporte exclusivo del Nautilus LCD Cap, basado en capturas verificadas.

Solo el trabajador LCD debe crear y utilizar esta clase. No ofrece sensores,
PWM ni firmware. La prueba de memoria usa únicamente muestras capturadas. Ver docs/PROTOCOLO_LCD_CAP_OBSERVADO.md.
"""
import time
import usb.core
import usb.util
from algor.core.i18n import _
from algor.core.lcd_protocol import jpeg_reports

CORSAIR_VID = 0x1b1c
NAUTILUS_PID = 0x0c57
SUPPORTED_PIDS = {NAUTILUS_PID: 'Corsair Nautilus LCD Cap'}


class CorsairNautilusDevice:
    def __init__(self):
        self.dev = None
        self._detached = False
        self._claimed = False
        self._tail = bytes(28)

    def connect(self):
        if self.dev is not None:
            return
        devices = list(usb.core.find(find_all=True, idVendor=CORSAIR_VID, idProduct=NAUTILUS_PID))
        if len(devices) != 1:
            raise RuntimeError(_('LCD no conectado a Linux. Libera el Nautilus desde VMware.') if not devices
                               else _('Hay varios Nautilus LCD; conecta uno para esta sesión.'))
        self.dev = devices[0]
        try:
            intf = self.dev.get_active_configuration()[(0, 0)]
            endpoint = next((e for e in intf if e.bEndpointAddress == 0x09), None)
            if (intf.bInterfaceClass != 3 or endpoint is None or
                    usb.util.endpoint_type(endpoint.bmAttributes) != usb.util.ENDPOINT_TYPE_INTR):
                raise RuntimeError(_('La interfaz del LCD no coincide con el protocolo admitido.'))
            if self.dev.is_kernel_driver_active(0):
                self.dev.detach_kernel_driver(0)
                self._detached = True
            # Si VMware u otra aplicación mantiene la interfaz, no se fuerza su salida.
            usb.util.claim_interface(self.dev, 0)
            self._claimed = True
        except Exception:
            self.disconnect()
            raise

    def _feature(self, prefix):
        if not self._claimed:
            raise RuntimeError(_('La interfaz LCD no está reclamada.'))
        data = prefix + self._tail
        count = self.dev.ctrl_transfer(0x21, 0x09, 0x0303, 0, data, timeout=500)
        if count != 32:
            raise RuntimeError(_('Reporte de control incompleto: {count}/32 bytes.').format(count=count))

    def read_feature(self, report_id):
        if report_id not in (0x0a, 0x0b, 0x0f) or not self._claimed:
            raise ValueError(_('Consulta de memoria no admitida o interfaz no reclamada.'))
        result = bytes(self.dev.ctrl_transfer(0xa1, 0x01, 0x0300 | report_id, 0, 32, timeout=500))
        if len(result) != 32 or result[0] != report_id:
            raise RuntimeError(_('Respuesta HID incompleta o identificador inesperado.'))
        return result

    def write_feature_report(self, report):
        if not self._claimed or len(report) != 32 or report[:2] not in (b'\x03\x1c', b'\x03\x1b'):
            raise ValueError(_('Reporte de finalización no admitido.'))
        if self.dev.ctrl_transfer(0x21, 9, 0x0303, 0, report, timeout=500) != 32:
            raise RuntimeError(_('Finalización incompleta; resultado de memoria incierto.'))

    def write_memory_report(self, report):
        if not self._claimed or len(report) != 1024 or report[:2] != b'\x02\x06':
            raise ValueError(_('Reporte de memoria no admitido.'))
        if self.dev.write(0x09, report, timeout=500) != 1024:
            raise RuntimeError(_('Carga incompleta; resultado de memoria incierto.'))

    def send_jpeg(self, jpeg, cancelled=lambda: False):
        if not self._claimed:
            raise RuntimeError(_('La interfaz LCD no está reclamada.'))
        reports = jpeg_reports(jpeg)
        deadline = time.monotonic() + 3.0
        for report in reports:
            if cancelled():
                raise InterruptedError(_('Sesión detenida.'))
            if time.monotonic() >= deadline:
                raise TimeoutError(_('El cuadro LCD excedió el tiempo de transmisión.'))
            if self.dev.write(0x09, report, timeout=500) != len(report):
                raise RuntimeError(_('Transferencia de imagen incompleta.'))
            time.sleep(0.001)
        self._tail = reports[-1][4:32]

    def keep_alive(self):
        # Mantener sesión: patrón que mostró físicamente el primer cuadro Linux.
        self._feature(b'\x03\x19\x03\x01')

    def set_brightness(self, percent):
        if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= 100:
            raise ValueError(_('El brillo debe ser un entero entre 0 y 100.'))
        self._feature(bytes([3, 0x0b, percent, 1]))

    def disconnect(self):
        dev, claimed, detached = self.dev, self._claimed, self._detached
        self.dev = None
        self._claimed = self._detached = False
        self._tail = bytes(28)
        if dev is None:
            return
        error = None
        try:
            if claimed:
                usb.util.release_interface(dev, 0)
        except Exception as exc:
            error = exc
        try:
            if detached:
                dev.attach_kernel_driver(0)
        except Exception as exc:
            error = error or exc
        finally:
            try:
                usb.util.dispose_resources(dev)
            except Exception as exc:
                error = error or exc
        if error is not None:
            # Una desconexión física puede impedir restaurar el driver.
            from algor.core.logging_config import get_logger
            get_logger('lcd').warning('No se pudo restaurar la interfaz HID: %s', error)
