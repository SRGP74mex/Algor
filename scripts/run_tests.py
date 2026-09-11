#!/usr/bin/env python3
"""Run the test suite with an isolated home; never touch user preferences."""
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    with tempfile.TemporaryDirectory(prefix='algor-tests-') as folder:
        environment = {key: str(Path(folder) / value) for key, value in {
            'XDG_CONFIG_HOME': 'config', 'XDG_DATA_HOME': 'data', 'XDG_STATE_HOME': 'state',
            'XDG_CACHE_HOME': 'cache'}.items()}
        # Pin locale env vars so tests assert on the Spanish source strings
        # regardless of the host/CI locale (gettext reads these directly).
        environment.update({'LANGUAGE': '', 'LC_ALL': 'C', 'LC_MESSAGES': 'C', 'LANG': 'C'})
        with patch.object(Path, 'home', return_value=Path(folder)), patch.dict(os.environ, environment):
            suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
            return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
