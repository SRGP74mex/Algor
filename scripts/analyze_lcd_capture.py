#!/usr/bin/env python3
"""Analiza offline pcapng usbmon y reconstruye JPEG del Nautilus. No accede a USB."""
import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import struct
from PIL import Image


def packets(path, stats):
    endian = '<'
    interfaces = []
    with path.open('rb') as stream:
        while header := stream.read(8):
            if len(header) != 8:
                raise ValueError('Cabecera pcapng incompleta')
            if header[:4] == b'\x0a\x0d\x0d\x0a':
                magic = stream.read(4)
                if magic not in (b'\x4d\x3c\x2b\x1a', b'\x1a\x2b\x3c\x4d'):
                    raise ValueError('Byte-order magic inválido')
                endian = '<' if magic == b'\x4d\x3c\x2b\x1a' else '>'
                typ, size = struct.unpack(endian + 'II', header)
                prefix = magic
                interfaces = []
            else:
                typ, size = struct.unpack(endian + 'II', header)
                prefix = b''
            if size < 12 + len(prefix) or size % 4 or size > 16 * 1024 * 1024:
                raise ValueError('Longitud de bloque inválida')
            rest = stream.read(size - 8 - len(prefix))
            if len(rest) != size - 8 - len(prefix) or struct.unpack(endian + 'I', rest[-4:])[0] != size:
                raise ValueError('Bloque pcapng incompleto')
            body = prefix + rest[:-4]
            if typ == 1:
                linktype = struct.unpack_from(endian + 'H', body)[0]
                resolution = 1e-6
                for code, value in options(body[8:], endian):
                    if code == 9:
                        n = value[0]
                        resolution = 2 ** -(n & 127) if n & 128 else 10 ** -n
                interfaces.append((linktype, resolution))
            elif typ == 5:
                for code, value in options(body[12:], endian):
                    if code in (4, 5, 6, 7, 8) and len(value) == 8:
                        stats.setdefault('interface_statistics', {})[str(code)] = struct.unpack(endian + 'Q', value)[0]
            elif typ == 6:
                iface, hi, lo, caplen, original = struct.unpack_from(endian + 'IIIII', body)
                linktype, resolution = interfaces[iface]
                if linktype != 220:
                    raise ValueError('Solo se admite LINKTYPE_USB_LINUX_MMAPPED (220)')
                if len(body) < 20 + caplen or caplen < 64:
                    raise ValueError('Registro USB incompleto')
                stats['packets'] += 1
                stats['truncated_packets'] += caplen < original
                raw = body[20:20 + caplen]
                # La captura de este proyecto es Linux x86-64, cabecera USB little endian.
                uid, event, transfer, ep, device, bus = struct.unpack_from('<QBBBBH', raw)
                status, urb_len, data_len = struct.unpack_from('<iII', raw, 28)
                if data_len > len(raw) - 64:
                    stats['short_payloads'] += 1
                yield ((hi << 32 | lo) * resolution, uid, chr(event), transfer,
                       ep, device, bus, status, urb_len, raw[64:64 + data_len], raw[40:48])


def options(data, endian):
    offset = 0
    while offset + 4 <= len(data):
        code, size = struct.unpack_from(endian + 'HH', data, offset)
        offset += 4
        if code == 0:
            return
        if offset + size > len(data):
            raise ValueError('Opción pcapng incompleta')
        yield code, data[offset:offset + size]
        offset += (size + 3) & ~3


def analyze(source, output):
    output.mkdir(parents=True, exist_ok=False)
    stats = dict(packets=0, truncated_packets=0, short_payloads=0,
                 frame_errors=0, incomplete_frames=0, completion_errors=0)
    endpoints, addresses, headers = Counter(), Counter(), Counter()
    frames, controls, pending = [], [], {}
    current = None
    first_time = None
    last_saved = -100
    first_jpeg = last_jpeg = None
    first_dimensions = None
    for t, uid, event, transfer, ep, dev, bus, status, length, data, setup in packets(source, stats):
        if first_time is None:
            first_time = t
        relative = t - first_time
        endpoints[f'{event}/type={transfer}/ep=0x{ep:02x}'] += 1
        addresses[f'{bus}:{dev}'] += 1
        if event == 'S':
            pending[uid] = relative
        elif event in ('C', 'E'):
            if uid not in pending:
                stats['unmatched_completions'] = stats.get('unmatched_completions', 0) + 1
            pending.pop(uid, None)
            stats['completion_errors'] += status != 0
        if transfer == 2:
            controls.append(dict(time=relative, event=event, endpoint=ep, setup=setup.hex() if event == 'S' else None,
                                 data=data.hex(), status=status))
        if event != 'S' or ep != 9 or transfer != 1:
            continue
        if data[:2] != bytes.fromhex('0205'):
            # Otros reportes (por ejemplo 02 06 de memoria) no son JPEG en vivo
            # dañados. Se contabilizan aparte hasta analizarlos con su formato.
            stats['other_output_reports'] = stats.get('other_output_reports', 0) + 1
            continue
        if len(data) != 1024:
            stats['frame_errors'] += 1
            continue
        final, index, used = struct.unpack_from('<BHH', data, 3)
        headers[data[:4].hex()] += 1
        if index == 0:
            if current is not None:
                stats['incomplete_frames'] += 1
            current = dict(start=relative, next=0, data=bytearray(), header_byte_2=data[2])
        if current is None:
            continue
        if index != current['next'] or used > 1016 or final not in (0, 1):
            stats['frame_errors'] += 1
            current = None
            continue
        current['next'] += 1
        current['data'].extend(data[8:8 + used])
        if not final:
            continue
        jpeg = bytes(current['data'])
        try:
            if not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                raise ValueError('JPEG sin delimitadores')
            with Image.open(BytesIO(jpeg)) as img:
                img.load()
                dimensions = list(img.size)
                if img.format != 'JPEG':
                    raise ValueError('Formato inesperado')
        except (OSError, ValueError):
            stats['frame_errors'] += 1
            current = None
            continue
        record = dict(number=len(frames), start=current['start'], end=relative,
                      chunks=current['next'], bytes=len(jpeg), dimensions=dimensions,
                      sha256=hashlib.sha256(jpeg).hexdigest(),
                      header_byte_2=current['header_byte_2'])
        if current['start'] - last_saved >= 5:
            name = f"frame_{len(frames):04d}.jpg"
            (output / name).write_bytes(jpeg)
            record['example'] = name
            last_saved = current['start']
        frames.append(record)
        if first_jpeg is None:
            first_jpeg, first_dimensions = jpeg, dimensions
        last_jpeg = jpeg
        current = None
    if current is not None:
        stats['incomplete_frames'] += 1
    stats['pending_submissions_at_end'] = len(pending)
    stats['duration'] = relative if first_time is not None else 0
    stats['frames'] = len(frames)
    stats['unique_jpeg_hashes'] = len({f['sha256'] for f in frames})
    stats['addresses'] = dict(addresses)
    stats['endpoints'] = dict(endpoints)
    stats['image_headers'] = dict(headers)
    if last_jpeg:
        (output / 'last_frame.jpg').write_bytes(last_jpeg)
    report = dict(source=str(source), stats=stats, frames=frames, control_transfers=controls)
    (output / 'analysis.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(stats, indent=2))
    print('Informe y ejemplos:', output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    analyze(args.capture, args.output)
