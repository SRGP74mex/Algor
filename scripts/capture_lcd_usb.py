#!/usr/bin/env python3
"""Captura pasiva del LCD 1b1c:0c57 mediante usbmon y dumpcap en Linux."""
import argparse
import datetime
import json
from pathlib import Path
import shutil
import subprocess
import sys


def find_lcd(root=Path('/sys/bus/usb/devices')):
    devices = []
    for path in root.iterdir():
        try:
            if ((path / 'idVendor').read_text().strip(),
                    (path / 'idProduct').read_text().strip()) != ('1b1c', '0c57'):
                continue
            devices.append({
                'path': path.name,
                'bus': int((path / 'busnum').read_text()),
                'address': int((path / 'devnum').read_text()),
                'product': (path / 'product').read_text().strip(),
            })
        except (OSError, ValueError):
            continue
    if len(devices) != 1:
        raise RuntimeError(f'Se esperaba un LCD 1b1c:0c57; se encontraron {len(devices)}.')
    return devices[0]


def find_dumpcap():
    # Debian puede restringir ejecución al grupo wireshark. which() lo omite
    # para otros usuarios, aunque sudo sí puede ejecutarlo. No ampliar permisos.
    for candidate in (Path('/usr/bin/dumpcap'), Path('/usr/sbin/dumpcap')):
        if candidate.is_file():
            return str(candidate)
    return shutil.which('dumpcap')


def capture_command(dumpcap, device, duration):
    # pcap/usb.h: device_address está en el byte 11 de USB_LINUX_MMAPPED.
    # Elegimos un solo bus y filtramos ANTES de guardar, no al visualizar.
    return [dumpcap, '-i', f"usbmon{device['bus']}", '-y', 'USB_LINUX_MMAPPED',
            '-f', f"link[11] == {device['address']}", '-s', '1048576',
            '-B', '16', '-a', f'duration:{duration}', '-a', 'filesize:102400',
            '-w', '-']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', choices=['baseline', 'startup', 'image', 'rotation', 'brightness', 'memory', 'memory_gif'], required=True)
    parser.add_argument('--duration', type=int, default=30)
    parser.add_argument('--check', action='store_true', help='Solo detectar el LCD y las herramientas; no usa sudo.')
    args = parser.parse_args()
    if not 5 <= args.duration <= 120:
        parser.error('La duración debe estar entre 5 y 120 segundos.')
    device = find_lcd()
    dumpcap = find_dumpcap()
    print(json.dumps(device, ensure_ascii=False, indent=2), flush=True)
    if not dumpcap:
        raise RuntimeError('Falta dumpcap. En Debian: sudo apt install wireshark-common tshark')
    command = capture_command(dumpcap, device, args.duration)
    if args.check:
        print('Comando previsto:', command)
        return

    print('Cierra Algor (bandeja → Salir). Conecta el LCD a Windows en VMware.')
    if args.label == 'startup':
        print('Mantén iCUE cerrado, incluida su bandeja, hasta que aparezca Capturing on.')
    else:
        print('Abre iCUE y deja el LCD listo antes de continuar.')
    print('Mantén esa conexión durante la captura. No conectes/desconectes dispositivos del bus.')
    input('Cuando hayas completado la preparación indicada, pulsa Enter: ')
    # Autenticación en el terminal local; nunca se recibe ni guarda la contraseña.
    subprocess.run(['sudo', '-v'], check=True)
    subprocess.run(['sudo', '-n', 'modprobe', 'usbmon'], check=True)
    # VMware puede haber cambiado la dirección desde la detección inicial.
    device = find_lcd()
    command = capture_command(dumpcap, device, args.duration)
    subprocess.run(['sudo', '-n', dumpcap, '-i', f"usbmon{device['bus']}",
                    '-y', 'USB_LINUX_MMAPPED', '-f', f"link[11] == {device['address']}",
                    '-d'], check=True, stdout=subprocess.DEVNULL)

    output_root = Path(__file__).resolve().parents[1] / 'captures'
    output_root.mkdir(exist_ok=True, mode=0o700)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    directory = output_root / f'{stamp}_{args.label}'
    directory.mkdir(mode=0o700)
    capture = directory / 'lcd.pcapng'
    instructions = {
        'memory_gif': 'Con Device Memory Mode ON: importa probe_200_800.gif, pulsa Guardar UNA vez y espera a que termine. No cambies brillo ni orientación. No cierres iCUE durante la captura.',
        'memory': 'Con Device Memory Mode ON: selecciona UNA imagen estática distinta, pulsa Guardar una vez y espera a que termine. No cambies brillo ni orientación; no cierres iCUE durante la captura.',
        'baseline': 'No cambies nada en iCUE.',
        'startup': 'Abre iCUE y espera sin cambiar imagen, brillo ni rotación.',
        'image': 'Selecciona UNA imagen estática distinta y confirma el cambio en el LCD físico.',
        'rotation': 'Rota UNA vez 90° y confirma el cambio en el LCD físico.',
        'brightness': 'Cambia UNA vez el brillo (por ejemplo de 80% a 40%).',
    }
    metadata = dict(device=device, label=args.label, duration=args.duration,
                    started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    command=command, snaplen=1048576)
    print(f'\nSe inicia una captura de hasta {args.duration} segundos / 100 MB.', flush=True)
    print('Espera a que dumpcap muestre "Capturing on" antes de actuar.', flush=True)
    print('ACCIÓN: ' + instructions[args.label], flush=True)
    # El usuario crea el archivo; dumpcap privilegiado solo escribe a stdout.
    with capture.open('xb') as stream:
        result = subprocess.run(['sudo', '-n', *command], stdout=stream)
    metadata['returncode'] = result.returncode
    metadata['bytes'] = capture.stat().st_size
    try:
        metadata['device_after'] = find_lcd()
        metadata['same_address'] = metadata['device_after'] == device
    except RuntimeError:
        metadata['same_address'] = False
    # Persistir primero el resultado técnico: esperar la descripción física no
    # debe dejar una captura sin metadatos si se cierra el terminal.
    metadata['physical_result'] = None
    metadata_path = directory / 'metadata.json'
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    try:
        metadata['physical_result'] = input('\n¿Qué cambió en el LCD físico? (o escribe "sin cambio"): ')
    except (EOFError, KeyboardInterrupt):
        print('\nDescripción visual pendiente; los datos técnicos ya están guardados.')
    else:
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print('Archivo:', capture)
    if result.returncode or not metadata['same_address']:
        raise RuntimeError('Captura incompleta o dispositivo cambiado. Revisar antes de interpretar.')
    print('Captura terminada; falta verificar paquetes, pérdidas y posible truncamiento con tshark.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\nCaptura interrumpida; cualquier archivo generado es parcial.', file=sys.stderr)
        sys.exit(130)
