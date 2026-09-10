#!/usr/bin/env python3
"""Print a limited read-only diagnostic. No USB claims, serials, hostname or user config."""
import importlib.metadata
import json
from pathlib import Path
import platform


def text_file(path):
    try:
        return path.read_text(encoding='utf-8').strip()[:200]
    except (OSError, UnicodeError):
        return None


def collect(sys_root=Path('/sys'), os_release=Path('/etc/os-release')):
    distro = {}
    raw = text_file(os_release) or ''
    for line in raw.splitlines():
        key, _, value = line.partition('=')
        if key in ('ID', 'VERSION_ID', 'PRETTY_NAME'):
            distro[key] = value.strip('"')
    versions = {}
    for package in ('PyQt6', 'PyQt6-Qt6', 'Pillow', 'psutil', 'pyusb'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    chips = []
    for base in sorted((sys_root / 'class/hwmon').glob('hwmon*')):
        chips.append({'chip': text_file(base / 'name'),
                      'rpm_channels': sorted(p.name for p in base.glob('fan*_input')),
                      'temperature_channels': sorted(p.name for p in base.glob('temp*_input'))})
    usb = []
    for base in (sys_root / 'bus/usb/devices').glob('*'):
        vid, pid = text_file(base / 'idVendor'), text_file(base / 'idProduct')
        if vid == '1b1c' and pid:
            usb.append({'vid': vid, 'pid': pid})
    return {'schema': 1, 'distribution': distro, 'kernel': platform.release(),
            'architecture': platform.machine(), 'python': platform.python_version(),
            'board': {field: text_file(sys_root / 'class/dmi/id' / field)
                      for field in ('board_vendor', 'board_name')},
            'dependencies': versions, 'corsair_usb': usb, 'hwmon': chips,
            'notice': 'Review before sharing. No configuration, media, serials or raw USB traffic included.'}


if __name__ == '__main__':
    print(json.dumps(collect(), indent=2, ensure_ascii=False))
