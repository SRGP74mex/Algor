#!/usr/bin/env python3
"""Prueba de memoria con muestras A/B/C. Por defecto solo valida, sin abrir USB."""
import argparse
import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from algor.core.lcd_memory import CapturedMemoryImage, save_captured_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', choices=['A', 'B', 'C'], default='A')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--check-stored', action='store_true', help='Consultar CRC actual sin enviar imagen ni órdenes de guardado.')
    actions.add_argument('--send', action='store_true', help='Reemplazar la imagen guardada con la muestra elegida, una sola vez.')
    args = parser.parse_args()
    source = ROOT / 'captures/20260908T225405_780878Z_memory/memory_analysis' / f'memory_{"ABC".index(args.image):02d}.jpg'
    asset = CapturedMemoryImage(args.image, source.read_bytes())
    reports, crc = asset.prepare()
    print(f'Muestra {args.image}: {len(asset.jpeg)} bytes JPEG, {len(reports)} reportes, CRC {crc.hex()}.', flush=True)
    if not args.send and not args.check_stored:
        print('Validación offline correcta. No se abrió el USB ni se escribió memoria.')
        return 0
    from algor.core.corsair_usb import CorsairNautilusDevice
    print('Consulta de CRC sin escritura de memoria.' if args.check_stored else 'Prueba experimental: sustituye la imagen de memoria.', flush=True)
    print('Algor e iCUE deben estar cerrados y el LCD libre en Linux.', flush=True)
    folder = ROOT / 'captures/linux_memory_tests' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    folder.mkdir(parents=True, mode=0o700)
    journal = folder / 'result.json'
    record = dict(operation='check_stored' if args.check_stored else 'save', diagnostics={}, image=args.image, crc32_le=crc.hex(), outcome='started', physical_persistence='pending')
    journal.write_text(json.dumps(record, indent=2)+'\n')
    device = CorsairNautilusDevice()
    result_code = 1
    try:
        device.connect()
        if args.check_stored:
            response = device.read_feature(0x0f)
            actual = response[1:5]
            record.update(outcome='stored_crc_matches' if actual == crc else 'stored_crc_differs',
                          actual_report=response.hex(), actual_crc32_le=actual.hex())
            print(f'CRC esperado: {crc.hex()} · CRC leído: {actual.hex()}', flush=True)
        else:
            record.update(save_captured_image(device, asset, lambda text: print(text, flush=True), record['diagnostics']))
        result_code = 0
    except (Exception, KeyboardInterrupt) as exc:
        record.update(outcome='unconfirmed', error=str(exc) or type(exc).__name__)
        print('Operación no confirmada; no se reintentó. ' + record['error'], flush=True)
    finally:
        device.disconnect()
        journal.write_text(json.dumps(record, indent=2)+'\n')
    print(f'Resultado: {record["outcome"]}. Registro: {journal}', flush=True)
    if result_code == 0:
        print('Comprueba qué imagen queda en el LCD después de terminar este proceso. CRC correcto no sustituye esa observación.')
    return result_code


if __name__ == '__main__':
    raise SystemExit(main())
