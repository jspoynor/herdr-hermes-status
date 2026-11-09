import importlib.util
from pathlib import Path
import unittest


def load_bridge():
    spec = importlib.util.spec_from_file_location('bridge_under_test', (Path(__file__).resolve().parents[1] / 'companion').joinpath('bridge.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BridgeTests(unittest.TestCase):
    def test_real_client_boundaries_report_idle_working_idle(self):
        bridge = load_bridge()
        reports = []
        class Client:
            def __init__(self):
                self._agent_running = False
            def chat(self, message):
                # Hermes clears this viewer flag outside chat(), after the return.
                self._agent_running = True
                self._invalidate()
                return message.upper()
            def _invalidate(self, *args, **kwargs):
                return 'redrawn'
        bridge.patch_client(Client, reports.append)
        client = Client()
        self.assertEqual(reports, ['idle'])
        self.assertEqual(client.chat('hello'), 'HELLO')
        self.assertEqual(reports, ['idle', 'working', 'idle'])
        self.assertEqual(client._invalidate(), 'redrawn')
        self.assertEqual(reports, ['idle', 'working', 'idle'])


    def test_modal_wait_is_blocked_and_returns_to_working(self):
        bridge = load_bridge()
        reports = []
        class Client:
            def __init__(self):
                self._agent_running = False
            def _invalidate(self):
                pass
            def _paint_now(self):
                return 'painted'
            def chat(self, message):
                self._clarify_state = {'question': 'needs input'}
                self._paint_now()
                self._clarify_state = None
                self._paint_now()
        bridge.patch_client(Client, reports.append)
        Client().chat('test')
        self.assertEqual(reports, ['idle', 'working', 'blocked', 'working', 'idle'])


    def test_exception_restores_idle_and_install_is_idempotent(self):
        bridge = load_bridge()
        reports = []
        class Client:
            def __init__(self):
                pass
            def _invalidate(self):
                pass
            def chat(self, message):
                raise RuntimeError('test interruption')
        bridge.patch_client(Client, reports.append)
        bridge.patch_client(Client, reports.append)
        client = Client()
        with self.assertRaisesRegex(RuntimeError, 'test interruption'):
            client.chat('test')
        self.assertEqual(reports, ['idle', 'working', 'idle'])


class VerifierTests(unittest.TestCase):
    def test_echoed_request_does_not_count_as_model_reply(self):
        import runpy
        verifier = runpy.run_path(str((Path(__file__).resolve().parents[1] / 'companion').joinpath('verify_live.py')))
        request = verifier['REQUEST']
        self.assertNotIn(verifier['EXPECTED'], request)
        self.assertFalse(verifier['response_seen'](request))
        self.assertTrue(verifier['response_seen'](request + '\n' + verifier['EXPECTED']))


class LauncherTests(unittest.TestCase):
    def test_preserves_runtime_bootstrap_and_arguments(self):
        import runpy
        launcher = runpy.run_path(str((Path(__file__).resolve().parents[1] / 'companion').joinpath('launcher.py')))
        inner = '#!/bin/sh\nexec /runtime/python -I -c \'import bootstrap; from hermes_cli.main import main; main()\' "$@"\n'
        command = launcher['build_command'](inner, '/adapter/bridge.py', ['-p', 'code', 'chat'])
        self.assertEqual(command[:3], ['/runtime/python', '-I', '-c'])
        self.assertEqual(command[4:], ['-p', 'code', 'chat'])
        self.assertIn('import bootstrap;', command[3])
        self.assertIn('run_path', command[3])
        self.assertLess(command[3].index('run_path'), command[3].index('from hermes_cli.main'))


if __name__ == '__main__':
    unittest.main()
