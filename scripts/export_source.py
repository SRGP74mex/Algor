#!/usr/bin/env python3
"""Build a reviewable source folder from an explicit allowlist, without publishing."""
import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {'.gitignore', 'README.md', 'LICENSE', 'requirements.txt', 'requirements-tested.txt',
              'main.py', 'setup_udev.sh', 'setup_udev_pwm.sh', 'CONTRIBUTING.md', 'THIRD_PARTY_NOTICES.md'}
# Extensiones de catálogo de idioma: .pot (plantilla), .po (traducción editable),
# .mo (compilado, lo que gettext realmente lee en runtime) — las tres se
# publican; sin el .mo, la app funcionaría pero mostraría siempre español
# aunque exista un .po sin compilar.
LOCALE_EXTENSIONS = {'.pot', '.po', '.mo'}
DOCS = {'ROADMAP.md', 'ASISTENTE_VENTILADORES.md', 'PRUEBA_ARRANQUE_Y_ALERTAS.md',
        'COMPATIBILITY.md', 'MEDIA.md', 'RELEASE_CHECKLIST.md', 'LICENSING.md',
        'PROTOCOLO_LCD_CAP_OBSERVADO.md', 'PWM_REAL_CONTROL.md'}
SCRIPTS = {'install_desktop.py', 'run_tests.py', 'smoke_test.py', 'export_source.py',
           'diagnostics.py', 'test_lcd_static.py', 'analyze_lcd_capture.py', 'analyze_lcd_memory.py', 'compare_lcd_memory.py',
           'i18n_extract.sh', 'i18n_compile.sh'}


def publishable(path):
    parts = path.parts
    if any(part.startswith('__') and part == '__pycache__' for part in parts):
        return False
    if len(parts) == 1:
        return path.name in ROOT_FILES
    if parts[0] == 'algor':
        return (path.suffix == '.py' or path.suffix in LOCALE_EXTENSIONS
                or str(path) in ('algor/assets/icons/Algor.svg', 'algor/assets/icons/README.md'))
    if parts[0] == 'tests':
        return path.suffix == '.py'
    if parts[0] == '.github':
        return path.suffix in ('.yml', '.yaml', '.md')
    if parts[0] == 'docs':
        return path.name in DOCS and len(parts) == 2
    if parts[0] == 'scripts':
        return path.name in SCRIPTS and len(parts) == 2
    return False


def export(destination):
    destination = Path(destination).resolve()
    if destination == ROOT or ROOT in destination.parents and 'local' not in destination.relative_to(ROOT).parts:
        raise ValueError('Choose a new destination outside the project or under local/.')
    if destination.exists():
        raise ValueError('Destination already exists; choose a new empty path.')
    candidates = [p for p in ROOT.rglob('*') if not p.is_symlink() and p.is_file() and publishable(p.relative_to(ROOT))]
    destination.mkdir(parents=True)
    for source in candidates:
        target = destination / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return len(candidates), sum(p.stat().st_size for p in candidates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    count, size = export(args.destination)
    print(f'{count} files, {size / 1024 / 1024:.2f} MiB: {args.destination}')


if __name__ == '__main__':
    main()
