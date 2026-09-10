"""Memoria LCD: muestras capturadas y preparación experimental de medios propios.

La temporización del campo común sigue siendo una hipótesis. Preparación offline
separada del transporte; ninguna escritura al importar.
"""
from dataclasses import dataclass
from io import BytesIO
import hashlib
import struct
import time
import zlib
from PIL import Image
from algor.core.media_library import MAX_FRAMES

# SHA-256 de JPEG y envoltura completa, ver PROTOCOLO_LCD_CAP_OBSERVADO.md.
CAPTURED_IMAGES = {
    'A': ('bdb2cccf4155fe440faf546bdcac76c9a0e98239b75c275d994b22155ba1be4d', '01e001e0010100ce030f520000'),
    'B': ('6c6965cd92a05e566f789379ef9b55902e89a06804b95fa45e808fb81cfebe5e', '01e001e0010100d403b4e20000'),
    'C': ('352e7a99ad82bf9713c9a8c0a5c19cd344e46e92d80be6c7e6a1840ce8fac5c2', '01e001e0010100b60314d00000'),
}


@dataclass(frozen=True)
class CapturedMemoryImage:
    label: str
    jpeg: bytes

    def prepare(self):
        if self.label not in CAPTURED_IMAGES:
            raise ValueError('Solo se admiten las muestras capturadas A, B y C.')
        expected_hash, envelope_hex = CAPTURED_IMAGES[self.label]
        if hashlib.sha256(self.jpeg).hexdigest() != expected_hash:
            raise ValueError('El JPEG no coincide con la muestra capturada; no se escribirá.')
        envelope = bytes.fromhex(envelope_hex)
        if struct.unpack_from('<I', envelope, 9)[0] != len(self.jpeg):
            raise ValueError('Longitud de envoltura inválida.')
        with Image.open(BytesIO(self.jpeg)) as image:
            if image.format != 'JPEG' or image.size != (480, 480):
                raise ValueError('Formato de imagen inválido.')
            image.load()
        content = envelope + self.jpeg
        total = struct.pack('<I', len(content))
        initial = b'\x02\x06' + total + bytes.fromhex('00000100010004000000')
        reports = [initial.ljust(1024, b'\0')]
        for index, offset in enumerate(range(0, len(content), 1008)):
            chunk = content[offset:offset + 1008]
            final = int(offset + len(chunk) == len(content))
            header = b'\x02\x06' + total + b'\x01\x00\x01\x00' + bytes([final, 1]) + struct.pack('<HH', len(chunk), index)
            reports.append((header + chunk).ljust(1024, b'\0'))
        return reports, struct.pack('<I', zlib.crc32(self.jpeg))


