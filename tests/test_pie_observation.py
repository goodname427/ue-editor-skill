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


class PieObservationTests(unittest.TestCase):
    def setUp(self):
        self.lib = mock.Mock()
        path = ROOT / 'skills' / 'ue-editor' / 'scripts' / 'lib' / 'ue_input.py'
        common = SimpleNamespace(require=lambda name: self.lib, parse=json.loads)
        with mock.patch.dict(sys.modules, unreal=SimpleNamespace(), ue_common=common):
            spec = importlib.util.spec_from_file_location('pie_input_under_test', path)
            self.input = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.input)
        self.viewport = {'instance': 1, 'world': '/Game/UEDPIE_1_Map', 'window': 'Editor', 'rect': [0, 0, 100, 100]}
        self.lib.list_pie_viewports.return_value = json.dumps([self.viewport])
        self.lib.get_keyboard_focus.return_value = '{}'
        self.lib.find_widgets.return_value = json.dumps([{'type': 'SViewport', 'rect': [0, 0, 100, 100], 'pie_instance': 1}])
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'title': 'Editor', 'nodes': []}]})

    def node(self, **values):
        return dict(type='SButton', name='Button', window='Editor', rect=[10, 10, 20, 20], pie_instance=1, **values)

    def test_no_viewport_does_not_scan_editor_tree(self):
        self.lib.list_pie_viewports.return_value = '[]'
        self.assertEqual(self.input.observe_ui(scope='pie')['status'], 'no_pie_viewport')
        self.lib.dump_slate_tree.assert_not_called()

    def test_multiple_instances_need_selection(self):
        self.lib.list_pie_viewports.return_value = json.dumps([self.viewport, dict(self.viewport, instance=2)])
        self.assertEqual(self.input.observe_ui(scope='pie')['status'], 'selection_required')
        self.lib.dump_slate_tree.assert_not_called()
        self.lib.find_widgets.return_value = json.dumps([{'type': 'SViewport', 'rect': [0, 0, 100, 100], 'pie_instance': 2}])
        self.assertEqual(self.input.observe_ui(scope='pie', instance=2)['status'], 'observed')
        self.assertEqual(self.input.observe_ui(scope='pie', instance=2)['selected']['instance'], 2)

    def test_root_is_selected_inside_pie_not_first_editor_match(self):
        self.lib.find_widgets.return_value = json.dumps([{'type': 'SViewport', 'rect': [-200, 0, 100, 100]},
                                                       {'type': 'SViewport', 'rect': [0, 0, 100, 100], 'pie_instance': 1}])
        self.input.observe_ui(scope='pie', depth=3, limit=12)
        self.lib.dump_slate_tree.assert_called_once_with('Editor', 'type=SViewport', 3, False, True, 12, 1)

    def test_overlapping_editor_panel_is_not_a_pie_root(self):
        self.lib.find_widgets.return_value = json.dumps([{'type': 'SLevelEditor', 'rect': [0, 0, 100, 100]}])
        self.assertEqual(self.input.observe_ui(scope='pie', root='type=SLevelEditor')['status'], 'root_not_found')
        self.lib.dump_slate_tree.assert_not_called()

    def test_ambiguous_root_is_not_guessed(self):
        self.lib.find_widgets.return_value = json.dumps([self.node(), self.node()])
        self.assertEqual(self.input.observe_ui(scope='pie', root='name=Button')['status'], 'root_ambiguous')
        self.lib.dump_slate_tree.assert_not_called()

    def test_bounded_observation_reports_target_ambiguity_without_refs(self):
        button = self.node(interactable=True)
        self.lib.find_widgets.side_effect = [json.dumps([{'type': 'SViewport', 'rect': [0, 0, 100, 100], 'pie_instance': 1}]),
                                            json.dumps([button, button])]
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'nodes': [button, button]}], 'truncated': True})
        result = self.input.observe_ui(scope='pie')
        self.assertTrue(result['truncated'])
        self.assertEqual(result['nodes'][0]['target_match_count'], 2)
        self.assertEqual(self.lib.find_widgets.call_count, 2)
        self.assertNotIn('ref', result['nodes'][0])
        self.assertIn('omitted nodes', result['recovery'])

    def test_bad_limits_fail_before_query(self):
        with self.assertRaises(ValueError):
            self.input.observe_ui(scope='pie', limit=301)
        self.lib.list_pie_viewports.assert_not_called()

    def test_readiness_waits_for_visible_and_two_equal_samples(self):
        self.lib.find_widgets.side_effect = ['[]', json.dumps([self.node()]), json.dumps([self.node()])]
        self.assertEqual(self.input.readiness('name=Button')['reason'], 'target_not_visible')
        first = self.input.readiness('name=Button')
        self.assertEqual(first['status'], 'waiting')
        self.assertEqual(self.input.readiness('name=Button', previous=first['sample'])['status'], 'ready')
        self.lib.mouse_down.assert_not_called()

    def test_readiness_refuses_ambiguity_disabled_and_bad_index(self):
        for nodes, index, reason in (([self.node(), self.node()], None, 'ambiguous_target'),
                                     ([self.node(enabled=False)], None, 'target_disabled'),
                                     ([self.node()], 9, 'index_out_of_range')):
            with self.subTest(reason=reason):
                self.lib.find_widgets.return_value = json.dumps(nodes)
                self.assertEqual(self.input.readiness('name=Button', index=index)['reason'], reason)

    def test_geometry_change_resets_sample(self):
        self.lib.find_widgets.return_value = json.dumps([self.node()])
        previous = self.input.readiness('name=Button')['sample']
        self.lib.find_widgets.return_value = json.dumps([dict(self.node(), rect=[12, 10, 20, 20])])
        self.assertEqual(self.input.readiness('name=Button', previous=previous)['status'], 'waiting')


