import json
from pathlib import Path
import shlex
import tempfile
import unittest
from unittest.mock import patch
from scripts import diagnostics, export_source, install_desktop


class ReleaseToolsTests(unittest.TestCase):
    def test_launcher_preserves_interpreter_and_paths_and_uninstall_keeps_data(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder) / 'user space'
            source = Path(folder) / 'project $literal `literal`'
            source.mkdir()
            interpreter = '/tmp/virtual env/bin/python'
            with patch.object(install_desktop, 'ROOT', source), patch.object(install_desktop.sys, 'executable', interpreter):
                launcher, desktop = install_desktop.install(home)
            command = launcher.read_text().splitlines()[1]
            self.assertEqual(shlex.split(command)[1:3], [interpreter, str(source / 'main.py')])
            self.assertIn('Exec="', desktop.read_text())
            data = home / '.config/algor/config.json'
            data.parent.mkdir(parents=True)
            data.write_text('{}')
            install_desktop.uninstall(home)
            self.assertTrue(data.exists())
            self.assertFalse(launcher.exists())
            self.assertFalse(desktop.exists())

    def test_diagnostics_allowlist_excludes_serial_hostname_and_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dmi = root / 'class/dmi/id'
            dmi.mkdir(parents=True)
            (dmi / 'board_name').write_text('Test board')
            (dmi / 'board_serial').write_text('PRIVATE-SERIAL')
            hwmon = root / 'class/hwmon/hwmon3'
            hwmon.mkdir(parents=True)
            (hwmon / 'name').write_text('it8792')
            (hwmon / 'fan1_input').write_text('2200')
            (hwmon / 'fan1_label').write_text('PRIVATE-LABEL')
            usb = root / 'bus/usb/devices/1-2'
            usb.mkdir(parents=True)
            (usb / 'idVendor').write_text('1b1c')
            (usb / 'idProduct').write_text('0c57')
            (usb / 'serial').write_text('PRIVATE-SERIAL')
            release = root / 'os-release'
            release.write_text('ID=debian\nVERSION_ID="13"\nHOSTNAME=PRIVATE-HOST\n')
            result = diagnostics.collect(root, release)
            serialized = json.dumps(result)
            self.assertNotIn('PRIVATE', serialized)
            self.assertNotIn(folder, serialized)
            self.assertEqual(result['corsair_usb'], [{'vid':'1b1c','pid':'0c57'}])
            self.assertEqual(result['hwmon'][0]['rpm_channels'], ['fan1_input'])

    def test_public_export_excludes_media_captures_secrets_and_symlinks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / 'source'
            root.mkdir()
            for name in ('main.py', 'README.md', 'local/media/Tux.GIF', 'captures/lcd.pcapng',
                         '.env', 'algor/assets/memory/A.jpg', 'algor/core/config.py',
                         'algor/__pycache__/private.py', 'tests/test_sample.py'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('test')
            (root / 'scripts').mkdir()
            (root / 'scripts/diagnostics.py').symlink_to(root / '.env')
            destination = Path(folder) / 'public'
            with patch.object(export_source, 'ROOT', root):
                export_source.export(destination)
                with self.assertRaises(ValueError):
                    export_source.export(destination)
            names = {str(p.relative_to(destination)) for p in destination.rglob('*') if p.is_file()}
            self.assertEqual(names, {'main.py','README.md','algor/core/config.py','tests/test_sample.py'})
