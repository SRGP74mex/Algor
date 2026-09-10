#!/usr/bin/env python3
"""Prueba experimental de un cuadro estático. Solo escribe USB con --send.

Requiere el LCD liberado por VMware/iCUE y Algor cerrado. Usa el estado
existente del dispositivo: no presupone conocer la inicialización en frío.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import time

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from algor.core.lcd_protocol import jpeg_reports


def diagnostic_jpeg():
    """Patrón de diagnóstico, sin lecturas térmicas ficticias."""
    image = Image.new("RGB", (480, 480), "#101827")
    draw = ImageDraw.Draw(image)
    font_path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')

    def font(size):
        return ImageFont.truetype(str(font_path), size) if font_path.exists() else ImageFont.load_default()

    draw.ellipse((18, 18, 462, 462), outline="#00d9d0", width=9)
    draw.polygon([(240, 65), (212, 110), (229, 110), (229, 142),
                  (251, 142), (251, 110), (268, 110)], fill="#00d9d0")
    for y, text, size, color in [(182, "ALGOR", 43, "white"),
                                 (248, "LINUX", 54, "#00d9d0"),
                                 (315, "PRUEBA USB", 26, "white")]:
        draw.text((240, y), text, font=font(size), fill=color, anchor="mm")
    encoded = BytesIO()
    image.save(encoded, format="JPEG", quality=90, subsampling=0)
    return encoded.getvalue()


def transmit(reports, session_report=False, hold_seconds=0):
    import usb.core
    import usb.util

    devices = list(usb.core.find(find_all=True, idVendor=0x1b1c, idProduct=0x0c57))
    if len(devices) != 1:
        raise RuntimeError(f"Se esperaba un LCD 1b1c:0c57; detectados: {len(devices)}.")
    device = devices[0]
    detached = claimed = False
    sent = 0
    session_reports_sent = 0
    try:
        configuration = device.get_active_configuration()
        interface = configuration[(0, 0)]
        endpoint = next((ep for ep in interface if ep.bEndpointAddress == 0x09), None)
        if (interface.bInterfaceClass != 3 or endpoint is None
                or usb.util.endpoint_type(endpoint.bmAttributes) != usb.util.ENDPOINT_TYPE_INTR):
            raise RuntimeError("Interfaz HID/endpoint distintos de la captura; se cancela.")
        # No reset(), set_configuration() ni fuerza de desconexión de VMware.
        # Solo liberar temporalmente el controlador HID del kernel si está unido.
        if device.is_kernel_driver_active(0):
            device.detach_kernel_driver(0)
            detached = True
        usb.util.claim_interface(device, 0)
        claimed = True
        for report in reports:
            written = device.write(0x09, report, timeout=1000)
            if written != len(report):
                raise RuntimeError(f"Escritura parcial: {written}/{len(report)} bytes.")
            sent += 1
            time.sleep(0.001)
        if session_report:
            # Reporte periódico observado en TODAS las tomas iCUE con imagen.
            # Su función es hipótesis (sesión/watchdog), no un hecho establecido.
            # Los bytes 4–31 capturados eran restos del último fragmento JPEG.
            # Reproducimos ese patrón con nuestro último reporte, sin datos ajenos.
            payload = b'\x03\x19\x03\x01' + reports[-1][4:32]
            deadline = time.monotonic() + hold_seconds
            while True:
                written = device.ctrl_transfer(0x21, 0x09, 0x0303, 0, payload, timeout=1000)
                if written != 32:
                    raise RuntimeError(f'Reporte de sesión parcial: {written}/32 bytes.')
                session_reports_sent += 1
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(4.5, remaining))
        elif hold_seconds:
            time.sleep(hold_seconds)
        return dict(bus=device.bus, address=device.address, reports_sent=sent,
                    bytes_sent=sum(map(len, reports)), usb_completed=True,
                    session_reports_sent=session_reports_sent,
                    physical_result="pending_user_observation")
    finally:
        # Restaurar la interfaz incluso si hay timeout o escritura parcial.
        try:
            if claimed:
                usb.util.release_interface(device, 0)
        finally:
            try:
                if detached:
                    device.attach_kernel_driver(0)
            finally:
                usb.util.dispose_resources(device)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--send', action='store_true', help='Enviar exactamente un cuadro al LCD 1b1c:0c57.')
    parser.add_argument('--session-report', action='store_true',
                        help='Probar también el reporte periódico 03 19 03 01 observado en iCUE.')
    parser.add_argument('--hold-seconds', type=int, default=0,
                        help='Mantener la interfaz reclamada entre 0 y 30 s tras enviar la imagen.')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'captures' / 'linux_static_tests')
    args = parser.parse_args()
    if not 0 <= args.hold_seconds <= 30:
        parser.error('--hold-seconds debe estar entre 0 y 30.')
    jpeg = diagnostic_jpeg()
    reports = jpeg_reports(jpeg)
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = args.output / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    directory.mkdir(mode=0o700)
    (directory / 'preview.jpg').write_bytes(jpeg)
    result = dict(jpeg_bytes=len(jpeg), reports=len(reports),
                  sha256=hashlib.sha256(jpeg).hexdigest(), send_requested=args.send,
                  initialization='none; existing device state',
                  session_report=args.session_report, hold_seconds=args.hold_seconds,
                  brightness_changed=False, rotation_changed=False)
    try:
        if args.send:
            print('Enviando UN cuadro de prueba a Nautilus LCD Cap 1b1c:0c57...', flush=True)
            result.update(transmit(reports, session_report=args.session_report,
                                   hold_seconds=args.hold_seconds))
            print('Transferencias USB terminadas. Falta confirmar visualmente el LCD.')
        else:
            print('Preparación offline: no se abrió ningún dispositivo USB.')
    except Exception as exc:
        result.update(usb_completed=False, error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        (directory / 'result.json').write_text(json.dumps(result, indent=2))
        print('Resultado:', directory / 'result.json', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
