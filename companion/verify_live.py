"""Verify a real, already-started Hermes terminal through herdr-core."""
import json
from pathlib import Path
import subprocess
import sys

EXPECTED = 'Hermes bridge verified.'
REQUEST = ('Read-only integration test. Do not edit files or start agents. '
           'Run terminal command: printf "HERDR_REAL_BRIDGE_TEST\\n"; sleep 3. '
           'Then reply only with the phrase formed by joining these three words '
           'with single spaces and adding a final period: Hermes / bridge / verified')


def response_seen(output):
    # The expected response must not occur in the submitted request or its echo.
    assert EXPECTED not in REQUEST
    return EXPECTED in output


def main(address):
    core = str(Path.home() / '.local/bin/herdr-core')

    def command(*args):
        return subprocess.check_output([core, *args], text=True)

    def expect(state):
        terminal = json.loads(command('get', address))
        assert terminal['reported'] and terminal['status'] == {'app': 'hermes', 'state': state}, {
            key: terminal.get(key) for key in ('address', 'reported', 'status', 'turn')}
        print('PASS', address, state, 'turn', terminal['turn'], flush=True)
        return terminal

    print(command('wait', address, '--timeout', '45').strip(), flush=True)
    expect('idle')
    print(command('send', address, REQUEST).strip(), flush=True)
    expect('working')
    print(command('wait', address, '--timeout', '90').strip(), flush=True)
    terminal = expect('idle')
    assert terminal['turn'] >= 1
    output = command('read', address, '--lines', '20')
    assert response_seen(output), output
    print('PASS actual model response: ' + EXPECTED, flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
