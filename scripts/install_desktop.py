#!/usr/bin/env python3
"""Install a per-user launcher using this interpreter. No USB permissions changed."""
import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def desktop_quote(value):
    value = str(value).replace('%', '%%')
    for char in ('\\', '"', '`', '$'):
        value = value.replace(char, '\\' + char)
    return '"' + value.replace('\\', '\\\\') + '"'


def install(home=None):
    home = Path(home) if home else Path.home()
    launcher = home / '.local/bin/algor'
    desktop = home / '.local/share/applications/algor.desktop'
    icon = home / '.local/share/icons/hicolor/scalable/apps/algor.svg'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' +
                        shlex.quote(str(ROOT / 'main.py')) + ' "$@"\n', encoding='utf-8')
    launcher.chmod(0o755)
    source = ROOT / 'algor/assets/icons/Algor.svg'
    icon_name = 'applications-system'
    if source.is_file():
        icon.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, icon)
        icon_name = 'algor'
    desktop.write_text('[Desktop Entry]\nType=Application\nName=Algor\n'
                       'Comment=Linux telemetry and Nautilus LCD Cap\n'
                       f'Exec={desktop_quote(launcher)}\nIcon={icon_name}\n'
                       'Terminal=false\nCategories=System;Monitor;Qt;\n'
                       'StartupWMClass=algor\nStartupNotify=true\n', encoding='utf-8')
    return launcher, desktop


def uninstall(home=None):
    home = Path(home) if home else Path.home()
    for relative in ('.local/bin/algor',
                     '.local/share/applications/algor.desktop',
                     '.local/share/icons/hicolor/scalable/apps/algor.svg',
                     '.config/autostart/algor.desktop'):
        (home / relative).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    if args.uninstall:
        uninstall()
        print('Accesos directos retirados; preferencias, medios y regla USB conservados.')
    else:
        launcher, desktop = install()
        print(f'Instalado: {desktop}\nIntérprete: {sys.executable}\nConserva la carpeta del proyecto y su entorno virtual.')
    if shutil.which('update-desktop-database'):
        subprocess.run(['update-desktop-database', str(Path.home() / '.local/share/applications')], check=False)


if __name__ == '__main__':
    main()
