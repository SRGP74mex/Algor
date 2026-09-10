"""Codificación offline del formato JPEG observado en Nautilus LCD Cap 0c57.

No inicializa dispositivos, lee sensores ni altera controles de refrigeración.
"""
from io import BytesIO
import struct

from PIL import Image

REPORT_SIZE = 1024
CHUNK_SIZE = 1016
MAX_JPEG_SIZE = 512 * 1024


def jpeg_reports(jpeg: bytes) -> list[bytes]:
    """Fragmenta un JPEG 480x480; rellena con ceros, no con residuos de iCUE.

    El byte 2 se fija en 03, como en las capturas iniciales. Su función sigue
    sin estar confirmada; no representa necesariamente brillo u orientación.
    """
    if not 4 <= len(jpeg) <= MAX_JPEG_SIZE:
        raise ValueError("JPEG vacío o superior al límite de prueba (512 KiB).")
    if not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
        raise ValueError("Se requiere un JPEG completo.")
    with Image.open(BytesIO(jpeg)) as image:
        if image.format != "JPEG" or image.size != (480, 480):
            raise ValueError("Se requiere JPEG de 480 × 480.")
        image.load()
    reports = []
    for index, offset in enumerate(range(0, len(jpeg), CHUNK_SIZE)):
        chunk = jpeg[offset:offset + CHUNK_SIZE]
        final = int(offset + len(chunk) == len(jpeg))
        header = b"\x02\x05\x03" + struct.pack("<BHH", final, index, len(chunk))
        reports.append((header + chunk).ljust(REPORT_SIZE, b"\0"))
    return reports
