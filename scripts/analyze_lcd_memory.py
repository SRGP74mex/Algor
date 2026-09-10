#!/usr/bin/env python3
"""Reconstrucción OFFLINE del formato de memoria 02 06 observado; no escribe USB."""
import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct
import zlib
from PIL import Image
from analyze_lcd_capture import packets


def extract(source, destination):
    destination.mkdir(parents=True, exist_ok=False)
    statistics = dict(packets=0, truncated_packets=0, short_payloads=0)
    current = None
    uploads = []
    first_time = None
    controls = []
    for timestamp, uid, event, transfer, ep, dev, bus, status, size, data, setup in packets(source, statistics):
        if first_time is None:
            first_time = timestamp
        if event == 'S' and transfer == 2 and setup[:6] == bytes.fromhex('210903030000') and data[:2] == b'\x03\x1c':
            controls.append(dict(time=timestamp-first_time, crc32_le=data[2:6].hex()))
        if event != 'S' or ep != 9 or transfer != 1 or data[:2] != b'\x02\x06':
            continue
        if len(data) != 1024:
            raise ValueError('Reporte de memoria incompleto')
        total = struct.unpack_from('<I', data, 2)[0]
        if not 13 < total <= 64 * 1024 * 1024:
            raise ValueError('Longitud de carga fuera del límite offline')
        if data[6:8] == b'\0\0':
            if current is not None:
                raise ValueError('Nueva carga antes de completar la anterior')
            current = dict(start=timestamp-first_time, size=total, next=0, page=1, reports=0, content=bytearray(),
                           header=data[:32].hex())
            continue
        if current is None:
            raise ValueError('Fragmento de memoria sin inicio reconocido')
        page = struct.unpack_from('<H', data, 6)[0]
        if page != current['page']:
            raise ValueError('Página de memoria fuera de secuencia')
        length, index = struct.unpack_from('<HH', data, 12)
        final = data[10]
        if total != current['size'] or index != current['next'] or length > 1008 or final not in (0, 1) or data[11] not in (0, 1):
            raise ValueError('Secuencia o longitud de memoria inválida')
        current['content'].extend(data[16:16+length])
        current['next'] += 1
        current['reports'] += 1
        if len(current['content']) > total:
            raise ValueError('Más bytes que la longitud anunciada')
        if not final:
            continue
        if not data[11]:
            current['page'] += 1
            current['next'] = 0
            continue
        content = bytes(current['content'])
        if len(content) != total:
            raise ValueError('Carga incompleta')
        if len(content) < 13 or content[0] != 1:
            raise ValueError('Cabecera de contenido desconocida')
        width, height, count, candidate_interval = struct.unpack_from('<HHHH', content, 1)
        if (width, height) != (480, 480) or not 1 <= count <= 4096:
            raise ValueError('Dimensiones o cantidad de cuadros fuera del formato observado')
        offset = 9 + 4 * count
        if len(content) < offset:
            raise ValueError('Tabla de longitudes incompleta')
        lengths = struct.unpack_from('<' + 'I' * count, content, 9)
        if any(n < 4 for n in lengths) or offset + sum(lengths) != len(content):
            raise ValueError('Las longitudes de cuadros no coinciden con el contenedor')
        jpeg_payload = content[offset:]
        frames = []
        for index, length in enumerate(lengths):
            jpeg = content[offset:offset + length]
            offset += length
            if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                raise ValueError('Cuadro JPEG incompleto')
            with Image.open(BytesIO(jpeg)) as image:
                image.load()
                if image.format != 'JPEG' or image.size != (width, height):
                    raise ValueError('Las dimensiones no coinciden')
            name = (f'memory_{len(uploads):02d}.jpg' if count == 1 else
                    f'memory_{len(uploads):02d}_frame_{index:03d}.jpg')
            (destination/name).write_bytes(jpeg)
            frames.append(dict(image=name, image_bytes=length,
                               image_sha256=hashlib.sha256(jpeg).hexdigest()))
        upload = dict(start=current['start'], end=timestamp-first_time,
                      data_reports=current['reports'], pages=current['page'], total_bytes=total,
                      image_bytes=len(jpeg_payload), dimensions=[width, height],
                      image_sha256=hashlib.sha256(jpeg_payload).hexdigest(),
                      jpeg_crc32_le=struct.pack('<I', zlib.crc32(jpeg_payload)).hex(),
                      frame_count=count, candidate_interval=candidate_interval,
                      frames=frames, envelope_hex=content[:9 + 4 * count].hex(),
                      start_header_hex=current['header'])
        if count == 1:
            upload['image'] = frames[0]['image']
        uploads.append(upload)
        current = None
    if current is not None:
        raise ValueError('Última carga de memoria incompleta')
    for i, upload in enumerate(uploads):
        next_start = uploads[i + 1]['start'] if i + 1 < len(uploads) else float('inf')
        following = [c for c in controls if upload['end'] <= c['time'] < next_start]
        upload['finalizers'] = following
        upload['crc32_matches_finalizer'] = (len(following) == 1 and following[0]['crc32_le'] == upload['jpeg_crc32_le'])
    report = dict(source=str(source), uploads=uploads, statistics=statistics,
                  persistence='Not proven by transfer; requires physical observation after software exit.')
    (destination/'memory_analysis.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    extract(args.capture, args.output)