def save_captured_image(device, image, progress=lambda message: None, diagnostics=None):
    """Una sola transacción, sin reconectar ni reintentar al fallar.

    El llamador debe poseer la interfaz. Después del primer OUT, un error puede
    significar escritura parcial o completada sin confirmación. No cancelarla
    entre fragmentos por minimizar/cerrar una ventana ni repetirla al reconectar.
    """
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics["phase"] = "validating"
    reports, crc = image.prepare()
    previous = device.read_feature(0x0f)
    diagnostics.update(previous_report=previous.hex(), previous_crc32_le=previous[1:5].hex(), expected_crc32_le=crc.hex())
    # El CRC solo cubre JPEG, no el intervalo. Un GIF propio puede tener el mismo
    # CRC y necesitar actualizar su velocidad mediante un guardado explícito.
    timing_update = isinstance(image, PreparedMemoryMedia) and len(image.frames) > 1
    diagnostics["timing_update_requested"] = timing_update
    if timing_update:
        diagnostics.update(interval_field=image.interval_field, target_duration_ms=image.interval_field * len(image.frames))
    if previous[1:5] == crc and not timing_update:
        return dict(outcome='already_stored', crc32_le=crc.hex(), previous_crc32_le=crc.hex())
    diagnostics["preflight_report"] = device.read_feature(0x0b).hex()
    diagnostics.update(phase="uploading", reports_sent=0)
    progress('Enviando contenido a memoria…')
    deadline = time.monotonic() + max(5, min(30, len(reports) * 0.003 + 5))
    for report in reports:
        if time.monotonic() >= deadline:
            raise TimeoutError('Tiempo de carga agotado; resultado incierto. No se reintentó.')
        device.write_memory_report(report)
        diagnostics["reports_sent"] += 1
        time.sleep(0.001)
    expected_pages = struct.unpack_from('<H', reports[-1], 6)[0]
    diagnostics.update(phase='waiting', status_reports=[], expected_pages=expected_pages)
    progress('Esperando finalización del dispositivo…')
    last_completed = None
    deadline = time.monotonic() + 5
    while True:
        state = device.read_feature(0x0a)
        diagnostics["status_reports"].append(state.hex())
        if len(state) != 32 or state[0] != 0x0a:
            raise RuntimeError('Respuesta de progreso inválida; no se enviaron órdenes finales.')
        completed_pages = int.from_bytes(state[1:5], 'little')
        diagnostics['completed_pages'] = completed_pages
        if completed_pages != last_completed and completed_pages <= expected_pages:
            progress(f'Procesando memoria: {completed_pages}/{expected_pages} bloques…')
            last_completed = completed_pages
        if completed_pages == expected_pages:
            break
        if completed_pages > expected_pages:
            raise RuntimeError(f'Progreso inesperado: {completed_pages}/{expected_pages} bloques; no se enviaron órdenes finales.')
        if time.monotonic() >= deadline:
            raise TimeoutError('Memoria sin confirmación; no se enviaron órdenes finales ni se reintentó.')
        time.sleep(0.01)
    # Conservar las colas observadas derivadas del último informe, nunca memoria
    # ajena de iCUE. Los primeros seis bytes de 0x1c llevan el CRC del JPEG.
    last = reports[-1]
    finalizer = b'\x03\x1c' + crc + last[6:32]
    diagnostics["phase"] = "finalizing_crc"
    device.write_feature_report(finalizer)
    diagnostics["phase"] = "finalizing_selection"
    device.write_feature_report(b'\x03\x1b\x00' + finalizer[3:])
    diagnostics["phase"] = "verifying"
    diagnostics['verification_reports'] = []
    # El dispositivo puede publicar el CRC después de responder a SET_REPORT.
    # Solo se repiten consultas: nunca la carga ni las órdenes finales.
    for attempt in range(21):
        response = device.read_feature(0x0f)
        actual = response[1:5]
        diagnostics['verification_reports'].append(response.hex())
        diagnostics.update(actual_report=response.hex(), actual_crc32_le=actual.hex())
        if actual == crc:
            break
        if attempt < 20:
            time.sleep(0.1)
    else:
        raise RuntimeError(f'CRC esperado {crc.hex()}, leído {actual.hex()}. Resultado incierto; no se reintentó la escritura.')
    return dict(outcome='crc_verified', crc32_le=crc.hex(), previous_crc32_le=previous[1:5].hex(),
                reports=len(reports), physical_persistence='pending')


def load_captured_image(label):
    from pathlib import Path
    if label not in CAPTURED_IMAGES:
        raise ValueError('Imagen de memoria desconocida.')
    image = CapturedMemoryImage(label, (Path(__file__).resolve().parent.parent / 'assets' / 'memory' / f'{label}.jpg').read_bytes())
    image.prepare()
    return image


def inspect_stored_image(device):
    """Identifica por CRC, sin enviar imágenes ni SET_REPORT de memoria."""
    response = device.read_feature(0x0f)
    if len(response) != 32 or response[0] != 0x0f:
        raise ValueError('Respuesta de memoria incompleta o inesperada.')
    crc = response[1:5].hex()
    known = {'3ee0fd35': 'A', '9e2bfc94': 'B', '1c068d9b': 'C'}
    return dict(outcome='queried', actual_report=response.hex(), actual_crc32_le=crc,
                identified_image=known.get(crc), physical_persistence='not_observed')


MAX_MEMORY_BYTES = 12 * 1024 * 1024


def memory_reports(content):
    if not 13 < len(content) <= MAX_MEMORY_BYTES:
        raise ValueError('Contenido de memoria fuera del límite de 12 MiB.')
    total = struct.pack('<I', len(content))
    reports = [(b'\x02\x06' + total + bytes.fromhex('00000100010004000000')).ljust(1024, b'\0')]
    for page_index, offset in enumerate(range(0, len(content), 131072), 1):
        page = content[offset:offset + 131072]
        last_page = int(offset + len(page) == len(content))
        for index, start in enumerate(range(0, len(page), 1008)):
            chunk = page[start:start + 1008]
            last_chunk = int(start + len(chunk) == len(page))
            header = b'\x02\x06' + total + struct.pack('<H', page_index) + b'\x01\x00' + bytes([last_chunk, last_page]) + struct.pack('<HH', len(chunk), index)
            reports.append((header + chunk).ljust(1024, b'\0'))
    return reports


