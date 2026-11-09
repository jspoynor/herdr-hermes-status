import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_management():
    spec = importlib.util.spec_from_file_location('management_test', ROOT / 'management.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InstallationTests(unittest.TestCase):
    def test_install_repeat_status_and_uninstall_preserve_original(self):
        module = load_management()
        with tempfile.TemporaryDirectory(prefix='herdr plugin ') as tmp:
            home = Path(tmp)
            launcher = home / 'bin/hermes'
            launcher.parent.mkdir()
            original = b'#!/bin/sh\nprintf original\\n\n'
            launcher.write_bytes(original)
            launcher.chmod(0o755)
            runtime = home / 'runtime launcher'
            runtime.write_text('#!/bin/sh\nexec /usr/bin/python3 -I -c \'from hermes_cli.main import main; main()\' "$@"\n')
            manager = module.AdapterManager(ROOT, launcher, home, runtime, '/usr/bin/python3')
            self.assertFalse(manager.status()['installed'])
            manager.setup(dry_run=True)
            self.assertEqual(launcher.read_bytes(), original)
            self.assertFalse(manager.folder.exists())
            manager.setup()
            self.assertTrue(manager.status()['installed'])
            self.assertEqual((manager.folder / 'hermes.original').read_bytes(), original)
            first = launcher.read_bytes()
            manager.setup()
            self.assertEqual(launcher.read_bytes(), first)
            manager.uninstall()
            self.assertEqual(launcher.read_bytes(), original)
            self.assertEqual(launcher.stat().st_mode & 0o777, 0o755)
            self.assertFalse(manager.status()['installed'])


    def test_modified_launcher_is_never_overwritten(self):
        module = load_management()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            launcher = home / 'hermes'
            launcher.write_text('#!/bin/sh\nexit 0\n')
            launcher.chmod(0o755)
            runtime = home / 'runtime'
            runtime.write_text('#!/bin/sh\nexec /usr/bin/python3 -I -c \'from hermes_cli.main import main; main()\' "$@"\n')
            manager = module.AdapterManager(ROOT, launcher, home, runtime)
            manager.setup()
            custom = b'#!/bin/sh\n# user changed this\nexit 0\n'
            launcher.write_bytes(custom)
            with self.assertRaisesRegex(ValueError, 'changed'):
                manager.setup()
            with self.assertRaisesRegex(ValueError, 'changed'):
                manager.uninstall()
            self.assertEqual(launcher.read_bytes(), custom)


    def test_setup_rejects_changed_backup_without_rebaselining_it(self):
        module = load_management()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            launcher = home / 'hermes'
            launcher.write_text('#!/bin/sh\nexit 0\n')
            launcher.chmod(0o755)
            runtime = home / 'runtime'
            runtime.write_text('#!/bin/sh\nexec /usr/bin/python3 -I -c \'from hermes_cli.main import main; main()\' "$@"\n')
            manager = module.AdapterManager(ROOT, launcher, home, runtime)
            manager.setup()
            state_before = (manager.folder / 'install-state.json').read_bytes()
            wrapper_before = launcher.read_bytes()
            (manager.folder / 'hermes.original').write_text('corrupted backup')
            with self.assertRaisesRegex(ValueError, 'Backup changed'):
                manager.setup()
            self.assertEqual((manager.folder / 'install-state.json').read_bytes(), state_before)
            self.assertEqual(launcher.read_bytes(), wrapper_before)


    def test_relative_runtime_override_is_persisted_as_absolute(self):
        import os
        module = load_management()
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            launcher = home / 'hermes'
            launcher.write_text('#!/bin/sh\nexit 0\n')
            launcher.chmod(0o755)
            runtime = home / 'runtime'
            runtime.write_text('#!/bin/sh\nexec /usr/bin/python3 -I -c \'from hermes_cli.main import main; main()\' "$@"\n')
            previous = Path.cwd()
            try:
                os.chdir(home)
                manager = module.AdapterManager(ROOT, launcher, home, Path('runtime'))
                manager.setup()
            finally:
                os.chdir(previous)
            self.assertEqual(Path(manager.state()['runtime_launcher']), runtime.resolve())


if __name__ == '__main__':
    unittest.main()
