import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import test_pie_observation as pie_tests
import ue_cli


class WindowObservationTests(unittest.TestCase):
    def setUp(self):
        pie_tests.PieObservationTests.setUp(self)
        self.window = {'title': 'Editor', 'active': True, 'rect': [0, 0, 100, 100]}
        self.lib.list_windows.return_value = json.dumps([self.window])
        self.lib.find_widgets.return_value = json.dumps([{'window': 'Editor', 'window_rect': [0, 0, 100, 100], 'type': 'SWindow', 'rect': [0, 0, 100, 100]}])

    def test_empty_replacement_deletes_selection_but_append_does_not(self):
        for replace in (True, False):
            with self.subTest(replace=replace), mock.patch.object(self.input, 'focus'), \
                    mock.patch.object(self.input, 'select_all') as select, mock.patch.object(self.input, 'type_chars') as chars, \
                    mock.patch.object(self.input, 'key') as key, mock.patch.object(self.input, 'wait'), \
                    mock.patch.object(self.input, 'check'), mock.patch.object(self.input, 'read_text', return_value='old'):
                self.input.input_text('hint=Search', '', replace=replace)
                if replace:
                    select.assert_called_once()
                    key.assert_called_once_with('BackSpace')
                    chars.assert_not_called()
                else:
                    select.assert_not_called()
                    key.assert_not_called()
                    chars.assert_called_once_with('')

    def test_default_observes_window_without_pie_query(self):
        result = self.input.observe_ui()
        self.assertEqual(result['kind'], 'ui')
        self.assertEqual(result['scope'], 'window')
        self.assertEqual(result['status'], 'observed')
        self.assertNotIn('viewports', result)
        self.lib.list_pie_viewports.assert_not_called()
        self.lib.dump_slate_tree.assert_called_once_with('Editor', 'type=SWindow', 6, False, True, 80, 0)

    def test_active_window_is_used_only_when_no_window_was_requested(self):
        self.lib.list_windows.return_value = json.dumps([dict(self.window, title='Other', active=False), self.window])
        self.assertEqual(self.input.observe_ui()['selected']['window'], 'Editor')
        self.assertEqual(self.input.observe_ui(window='missing')['status'], 'no_window')
        self.assertEqual(self.input.observe_ui(window='e')['status'], 'selection_required')

    def test_ambiguous_windows_are_not_guessed(self):
        self.lib.list_windows.return_value = json.dumps([dict(self.window, active=False), dict(self.window, title='Other', active=False)])
        self.assertEqual(self.input.observe_ui()['status'], 'selection_required')
        self.lib.dump_slate_tree.assert_not_called()

    def test_docked_root_does_not_require_pie_ancestry(self):
        self.lib.find_widgets.return_value = json.dumps([{'window': 'Editor', 'window_rect': [0, 0, 100, 100], 'type': 'SContentBrowser', 'rect': [10, 10, 40, 40]}])
        self.assertEqual(self.input.observe_ui(root='type=SContentBrowser')['status'], 'observed')
        self.lib.list_pie_viewports.assert_not_called()

    def test_duplicate_titles_with_same_root_are_refused(self):
        self.lib.find_widgets.return_value = json.dumps([{'window': 'Editor', 'window_rect': [0, 0, 100, 100], 'type': 'SContentBrowser', 'rect': [10, 10, 40, 40]},
                                                        {'window': 'Editor', 'window_rect': [0, 0, 100, 100], 'type': 'SContentBrowser', 'rect': [110, 10, 40, 40]}])
        self.assertEqual(self.input.observe_ui(root='type=SContentBrowser')['status'], 'root_ambiguous')

    def test_untitled_popup_uses_exact_root_rect_not_first_window(self):
        self.lib.list_windows.return_value = json.dumps([dict(self.window, active=False), {'title': '', 'active': True, 'rect': [20, 20, 30, 30]}])
        self.lib.find_widgets.return_value = json.dumps([{'window': 'Editor', 'window_rect': [0, 0, 100, 100], 'type': 'SWindow', 'rect': [0, 0, 100, 100]},
                                                        {'window': '', 'window_rect': [20, 20, 30, 30], 'type': 'SWindow', 'rect': [20, 20, 30, 30]}])
        self.assertEqual(self.input.observe_ui()['selected']['window'], '')
        self.lib.dump_slate_tree.assert_called_once_with('', 'type=SWindow', 6, False, True, 80, 1)

    def test_root_in_another_untitled_window_is_not_selected(self):
        self.lib.list_windows.return_value = json.dumps([{'title': '', 'active': True, 'rect': [0, 0, 100, 100]},
                                                        {'title': '', 'active': False, 'rect': [200, 0, 100, 100]}])
        self.lib.find_widgets.return_value = json.dumps([{'window': '', 'window_rect': [200, 0, 100, 100],
                                                        'type': 'SMenu', 'rect': [200, 0, 80, 80]}])
        self.assertEqual(self.input.observe_ui(root='type=SMenu')['status'], 'root_not_found')
        self.lib.dump_slate_tree.assert_not_called()

    def test_native_icon_button_gets_type_and_label_target(self):
        self.lib.find_widgets.side_effect = [json.dumps([{'window': 'Editor', 'window_rect': [0, 0, 100, 100], 'type': 'SWindow', 'rect': [0, 0, 100, 100]}]), '[{}]']
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'nodes': [{'type': 'SButton', 'rect': [10, 10, 20, 20],
                                                           'label': 'Save Level', 'interactable': True}]}]})
        node = self.input.observe_ui()['nodes'][0]
        self.assertEqual(node['target'], 'type=SButton;label=Save Level')
        self.assertEqual(node['target_match_count'], 1)

    def test_instance_requires_explicit_pie_scope(self):
        with self.assertRaises(ValueError):
            self.input.observe_ui(instance=1)
        self.lib.list_windows.assert_not_called()


