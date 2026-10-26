import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'ue-editor' / 'scripts'))
import ue_cli


class AnalogTests(unittest.TestCase):
    def setUp(self):
        self.callbacks = {}
        self.lib = mock.Mock()
        self.lib.wait_input.side_effect = [json.dumps({'success': True, 'request_id': 1}),
                                         json.dumps({'success': True, 'request_id': 2})]
        self.lib.get_input_result.return_value = json.dumps({'success': True, 'pending': False})
        self.lib.analog_input.return_value = json.dumps({'success': True, 'handled': False,
                                                       'device_id': 0, 'platform_user': 0, 'slate_user': 0})
        self.editor = mock.Mock()
        self.editor.is_in_play_in_editor.return_value = False
        self.unreal = SimpleNamespace(AgentSlateDriverFunctionLib=self.lib, LevelEditorSubsystem=object,
                                      get_editor_subsystem=lambda _: self.editor,
                                      register_slate_post_tick_callback=self.register,
                                      unregister_slate_post_tick_callback=self.unregister)
        path = ROOT / 'skills' / 'ue-editor' / 'scripts' / 'lib'
        self.modules = mock.patch.dict(sys.modules, unreal=self.unreal)
        self.modules.start()
        self.addCleanup(self.modules.stop)
        self.paths = mock.patch.object(sys, 'path', [str(path)] + sys.path)
        self.paths.start()
        self.addCleanup(self.paths.stop)
        sys.modules.pop('ue_common', None)
        spec = importlib.util.spec_from_file_location('input_under_test', path / 'ue_input.py')
        self.input = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.input)
        self.preserve_cursor = self.input.preserve_cursor
        self.input.preserve_cursor = mock.Mock(return_value={'pending': False, 'ok': True})
        self.lib.use_platform_cursor_for_cursor_user.return_value = json.dumps({'success': True, 'pos': [100, 200], 'visible': True})
        self.lib.set_cursor_position.return_value = json.dumps({'success': True})
        self.lib.set_cursor_visibility.return_value = json.dumps({'success': True})
        self.clock = mock.patch.object(self.input.time, 'monotonic', return_value=0.0)
        self.now = self.clock.start()
        self.addCleanup(self.clock.stop)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()
        self.addCleanup(self.output.__exit__, None, None, None)

    def register(self, callback):
        self.callbacks[1] = callback
        return 1

    def unregister(self, handle):
        self.callbacks.pop(handle, None)

    def tick(self, now):
        self.now.return_value = now
        for callback in list(self.callbacks.values()):
            callback(1 / 60)

    def test_cursor_isolation_covers_async_focus_before_restore(self):
        finished = {'done': False}
        guard = self.preserve_cursor(lambda: finished['done'])
        self.lib.use_platform_cursor_for_cursor_user.assert_called_once_with(False)
        self.lib.set_cursor_position.assert_called_once_with(100, 200)
        self.tick(0.1)
        self.assertTrue(guard['pending'])
        finished['done'] = True
        self.tick(0.2)
        self.assertTrue(guard['pending'])
        self.tick(0.3)
        self.assertTrue(guard['pending'])
        self.lib.use_platform_cursor_for_cursor_user.assert_called_once_with(False)
        self.tick(0.41)
        self.assertTrue(guard['ok'])
        self.assertFalse(guard['pending'])
        self.lib.set_cursor_visibility.assert_called_once_with(True)
        self.assertEqual(self.lib.use_platform_cursor_for_cursor_user.call_args_list, [mock.call(False), mock.call(True)])
        self.lib.set_cursor_position.assert_called_once_with(100, 200)
        self.assertFalse(self.callbacks)

    def test_cursor_timeout_restores_and_reports_failure(self):
        guard = self.preserve_cursor(lambda: False, timeout=1)
        self.tick(2)
        self.assertFalse(guard['pending'])
        self.assertFalse(guard['ok'])
        self.lib.use_platform_cursor_for_cursor_user.assert_called_with(True)
        self.assertFalse(self.callbacks)

    def test_cursor_restores_platform_binding_even_if_visibility_fails(self):
        guard = self.preserve_cursor(lambda: True)
        self.lib.set_cursor_visibility.side_effect = RuntimeError('visibility failed')
        self.tick(0.1)
        self.tick(0.31)
        self.assertFalse(guard['ok'])
        self.assertIn('visibility failed', guard['message'])
        self.lib.use_platform_cursor_for_cursor_user.assert_called_with(True)
        self.assertFalse(self.callbacks)

    def test_analog_check_waits_for_cursor_restoration(self):
        result = {'pending': False, 'ok': True, 'cursor': {'pending': True, 'ok': False}}
        self.assertTrue(json.loads(self.input.check_analog(result))['pending'])
        result['cursor'].update(pending=False, ok=True)
        self.assertTrue(json.loads(self.input.check_analog(result))['ok'])

    def test_key_uses_one_guard_and_can_opt_out(self):
        self.lib.key_down.return_value = json.dumps({'success': True, 'request_id': 10})
        self.lib.key_up.return_value = json.dumps({'success': True, 'request_id': 11})
        self.input.key('Gamepad_LeftShoulder')
        self.input.preserve_cursor.assert_called_once()
        self.input.preserve_cursor.reset_mock()
        self.lib.wait_input.side_effect = None
        self.lib.wait_input.return_value = json.dumps({'success': True, 'request_id': 12})
        self.input.key('Gamepad_LeftShoulder', protect_cursor=False)
        self.input.preserve_cursor.assert_not_called()

    def test_cursor_registration_failure_restores_binding(self):
        with mock.patch.object(self.unreal, 'register_slate_post_tick_callback', side_effect=RuntimeError('register failed')):
            with self.assertRaisesRegex(RuntimeError, 'register failed'):
                self.preserve_cursor(lambda: False)
        self.lib.use_platform_cursor_for_cursor_user.assert_called_with(True)

    def test_raw_event_has_no_hold_or_pairing(self):
        result = self.input.analog_input('Gamepad_LeftX', 0.4, 0)
        self.lib.analog_input.assert_called_once_with('Gamepad_LeftX', 0.4, 0)
        self.lib.wait_input.assert_not_called()
        self.assertFalse(result['handled'])

    def test_batch_validates_then_pairs_and_resolves_device(self):
        result = self.input.analog_set({'Gamepad_LeftX': 0.4})
        self.assertEqual(result['values'], {'Gamepad_LeftX': 0.4, 'Gamepad_LeftY': 0.0})
        self.assertEqual(self.lib.analog_input.call_args_list,
                         [mock.call('Gamepad_LeftX', 0.4, -1), mock.call('Gamepad_LeftY', 0.0, 0)])

    def test_invalid_batch_sends_nothing(self):
        for values in ({}, {'Gamepad_LeftX': 0.5, 'Gamepad_Left2D': 1},
                       {'Gamepad_LeftX': float('nan')}, {'Gamepad_RightY': 2},
                       {'Gamepad_LeftTriggerAxis': -0.1}, {'Gamepad_RightTriggerAxis': float('inf')}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.input.analog_set(values)
        self.lib.analog_input.assert_not_called()

    def test_invalid_hold_does_not_register_or_queue(self):
        for hold in (-1, 31, float('nan'), float('inf')):
            with self.subTest(hold=hold), self.assertRaises(ValueError):
                self.input.analog({'Gamepad_LeftX': 1}, hold)
        self.assertFalse(self.callbacks)
        self.lib.wait_input.assert_not_called()

    def test_pulse_waits_for_timeline_and_neutralizes_next_tick(self):
        result = self.input.analog({'Gamepad_LeftX': 1})
        self.lib.get_input_result.return_value = json.dumps({'success': True, 'pending': True})
        self.tick(0)
        self.lib.analog_input.assert_not_called()
        self.lib.get_input_result.return_value = json.dumps({'success': True, 'pending': False})
        self.tick(0.1)
        self.assertTrue(result['pending'])
        self.assertEqual(result['samples'], 1)
        self.tick(0.2)
        self.assertTrue(result['ok'])
        self.assertFalse(result['pending'])
        self.assertFalse(self.callbacks)
        self.assertEqual(self.lib.analog_input.call_args_list[-2:],
                         [mock.call('Gamepad_LeftX', 0.0, 0), mock.call('Gamepad_LeftY', 0.0, 0)])

    def test_hold_repeats_until_duration_then_zero(self):
        result = self.input.analog({'Gamepad_RightY': -1}, hold=0.5)
        for now in (1.0, 1.2, 1.4):
            self.tick(now)
        self.assertEqual(result['samples'], 3)
        self.assertTrue(result['pending'])
        self.tick(1.6)
        self.assertTrue(result['ok'])
        self.assertEqual(self.lib.analog_input.call_args_list[-2:],
                         [mock.call('Gamepad_RightY', 0.0, 0), mock.call('Gamepad_RightX', 0.0, 0)])
        self.assertNotIn('cancel', json.loads(self.input.check_analog(result)))

    def test_cancel_neutralizes_and_is_not_success(self):
        result = self.input.analog({'Gamepad_LeftTriggerAxis': 1}, hold=10)
        self.tick(0)
        result['cancel']()
        self.assertTrue(result['pending'])
        self.tick(0.1)
        self.assertFalse(result['ok'])
        self.assertFalse(self.callbacks)
        self.lib.analog_input.assert_called_with('Gamepad_LeftTriggerAxis', 0.0, 0)

    def test_tail_cancel_after_sampling_neutralizes(self):
        result = self.input.analog({'Gamepad_RightX': 1}, hold=10)
        self.tick(0)
        self.lib.get_input_result.side_effect = lambda request: json.dumps(
            {'success': True, 'pending': False} if request == 1 else
            {'success': False, 'pending': False, 'message': 'Cancelled by ReleaseAllInput'})
        self.tick(0.1)
        self.assertFalse(result['ok'])
        self.assertIn('ReleaseAllInput', result['message'])
        self.assertFalse(self.callbacks)
        self.lib.analog_input.assert_any_call('Gamepad_RightX', 0.0, 0)

    def test_pie_end_neutralizes_and_unregisters(self):
        self.editor.is_in_play_in_editor.return_value = True
        result = self.input.analog({'Gamepad_LeftX': 1}, hold=10)
        self.tick(0)
        self.editor.is_in_play_in_editor.return_value = False
        self.tick(0.1)
        self.assertFalse(result['ok'])
        self.assertIn('PIE ended', result['message'])
        self.assertFalse(self.callbacks)
        self.lib.analog_input.assert_any_call('Gamepad_LeftX', 0.0, 0)

    def test_cancelled_gate_does_not_inject(self):
        result = self.input.analog({'Gamepad_LeftX': 1})
        self.lib.get_input_result.return_value = json.dumps({'success': False, 'pending': False, 'message': 'cancelled'})
        self.tick(0)
        self.assertFalse(result['ok'])
        self.assertFalse(self.callbacks)
        self.lib.analog_input.assert_not_called()

    def test_describe_escapes_multiline_text_fields(self):
        text = '\u4e2d\u6587\r\n"quoted"\\path\rend\n'
        node = {'type': 'STextBlock', 'rect': [1, 2, 3, 4],
                'text': text, 'hint': text, 'label': text}
        line = self.input.describe(node)
        self.assertEqual(len(line.splitlines()), 1)
        encoded = json.dumps(text, ensure_ascii=False)
        self.assertIn(' ' + encoded, line)
        self.assertIn('hint=' + encoded, line)
        self.assertIn('label=' + encoded, line)
        node.update(tag='tag\r\n', owner='owner\n', hidden_by='parent\r')
        self.assertEqual(len(self.input.describe(node).splitlines()), 1)
        self.assertEqual(self.input.describe(None), '(none)')

    def test_center_prefers_visible_rect(self):
        node = {'type': 'STextBlock', 'rect': [100, 200, 80, 100],
                'visible_rect': [100, 200, 80, 20], 'clipped': True}
        self.assertEqual(self.input.center(node), (140, 210))
        self.assertIn('visible=[100,200,80,20]', self.input.describe(node))
        self.assertIn('!clipped', self.input.describe(node))
        self.assertEqual(self.input.center({'rect': [100, 200, 80, 100]}), (140, 250))

    def test_zero_failure_is_reported(self):
        result = self.input.analog({'Gamepad_LeftTriggerAxis': 1})
        self.tick(0)
        self.lib.analog_input.side_effect = RuntimeError('mapping lost')
        self.tick(0.1)
        self.assertFalse(result['ok'])
        self.assertIn('mapping lost', result['message'])
        self.assertFalse(self.callbacks)


class InputCheckTests(unittest.TestCase):
    def response(self, state):
        return {'status': 'ok', 'result': repr(json.dumps(state))}

    def test_pending_check_uses_existing_poll_then_reads_final_state(self):
        bridge = mock.Mock()
        bridge.evaluate.side_effect = [self.response({'ok': False, 'pending': True, 'wait': 7}),
                                       self.response({'ok': True, 'pending': False, 'samples': 2})]
        result = {'status': 'ok', 'output': ''}
        with mock.patch.object(ue_cli, '_poll', return_value={'status': 'ok'}) as poll:
            self.assertIsNone(ue_cli._input_check(bridge, 'check_job()', result))
        self.assertIn('not __import__("json").loads', poll.call_args.args[1])
        self.assertIn('"samples": 2', result['output'])

    def test_failed_check_is_not_handled_success(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = self.response({'ok': False, 'pending': False, 'message': 'neutral failed'})
        result = ue_cli._input_check(bridge, 'check_job()', {'output': ''})
        self.assertEqual(result['error_type'], 'InputAssertionFailed')
        self.assertEqual(result['message'], 'neutral failed')

    def test_invalid_pending_timeout_rejected(self):
        for wait in (0, -1, float('inf'), float('nan'), '5'):
            bridge = mock.Mock()
            bridge.evaluate.return_value = self.response({'ok': False, 'pending': True, 'wait': wait})
            with self.subTest(wait=wait):
                self.assertEqual(ue_cli._input_check(bridge, 'check_job()', {'output': ''})['error_type'], 'InvalidResponse')


if __name__ == '__main__':
    unittest.main()
