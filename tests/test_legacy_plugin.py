"""Regression coverage for the retained hook-based plugin."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch


def load_plugin():
    path = (Path(__file__).resolve().parents[1] / 'hermes-plugin' /
            'herdr-app-status' / '__init__.py')
    spec = importlib.util.spec_from_file_location('legacy_under_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LegacyPluginTests(unittest.TestCase):
    def setUp(self):
        self.plugin = load_plugin()
        self.reports = []
        self.plugin._write = lambda *args: self.reports.append(args)
        self.timer = patch.object(self.plugin.threading, 'Timer').start()
        self.addCleanup(patch.stopall)
        self.addCleanup(self.plugin._cancel_timer)

    def start(self):
        self.plugin._on_session_start(platform='cli', session_id='main')

    def test_overlapping_turns_stay_working_until_all_close(self):
        self.start()
        self.plugin._turn_open(session_id='main')
        self.plugin._turn_open(session_id='child')
        self.plugin._turn_close(session_id='child')
        self.assertEqual(self.reports[-1], ('working',))
        self.plugin._turn_close(session_id='main')
        self.assertEqual(self.reports[-1], ('idle',))

    def test_stray_tool_does_not_open_turn(self):
        self.start()
        self.plugin._tool(session_id='background')
        self.assertEqual(self.reports, [('idle',)])
        self.assertFalse(self.plugin._turns)

    def test_quick_approval_does_not_report_blocked(self):
        self.start()
        self.plugin._turn_open(session_id='main')
        self.plugin._approval_request(description='Allow command')
        self.timer.assert_called_once()
        callback = self.timer.call_args.args[1]
        callback_args = self.timer.call_args.kwargs['args']
        self.plugin._approval_response()
        # Simulate a cancelled timer callback racing with the response.
        callback(*callback_args)
        self.assertFalse(any(report[0] == 'blocked' for report in self.reports))
        self.assertEqual(self.reports[-1], ('working',))

    def test_cancelled_timer_cannot_report_old_prompt_after_new_request(self):
        self.start()
        self.plugin._turn_open(session_id='main')
        self.plugin._approval_request(description='Old prompt')
        old_callback = self.timer.call_args.args[1]
        old_args = self.timer.call_args.kwargs['args']
        self.plugin._approval_response()
        self.plugin._approval_request(description='New prompt')
        new_callback = self.timer.call_args.args[1]
        new_args = self.timer.call_args.kwargs['args']
        before = list(self.reports)

        # Cancellation cannot stop an old callback already waiting for _lock.
        old_callback(*old_args)
        self.assertEqual(self.reports, before)
        new_callback(*new_args)
        self.assertEqual(self.reports[-1],
                         ('blocked', 'permission', 'Approval needed'))

    def test_pending_approval_blocks_until_every_response(self):
        self.start()
        self.plugin._turn_open(session_id='main')
        self.plugin._approval_request(description='Allow command')
        self.plugin._approval_request(description='Allow another command')
        callback = self.timer.call_args.args[1]
        callback(*self.timer.call_args.kwargs['args'])
        self.assertEqual(self.reports[-1],
                         ('blocked', 'permission', 'Approval needed'))
        before = len(self.reports)
        self.plugin._approval_response()
        self.assertEqual(len(self.reports), before)
        self.plugin._approval_response()
        self.assertEqual(self.reports[-1], ('working',))

    def test_partial_out_of_order_response_cannot_report_resolved_description(self):
        self.start()
        self.plugin._turn_open(session_id='main')
        self.plugin._approval_request(description='Prompt A', surface='cli')
        self.plugin._approval_request(description='Prompt B', surface='cli')
        callback = self.timer.call_args.args[1]
        callback_args = self.timer.call_args.kwargs['args']
        # B resolves first, leaving only A pending when B's timer fires.
        self.plugin._approval_response(description='Prompt B', surface='cli', choice='once')
        self.assertEqual(self.plugin._pending, 1)
        callback(*callback_args)
        self.assertEqual(self.reports[-1],
                         ('blocked', 'permission', 'Approval needed'))
        self.plugin._approval_response(description='Prompt A', surface='cli', choice='once')
        self.assertEqual(self.reports[-1], ('working',))

    def test_new_session_cannot_overwrite_blocked_while_approval_pending(self):
        for open_turn in (False, True):
            with self.subTest(open_turn=open_turn):
                self.start()
                if open_turn:
                    self.plugin._turn_open(session_id='main')
                self.plugin._approval_request(description='Allow command')
                callback = self.timer.call_args.args[1]
                callback(*self.timer.call_args.kwargs['args'])
                self.assertEqual(self.reports[-1],
                                 ('blocked', 'permission', 'Approval needed'))
                before = list(self.reports)
                self.plugin._on_session_start(platform='cli', session_id='new')
                self.assertEqual(self.reports, before)
                self.assertEqual(self.plugin._pending, 1)
                self.plugin._approval_response()
                self.assertEqual(self.reports[-1],
                                 ('working' if open_turn else 'idle',))
                self.plugin._finalize()

    def test_guardian_checks_are_not_human_approvals(self):
        self.start()
        self.plugin._approval_request(surface='smart')
        self.plugin._approval_response(surface='smart')
        self.assertEqual(self.plugin._pending, 0)
        self.timer.assert_not_called()

    def test_noninteractive_session_is_silent(self):
        self.plugin._on_session_start(platform='telegram')
        self.plugin._turn_open(session_id='gateway')
        self.plugin._approval_request()
        self.plugin._turn_close(session_id='gateway')
        self.assertEqual(self.reports, [])

    def test_finalize_clears_turns_and_approvals(self):
        self.start()
        self.plugin._turn_open(session_id='main')
        self.plugin._approval_request()
        self.plugin._finalize()
        self.assertFalse(self.plugin._turns)
        self.assertEqual(self.plugin._pending, 0)
        self.assertIsNone(self.plugin._timer)
        self.assertEqual(self.reports[-1], ('idle',))


if __name__ == '__main__':
    unittest.main()