class WindowCommandTests(unittest.TestCase):
    def args(self, **values):
        return SimpleNamespace(observe_ui=True, observe=None, ui_scope='window', ui_window='Editor', ui_root='',
                               ui_instance=None, ui_depth=6, ui_limit=80, screenshot=None, shot_widget=None,
                               shot_name=None, shot_archive=None, shot_instance=None, shot_max_width=1600,
                               shot_wait_stable=0, **values)

    def test_standalone_observe_failure_reports_structured_check(self):
        source = (Path(ue_cli.ACTIONS_DIR) / 'ui.py').read_text(encoding='utf-8')
        state = {'kind': 'ui', 'scope': 'window', 'status': 'root_not_found'}
        module = SimpleNamespace(LIB=mock.Mock(), parse=json.loads, describe=str, MAX_HOLD=30,
                                 observe_ui=mock.Mock(return_value=state), check=mock.Mock())
        with mock.patch.dict(sys.modules, ue_input=module), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source, 'actions/ui.py', 'exec'), {'ARGS': ['observe'], 'OPTS': {}})
        expression = module.check.call_args.args[0]
        actual = json.loads(eval(expression))
        self.assertFalse(actual['ok'])
        self.assertEqual(actual['observation'], state)
        self.assertEqual(module.observe_ui.call_args.args[-1], 'window')

    def test_post_action_observation_scope_and_window_are_passed(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': repr(json.dumps({'kind': 'ui', 'scope': 'window', 'status': 'observed'}))}
        result = ue_cli._observe_after(bridge, {'status': 'ok'}, self.args())
        self.assertEqual(result['status'], 'ok')
        self.assertIn("'Editor'", bridge.evaluate.call_args.args[0])
        self.assertIn("'window'", bridge.evaluate.call_args.args[0])
        bridge.execute.assert_not_called()

    def test_wrong_scope_response_is_not_accepted(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': repr(json.dumps({'kind': 'ui', 'scope': 'pie', 'status': 'observed'}))}
        self.assertEqual(ue_cli._observe_after(bridge, {'status': 'ok'}, self.args())['error_type'], 'ObservationFailed')

    def test_window_screenshot_is_bound_to_selected_window(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': repr(json.dumps({'kind': 'ui', 'scope': 'window', 'status': 'observed',
                                                                                'selected': {'window': 'Editor', 'rect': [-100, 20, 400, 200]}}))}
        args = self.args()
        args.screenshot = 'window'
        def capture(actual, connection):
            self.assertIs(connection, bridge)
            self.assertEqual(actual.rect, '-100,20,400,200')
            self.assertEqual(actual.window, 'Editor')
            print(json.dumps({'status': 'ok', 'path': 'window.png'}))
        with mock.patch.object(ue_cli, 'cmd_screenshot', side_effect=capture):
            self.assertEqual(ue_cli._observe_after(bridge, {'status': 'ok'}, args)['status'], 'ok')

    def test_window_observation_does_not_invent_pie_instance_for_screenshot(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': repr(json.dumps({'kind': 'ui', 'scope': 'window', 'status': 'observed',
                                                                                'selected': {'window': 'Editor', 'rect': [0, 0, 100, 100]}}))}
        args = self.args()
        args.screenshot = 'pie'
        def capture(actual, connection):
            self.assertIsNone(actual.instance)
            print(json.dumps({'status': 'ok', 'path': 'pie.png'}))
        with mock.patch.object(ue_cli, 'cmd_screenshot', side_effect=capture):
            self.assertEqual(ue_cli._observe_after(bridge, {'status': 'ok'}, args)['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
