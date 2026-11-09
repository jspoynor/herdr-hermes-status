"""Explicit, per-user/per-machine companion setup for the native Hermes plugin."""
import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

VERSION = '2.0.0'
MARKER = '# Hermes Herdr terminal-side status adapter'
ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, content, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.herdr-writing-' + str(os.getpid()))
    try:
        with temporary.open('xb') as stream:
            stream.write(content)
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def wrapper(python, companion):
    return ('#!/bin/sh\n' + MARKER + '\nexec ' + shlex.quote(str(python)) + ' '
            + shlex.quote(str(companion)) + ' "$@"\n').encode()


def validate_runtime(runtime):
    spec = importlib.util.spec_from_file_location('herdr_launcher_validation', ROOT / 'companion/launcher.py')
    if spec is None or spec.loader is None:
        raise ValueError('launcher validation module is unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    command = module.build_command(Path(runtime).read_text(), ROOT / 'companion/bridge.py', [])
    compile(command[command.index('-c') + 1], '<Hermes launcher>', 'exec')
    if not os.access(command[0], os.X_OK):
        raise ValueError('Hermes runtime interpreter is not executable: ' + command[0])


def discover_runtime(launcher, home):
    result = subprocess.run([str(launcher), '--print-runtime-command'], capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        try:
            command = json.loads(result.stdout)
            tree = ast.parse(command[command.index('-c') + 1])
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and ast.unparse(node.func) == 'sys.path.insert' and len(node.args) == 2):
                    root = Path(ast.literal_eval(node.args[1]))
                    candidate = root / '.hermes/bin/hermes'
                    if candidate.is_file():
                        return candidate
        except (ValueError, TypeError, KeyError, IndexError, SyntaxError):
            pass
    candidate = home / '.hermes/hermes-agent/.hermes/bin/hermes'
    if candidate.is_file():
        return candidate
    raise ValueError('Cannot find the Hermes runtime launcher; supply --runtime-launcher PATH')


class AdapterManager:
    def __init__(self, source=ROOT, launcher=None, home=None, runtime_launcher=None, python=None):
        self.source = Path(source).expanduser().resolve()
        self.home = Path(home).expanduser().resolve() if home else Path.home()
        self.launcher = Path(launcher).expanduser().absolute() if launcher else self.home / '.local/bin/hermes'
        self.folder = self.home / '.local/share/hermes-herdr'
        self.runtime = Path(runtime_launcher).expanduser().resolve() if runtime_launcher else None
        self.python = str(python or ('/usr/bin/python3' if os.access('/usr/bin/python3', os.X_OK) else sys.executable))

    def state(self):
        path = self.folder / 'install-state.json'
        return json.loads(path.read_text()) if path.exists() else {}

    def status(self):
        state = self.state()
        current = self.launcher.read_bytes() if self.launcher.is_file() else b''
        installed = bool(state.get('installed') and digest(current) == state.get('wrapper_sha256'))
        return {'version': VERSION, 'installed': installed, 'machine': __import__('platform').node(),
                'launcher': str(self.launcher), 'companion': str(self.folder),
                'backup_exists': (self.folder / 'hermes.original').is_file(),
                'runtime_launcher': state.get('runtime_launcher'),
                'note': 'Setup is per machine/user. Existing sessions must be relaunched or resumed.'}

    def setup(self, dry_run=False):
        if os.name != 'posix':
            raise ValueError('This adapter supports macOS and Linux POSIX terminals only')
        if self.launcher.is_symlink():
            raise ValueError('Refusing to replace a symlink; supply --launcher with a user-owned regular entry point')
        if not self.launcher.is_file() or not os.access(self.launcher, os.X_OK):
            raise ValueError('Hermes launcher is missing or not executable: ' + str(self.launcher))
        current = self.launcher.read_bytes()
        mode = self.launcher.stat().st_mode & 0o777
        backup = self.folder / 'hermes.original'
        state = self.state()
        if state.get('backup_sha256') and backup.is_file() and digest(backup.read_bytes()) != state['backup_sha256']:
            raise ValueError('Backup changed since installation; refusing to rebaseline it')
        managed = digest(current) == state.get('wrapper_sha256')
        legacy = current == wrapper('/usr/bin/python3', self.folder / 'launcher.py')
        if managed or legacy:
            if not backup.is_file():
                raise ValueError('Managed launcher backup is missing; refusing to create a recursive backup')
        elif backup.exists() and current != backup.read_bytes():
            raise ValueError('Launcher changed since backup; inspect it before setup (no files changed)')
        runtime = (self.runtime or discover_runtime(backup if (managed or legacy) else self.launcher, self.home)).resolve()
        validate_runtime(runtime)
        payloads = {name: (self.source / 'companion' / name).read_bytes()
                    for name in ('bridge.py', 'launcher.py', 'verify_live.py')}
        generated = wrapper(self.python, self.folder / 'launcher.py')
        result = {'dry_run': dry_run, 'launcher': str(self.launcher), 'companion': str(self.folder),
                  'runtime_launcher': str(runtime), 'version': VERSION}
        if dry_run:
            return result
        if self.launcher.read_bytes() != current:
            raise ValueError('Launcher changed during setup; no launcher write was performed')
        if not backup.exists():
            atomic_write(backup, current, mode)
        for name, data in payloads.items():
            atomic_write(self.folder / name, data)
        state = {'installed': True, 'version': VERSION, 'launcher': str(self.launcher),
                 'runtime_launcher': str(runtime), 'wrapper_sha256': digest(generated),
                 'backup_sha256': digest(backup.read_bytes()),
                 'files': {name: digest(data) for name, data in payloads.items()}}
        atomic_write(self.folder / 'install-state.json', (json.dumps(state, indent=2) + '\n').encode())
        atomic_write(self.launcher, generated, mode)
        return result

    def uninstall(self):
        state = self.state()
        if not self.status()['installed']:
            raise ValueError('Launcher is not managed or was changed; refusing to overwrite it')
        backup = self.folder / 'hermes.original'
        if digest(backup.read_bytes()) != state.get('backup_sha256'):
            raise ValueError('Backup changed since installation; refusing to restore it')
        atomic_write(self.launcher, backup.read_bytes(), backup.stat().st_mode & 0o777)
        state['installed'] = False
        atomic_write(self.folder / 'install-state.json', (json.dumps(state, indent=2) + '\n').encode())
        return {'uninstalled': True, 'launcher': str(self.launcher), 'backup_retained': True}


def add_arguments(parser):
    parser.add_argument('action', choices=['setup', 'status', 'uninstall'])
    parser.add_argument('--dry-run', action='store_true', help='Validate setup without changing files')
    parser.add_argument('--launcher', type=Path, help='User-owned Hermes entry point (default ~/.local/bin/hermes)')
    parser.add_argument('--runtime-launcher', type=Path, help='Override detected Hermes runtime launcher')


def handle(args):
    try:
        manager = AdapterManager(launcher=args.launcher, runtime_launcher=args.runtime_launcher)
        if args.action == 'setup':
            result = manager.setup(dry_run=args.dry_run)
        elif args.action == 'uninstall':
            result = manager.uninstall()
        else:
            result = manager.status()
        print(json.dumps(result, indent=2))
        if args.action == 'setup' and not args.dry_run:
            print('Installed on THIS machine only. Repeat on each machine/user running Hermes.')
            print('Disable the old herdr-app-status plugin in affected profiles; relaunch/resume existing sessions.')
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('herdr-status: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_arguments(parser)
    handle(parser.parse_args())


if __name__ == '__main__':
    main()