@dataclass(frozen=True)
class PreparedMemoryMedia:
    label: str
    frames: tuple
    source_durations: tuple
    rotation: int
    optimization_summary: str = ""

    @property
    def interval_field(self):
        if len(self.frames) == 1:
            return 974  # Envoltura estática ya probada; no cambia esta prueba.
        if not self.frames or len(self.source_durations) != len(self.frames):
            raise ValueError('Faltan duraciones de los cuadros.')
        if any(type(value) is not int or not 1 <= value <= 60000 for value in self.source_durations):
            raise ValueError('Duración de GIF fuera del intervalo admitido.')
        return max(10, round(sum(self.source_durations) / len(self.frames)))

    def prepare(self):
        if not 1 <= len(self.frames) <= MAX_FRAMES:
            raise ValueError('Cantidad de cuadros fuera del límite.')
        # Hipótesis experimental: intervalo común en ms. Preserva duración total
        # aproximada, no pausas diferentes de cuadros individuales.
        field = self.interval_field
        for jpeg in self.frames:
            if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                raise ValueError('JPEG inválido.')
        payload = b''.join(self.frames)
        header = b'\x01' + struct.pack('<HHHH', 480, 480, len(self.frames), field)
        header += b''.join(struct.pack('<I', len(frame)) for frame in self.frames)
        return memory_reports(header + payload), struct.pack('<I', zlib.crc32(payload))


def prepare_custom_media(path, rotation=0):
    from pathlib import Path
    from PIL import ImageOps
    from algor.core.media_library import MAX_FILE_BYTES
    from bisect import bisect_right
    path = Path(path)
    if rotation not in (0, 90, 180, 270):
        raise ValueError('Giro inválido.')
    with path.open('rb') as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError('Archivo superior a 25 MiB.')
    deadline = time.monotonic() + 30
    def check_time():
        if time.monotonic() > deadline:
            raise TimeoutError('La optimización excedió 30 segundos. Usa un archivo más pequeño.')
    with Image.open(BytesIO(data)) as source:
        count = getattr(source, 'n_frames', 1)
        if source.format not in ('GIF', 'PNG', 'JPEG', 'BMP', 'WEBP') or (count > 1 and source.format != 'GIF'):
            raise ValueError('Formato de imagen no admitido; las animaciones deben ser GIF.')
        if count > 600 or source.width * source.height > 25_000_000 or count * source.width * source.height > 150_000_000:
            raise ValueError('Origen demasiado complejo: máximo 600 cuadros, 25 megapíxeles por cuadro y 150 megapíxeles acumulados.')
        durations, ends, elapsed = [], [], 0
        for i in range(count):
            check_time(); source.seek(i)
            duration = max(10, min(60000, int(source.info.get('duration', 100) or 100)))
            durations.append(duration); elapsed += duration; ends.append(elapsed)
        target_count = min(count, MAX_FRAMES)
        if target_count < count:
            # Muestrear por tiempo, no por índice: preserva la duración completa.
            selected = [min(bisect_right(ends, i * elapsed / target_count), count-1) for i in range(target_count)]
            output_durations = tuple(round((i+1)*elapsed/target_count)-round(i*elapsed/target_count) for i in range(target_count))
        else:
            selected = list(range(count)); output_durations = tuple(durations)
        frames = []
        for index in selected:
            check_time(); source.seek(index)
            rgba = ImageOps.exif_transpose(source).convert('RGBA')
            background = Image.new('RGBA', rgba.size, 'black'); background.alpha_composite(rgba)
            frames.append(ImageOps.fit(background.convert('RGB'), (480,480), method=Image.Resampling.LANCZOS).rotate(-rotation))
    # Probar calidad antes de reducir detalle espacial. Cada candidato tiene que
    # caber completo: nunca truncar una animación para satisfacer el límite.
    for resolution, quality in ((480,90),(480,80),(480,70),(320,80),(240,80),(160,70)):
        encoded, size = [], 9 + 4*len(frames)
        for frame in frames:
            check_time()
            candidate = frame if resolution == 480 else frame.resize((resolution,resolution), Image.Resampling.LANCZOS).resize((480,480), Image.Resampling.LANCZOS)
            buffer = BytesIO(); candidate.save(buffer, 'JPEG', quality=quality, subsampling=0)
            jpeg = buffer.getvalue(); size += len(jpeg)
            if size > MAX_MEMORY_BYTES:
                break
            encoded.append(jpeg)
        if len(encoded) == len(frames) and size <= MAX_MEMORY_BYTES:
            summary = (f'{count} → {len(frames)} cuadros · duración de origen {elapsed/1000:.2f} s · '
                       f'calidad JPEG {quality} · detalle {resolution}×{resolution} · preparado {size/1048576:.2f} MiB')
            asset = PreparedMemoryMedia(path.name, tuple(encoded), output_durations, rotation, summary)
            asset.prepare()
            return asset
    raise ValueError('No se pudo reducir el contenido a 12 MiB. Usa un GIF más corto o sencillo.')
