import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'ue-editor' / 'scripts'))
import ue_cli


class ObservationTests(unittest.TestCase):
    def args(self, **values):
        return SimpleNamespace(observe='state()', screenshot=None, shot_widget=None, shot_name=None,
                               shot_archive=None, shot_instance=None, shot_max_width=1600,
                               shot_wait_stable=0, **values)

    def test_observes_without_reexecuting_action(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': '{"count": 2}'}
        result = ue_cli._observe_after(bridge, {'status': 'ok', 'output': 'action done'}, self.args())
        self.assertEqual(result['observation'], '{"count": 2}')
        bridge.execute.assert_not_called()
        bridge.evaluate.assert_called_once_with('state()')

    def test_input_failure_keeps_original_error_and_adds_state(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': 'blocked'}
        result = ue_cli._observe_after(bridge, {'status': 'error', 'error_type': 'InputAssertionFailed'}, self.args())
        self.assertEqual(result['error_type'], 'InputAssertionFailed')
        self.assertEqual(result['observation'], 'blocked')

    def test_action_timeout_does_not_append_queries(self):
        bridge = mock.Mock()
        result = {'status': 'error', 'error_type': 'Timeout', 'resumable': True}
        self.assertIs(ue_cli._observe_after(bridge, result, self.args()), result)
        bridge.evaluate.assert_not_called()

    def test_observation_failure_is_not_action_failure_or_replay(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'error', 'error_type': 'ExecutionError', 'message': 'unknown state'}
        result = ue_cli._observe_after(bridge, {'status': 'ok'}, self.args())
        self.assertEqual(result['error_type'], 'ObservationFailed')
        self.assertTrue(result['command_sent'])
        bridge.execute.assert_not_called()

    def test_observation_timeout_skips_screenshot(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'error', 'error_type': 'Timeout', 'resumable': True}
        args = self.args()
        args.screenshot = 'pie'
        with mock.patch.object(ue_cli, 'cmd_screenshot') as shot:
            result = ue_cli._observe_after(bridge, {'status': 'ok'}, args)
        shot.assert_not_called()
        self.assertEqual(result['error_type'], 'ObservationFailed')

    def test_screenshot_reuses_same_bridge(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': 'state'}
        args = self.args()
        args.screenshot, args.shot_archive = 'pie', 'evidence'
        def capture(actual, connection):
            self.assertIs(connection, bridge)
            self.assertTrue(actual.pie)
            self.assertEqual(actual.archive, 'evidence')
            print(json.dumps({'status': 'ok', 'path': 'shot.png', 'stable': False}))
        with mock.patch.object(ue_cli, 'cmd_screenshot', side_effect=capture):
            result = ue_cli._observe_after(bridge, {'status': 'ok'}, args)
        self.assertFalse(result['screenshot']['stable'])
        self.assertEqual(result['status'], 'ok')

    def test_viewports_query_uses_existing_connection(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': repr('[{"instance": 1}]')}
        with mock.patch.object(ue_cli, '_run') as reconnect:
            self.assertEqual(ue_cli._pie_viewports(None, bridge), [{'instance': 1}])
        reconnect.assert_not_called()


class PresentationTests(unittest.TestCase):
    def test_compact_preserves_checks_without_merging_different_states(self):
        raw = '[input-request] 1\n[input-check] check()\nrequested\n'
        raw += '[input checked] {"success":true,"pending":false,"focus":{"name":"A"}}\n'
        raw += '[input checked] {"success":true,"pending":false,"focus":{"name":"B"}}\n'
        result = {'status': 'ok', 'output': raw}
        presented = ue_cli._present_result(result)
        self.assertNotIn('[input-request]', presented['output'])
        self.assertNotIn('[input-check]', presented['output'])
        self.assertIn('"A"', presented['output'])
        self.assertIn('"B"', presented['output'])
        self.assertIn('not business success', presented['output'])
        self.assertEqual(result['output'], raw)
        self.assertIs(ue_cli._present_result(result, True), result)

    def test_failure_does_not_claim_all_input_steps_completed(self):
        result = ue_cli._present_result({'status': 'error', 'output': '[input-request] 1\n[input-request] 2\n'})
        self.assertIn('[input requested]', result['output'])
        self.assertNotIn('[input completed]', result['output'])


class CommandContractTests(unittest.TestCase):
    def test_tree_default_is_bounded_and_can_be_expanded(self):
        source = (Path(ue_cli.ACTIONS_DIR) / 'ui.py').read_text(encoding='utf-8')
        for options, expected in (({}, 120), ({'max': '500'}, 500)):
            lib = mock.Mock()
            lib.dump_slate_tree.return_value = json.dumps({'windows': []})
            module = SimpleNamespace(LIB=lib, parse=json.loads, describe=str, MAX_HOLD=30)
            with self.subTest(options=options), mock.patch.dict(sys.modules, ue_input=module), \
                    contextlib.redirect_stdout(io.StringIO()):
                exec(compile(source, 'actions/ui.py', 'exec'), {'ARGS': ['tree'], 'OPTS': options})
            self.assertEqual(lib.dump_slate_tree.call_args.args[5], expected)

    def test_invalid_observation_options_are_rejected_before_connect(self):
        cases = (['--observe=invalid('], ['--screenshot=widget'],
                 ['--screenshot=pie', '--shot-wait-stable=31'], ['--screenshot=pie', '--shot-name=CON'])
        for options in cases:
            with self.subTest(options=options), mock.patch.object(sys, 'argv', ['ue_cli.py', 'exec', 'print(1)'] + options), \
                    mock.patch.object(ue_cli, '_run') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    ue_cli.main()
                self.assertEqual(error.exception.code, 2)
                run.assert_not_called()

    def test_ui_argument_error_is_concise_but_verbose_keeps_stack(self):
        message = 'Traceback (most recent call last):\n  File "actions/ui.py", line 1\nRuntimeError: no widget at index 9\n  [0] A'
        for verbose in (False, True):
            output = io.StringIO()
            args = ['ue_cli.py', 'exec', '--action=ui', 'move', 'name=A'] + (['--verbose'] if verbose else [])
            with self.subTest(verbose=verbose), mock.patch.object(sys, 'argv', args), \
                    mock.patch.object(ue_cli, '_run', return_value={'status': 'error', 'error_type': 'ExecutionError', 'message': message}), \
                    contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as error:
                    ue_cli.main()
            self.assertEqual(error.exception.code, 1)
            actual = json.loads(output.getvalue())['message']
            self.assertEqual('Traceback' in actual, verbose)
            self.assertIn('[0] A', actual)

    def test_successful_condition_omits_routing_details_but_not_stale_condition(self):
        raw = '[input-request] 1\n[input checked] {"success":true,"pending":false,"hit":{"name":"A"}}\n'
        result = {'status': 'ok', 'output': raw, 'condition_met': True}
        self.assertNotIn('[input results]', ue_cli._present_result(result)['output'])
        self.assertIn('postcondition holds', ue_cli._present_result(result)['output'])
        result['wait_note'] = 'already true'
        self.assertIn('[input results]', ue_cli._present_result(result)['output'])


class SequenceFeedbackTests(unittest.TestCase):
    def step(self, **values):
        return dict(name='step', parameters='params', code='action', wait=0, **values)

    def test_input_failure_reads_state_and_does_not_execute_next_step(self):
        bridge = mock.Mock()
        bridge.execute.side_effect = [{'status': 'ok'}, {'status': 'error', 'error_type': 'InputAssertionFailed',
                                    'command_sent': False, 'output': 'x' * 9000 + '\n[input-request] 7\n'}]
        bridge.evaluate.return_value = {'status': 'ok', 'result': 'blocked'}
        with contextlib.redirect_stderr(io.StringIO()):
            result = ue_cli._run_sequence(bridge, [self.step(state='snapshot()'), self.step()])
        self.assertEqual(bridge.execute.call_count, 2)
        self.assertEqual(bridge.evaluate.call_args_list[0].args[0], 'snapshot()')
        self.assertEqual(result['last_state'], 'blocked')
        self.assertFalse(result['command_sent'])
        self.assertTrue(result['input_released'])
        presented = ue_cli._present_result(result)
        self.assertTrue(presented['output_truncated'])

    def test_wait_expression_error_keeps_action_context(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'error', 'error_type': 'ExecutionError', 'message': 'NameError'}
        result = ue_cli._wait_until(bridge, {'status': 'ok', 'output': 'action done'},
                                    SimpleNamespace(wait_until='missing()', wait=0))
        self.assertEqual(result['output'], 'action done')
        self.assertTrue(result['command_sent'])


if __name__ == '__main__':
    unittest.main()