class ReadyGateTests(unittest.TestCase):
    def response(self, state):
        return {'status': 'ok', 'result': repr(json.dumps(state))}

    def test_waiting_never_queues_action_and_ready_sends_once(self):
        bridge = mock.Mock()
        bridge.execute.return_value = {'status': 'ok', 'output': ''}
        bridge.evaluate.side_effect = [self.response({'status': 'waiting', 'reason': 'geometry_settling', 'sample': {}}),
                                       self.response({'status': 'ready'})]
        args = SimpleNamespace(ready_timeout=1, ready_target=('name=Button', '', None), wait_until=None)
        with mock.patch.object(ue_cli.time, 'sleep'):
            result = ue_cli._execute_and_wait(bridge, 'action', args)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(bridge.execute.call_args_list[-1].args[0], 'action')
        self.assertEqual(sum(c.args[0] == 'action' for c in bridge.execute.call_args_list), 1)

    def test_refused_and_timeout_never_send_action(self):
        for status, expected in (('refused', 'TargetRefused'), ('waiting', 'TargetReadyTimeout')):
            bridge = mock.Mock()
            bridge.execute.return_value = {'status': 'ok'}
            bridge.evaluate.return_value = self.response({'status': status, 'reason': 'unavailable', 'sample': None})
            args = SimpleNamespace(ready_timeout=1 if status == 'refused' else 1e-9, ready_target=('name=Button', '', None), wait_until=None)
            result = ue_cli._execute_and_wait(bridge, 'action', args)
            self.assertEqual(result['error_type'], expected)
            self.assertFalse(result['command_sent'])
            self.assertEqual(bridge.execute.call_count, 1)

    def test_ready_response_after_deadline_does_not_send_action(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = self.response({'status': 'ready', 'reason': 'geometry_sampled'})
        with mock.patch.object(ue_cli.time, 'monotonic', side_effect=[0, 0.1, 1.1]):
            result = ue_cli._wait_ready(bridge, ('name=Button', '', None), 1)
        self.assertEqual(result['error_type'], 'TargetReadyTimeout')
        self.assertFalse(result['command_sent'])
        bridge.execute.assert_not_called()

    def test_deadline_expiry_does_not_start_another_query(self):
        bridge = mock.Mock()
        with mock.patch.object(ue_cli.time, 'monotonic', side_effect=[0, 1]):
            result = ue_cli._wait_ready(bridge, ('name=Button', '', None), 1)
        self.assertEqual(result['error_type'], 'TargetReadyTimeout')
        bridge.evaluate.assert_not_called()

    def test_resumable_query_is_not_followed_by_action(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'error', 'error_type': 'Timeout', 'resumable': True}
        result = ue_cli._wait_ready(bridge, ('name=Button', '', None), 1)
        self.assertTrue(result['resumable'])
        self.assertFalse(result['command_sent'])
        bridge.execute.assert_not_called()

    def test_invalid_gate_arguments_fail_before_connection(self):
        cases = (['--ready-timeout=31'], ['--ready-timeout=1', '--no-check'],
                 ['--ready-timeout=1', '--index=-1'], ['--ready-timeout=1', '--at=1,2'])
        for options in cases:
            with self.subTest(options=options), mock.patch.object(sys, 'argv', ['ue_cli.py', 'exec', '--action=ui', 'click', 'name=Button'] + options), \
                    mock.patch.object(ue_cli, '_run') as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    ue_cli.main()
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
