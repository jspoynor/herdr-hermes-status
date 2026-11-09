"""Launch the installed Hermes with a terminal-side adapter inside Herdr only."""
import json
import os
from pathlib import Path
import shlex
import sys


def build_command(text, bridge, arguments):
    tokens = shlex.split('\n'.join(text.splitlines()[1:]))
    if tokens[0] != 'exec' or tokens[-1] != '$@':
        raise ValueError('unrecognized Hermes launcher envelope')
    command = tokens[1:-1]
    index = command.index('-c') + 1
    marker = 'from hermes_cli.main import main'
    if command[index].count(marker) != 1:
        raise ValueError('unrecognized Hermes Python entry point')
    injection = 'import runpy; runpy.run_path(' + repr(str(bridge)) + ')["install"](); '
    command[index] = command[index].replace(marker, injection + marker)
    return command + list(arguments)


def main():
    folder = Path(__file__).resolve().parent
    original = folder / 'hermes.original'
    if not os.environ.get('HC_TERMINAL_ID') or '--print-runtime-command' in sys.argv[1:]:
        os.execv(str(original), [str(original), *sys.argv[1:]])
    try:
        state = json.loads((folder / 'install-state.json').read_text())
        inner = Path(state['runtime_launcher'])
        command = build_command(inner.read_text(), folder / 'bridge.py', sys.argv[1:])
    except (OSError, ValueError, IndexError, KeyError, TypeError) as exc:
        print('hermes-herdr: status adapter unavailable: ' + str(exc), file=sys.stderr)
        os.execv(str(original), [str(original), *sys.argv[1:]])
    os.execv(command[0], command)


if __name__ == '__main__':
    main()
