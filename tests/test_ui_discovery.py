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


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        pie_tests.PieObservationTests.setUp(self)

    def observe_nodes(self, nodes, **options):
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'nodes': nodes}], 'truncated': False})
        self.lib.find_widgets.return_value = json.dumps([{'type': 'SViewport', 'rect': [0, 0, 100, 100], 'pie_instance': 1}])
        return self.input.observe_ui(scope='pie', summary=True, **options)

    def test_summary_finds_late_target_after_repeated_widgets(self):
        nodes = [dict(type='SObjectWidget', name='Panel', **{'class': 'Panel'}, rect=[0, 0, 100, 100], d=0)]
        nodes.extend(dict(type='SObjectWidget', name='Row_%d' % i, **{'class': 'Row'}, rect=[0, 0, 10, 10], d=1) for i in range(140))
        nodes.append(dict(type='SButton', name='Next', label='Next page', rect=[20, 20, 10, 10], d=1, interactable=True))
        result = self.observe_nodes(nodes)
        self.assertEqual(self.lib.dump_slate_tree.call_args.args[5], 1000)
        self.assertEqual(result['nodes'], [])
        summary = result['summary']
        self.assertEqual(summary['scanned_nodes'], 142)
        self.assertEqual(summary['targets'][0]['name'], 'Next')
        self.assertEqual(summary['repeated_widgets'][0]['observed_count'], 140)
        self.assertEqual(len(summary['repeated_widgets'][0]['examples']), 3)
        self.assertIn('not logical list items', summary['coverage'])
        self.assertEqual(self.lib.find_widgets.call_count, 2)

    def test_summary_filters_off_view_and_query_only_nodes(self):
        nodes = [dict(type='SButton', name='Offscreen', rect=[200, 0, 10, 10], interactable=True),
                 dict(type='SButton', name='Hidden', rect=[0, 0, 10, 10], interactable=True, query_only=True),
                 dict(type='SButton', name='Disabled', rect=[0, 0, 10, 10], interactable=True, enabled=False)]
        summary = self.observe_nodes(nodes)['summary']
        self.assertEqual(summary['excluded_nodes'], 2)
        self.assertEqual(len(summary['targets']), 1)
        self.assertFalse(summary['targets'][0]['enabled'])

    def test_summary_bounds_all_categories_and_reports_truncation(self):
        nodes = [dict(type='SButton', name='Button_%d' % i, text=str(i), rect=[0, 0, 10, 10], interactable=True) for i in range(30)]
        result = self.observe_nodes(nodes, limit=2)
        self.assertEqual(len(result['summary']['targets']), 2)
        self.assertEqual(len(result['summary']['texts']), 2)
        self.assertTrue(result['summary']['output_truncated']['targets'])
        self.assertLessEqual(self.lib.find_widgets.call_count, 3)
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'nodes': []}], 'truncated': True})
        result = self.input.observe_ui(scope='pie', summary=True)
        self.assertTrue(result['truncated'])
        self.assertTrue(result['summary']['scan_truncated'])

    def test_repeated_widgets_are_grouped_by_enclosing_widget(self):
        nodes = []
        for parent in ('Left', 'Right'):
            nodes.append(dict(type='SObjectWidget', name=parent, **{'class': 'Panel'}, rect=[0, 0, 100, 100], d=0))
            nodes.extend(dict(type='SObjectWidget', name=parent + str(i), **{'class': 'Row'}, rect=[0, 0, 10, 10], d=1) for i in range(2))
        summary = self.observe_nodes(nodes)['summary']
        self.assertEqual(len(summary['repeated_widgets']), 3)
        rows = [n for n in summary['repeated_widgets'] if n['class'] == 'Row']
        self.assertEqual([n['observed_count'] for n in rows], [2, 2])
        self.assertNotEqual(rows[0]['parent'], rows[1]['parent'])

    def test_default_target_does_not_leak_full_text(self):
        text = 'x' * 200
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'nodes': [dict(type='SButton', name='Next', text='x' * 80 + '...',
                                                                                    text_full=text, rect=[0, 0, 10, 10], interactable=True)]}]})
        result = self.input.observe_ui(scope='pie')
        self.assertNotIn(text, json.dumps(result))
        self.assertNotIn('text=', result['nodes'][0]['target'])
        self.assertNotIn('summary', result)
        self.assertEqual(self.lib.dump_slate_tree.call_args.args[5], 80)

    def test_long_text_targets_are_not_merged_by_short_locator(self):
        nodes = [dict(type='SButton', name='Choice', text='x' * 80 + '...', text_full='x' * 200 + suffix,
                      rect=[10, 10, 20, 20], d=1, interactable=True) for suffix in ('one', 'two')]
        summary = self.observe_nodes(nodes)['summary']
        self.assertEqual(len(summary['targets']), 2)
        self.assertEqual([n['observed_count'] for n in summary['targets']], [1, 1])
        self.assertEqual(summary['targets'][0]['locator'], summary['targets'][1]['locator'])
        self.assertNotIn('x' * 200, json.dumps(summary))

    def test_shallow_same_class_roots_remain_separate_candidates(self):
        nodes = [dict(type='SObjectWidget', name=name, **{'class': 'Panel'}, rect=[0, 0, 100, 100], d=1)
                 for name in ('Left', 'Right')]
        summary = self.observe_nodes(nodes)['summary']
        self.assertEqual([n['name'] for n in summary['widget_roots']], ['Left', 'Right'])

    def test_summary_scan_recovery_does_not_suggest_raising_output_limit(self):
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'nodes': []}], 'truncated': True})
        result = self.input.observe_ui(scope='pie', summary=True)
        self.assertIn('does not expand the scan', result['recovery'])

    def test_full_text_uses_own_node_without_second_dump(self):
        for text in ('', 'x' * 80, 'x' * 81, 'line one\n中文内容' * 1000):
            with self.subTest(length=len(text)):
                node = dict(type='STextBlock', name='Title', text=text[:80], text_full=text, rect=[0, 0, 10, 10])
                self.lib.find_widgets.return_value = json.dumps([node])
                result = self.input.text_snapshot('name=Title')
                self.assertEqual(result['text'], text)
                self.assertEqual(result['length'], len(text))
                self.assertFalse(result['source_markup'])
        self.lib.dump_slate_tree.assert_not_called()

    def test_full_rich_text_preserves_source_markup(self):
        text = '<Style>Long description</>\n' * 100
        self.lib.find_widgets.return_value = json.dumps([dict(type='SRichTextBlock', text_full=text, rect=[0, 0, 10, 10])])
        result = self.input.text_snapshot('type=SRichTextBlock')
        self.assertTrue(result['source_markup'])
        self.assertEqual(result['text'], text)

    def test_full_text_refuses_missing_ambiguous_and_container_targets(self):
        for nodes in ([], [dict(type='STextBlock'), dict(type='STextBlock')], [dict(type='SObjectWidget')]):
            with self.subTest(nodes=nodes):
                self.lib.find_widgets.return_value = json.dumps(nodes)
                with self.assertRaises(RuntimeError):
                    self.input.text_snapshot('name=Text')
        self.lib.dump_slate_tree.assert_not_called()

    def test_full_text_explicit_index_and_invalid_indices(self):
        self.lib.find_widgets.return_value = json.dumps([dict(type='STextBlock', text='first'), dict(type='STextBlock', text='second')])
        self.assertEqual(self.input.text_snapshot('type=STextBlock', index=1)['text'], 'second')
        for index in (-1, 2, True, '1'):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.input.text_snapshot('type=STextBlock', index=index)

    def test_read_text_keeps_editable_descendant_behavior(self):
        self.lib.find_widgets.return_value = json.dumps([dict(type='SObjectWidget', text='label')])
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'nodes': [dict(type='SEditableText', text='input')]}]})
        self.assertEqual(self.input.read_text('name=Container'), 'input')


class DiscoveryCommandTests(unittest.TestCase):
    def test_ui_summary_calls_observation_once(self):
        module = SimpleNamespace(LIB=mock.Mock(), parse=json.loads, describe=str, MAX_HOLD=30,
                                 observe_ui=mock.Mock(return_value={'kind': 'ui', 'status': 'observed'}))
        source = (Path(ue_cli.ACTIONS_DIR) / 'ui.py').read_text(encoding='utf-8')
        with mock.patch.dict(sys.modules, ue_input=module), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source, 'actions/ui.py', 'exec'), {'ARGS': ['observe'], 'OPTS': {'summary': True}})
        module.observe_ui.assert_called_once()
        self.assertTrue(module.observe_ui.call_args.kwargs['summary'])

    def test_ui_text_returns_complete_structured_payload(self):
        payload = {'kind': 'text', 'text': 'x' * 10000}
        module = SimpleNamespace(LIB=mock.Mock(), parse=json.loads, describe=str, MAX_HOLD=30,
                                 text_snapshot=mock.Mock(return_value=payload))
        source = (Path(ue_cli.ACTIONS_DIR) / 'ui.py').read_text(encoding='utf-8')
        output = io.StringIO()
        with mock.patch.dict(sys.modules, ue_input=module), contextlib.redirect_stdout(output):
            exec(compile(source, 'actions/ui.py', 'exec'), {'ARGS': ['text', 'name=Text'], 'OPTS': {}})
        self.assertEqual(json.loads(output.getvalue()), payload)
        module.text_snapshot.assert_called_once_with('name=Text', '', None)
        presented = ue_cli._present_result({'status': 'ok', 'output': output.getvalue()})
        self.assertEqual(json.loads(presented['output']), payload)
        self.assertNotIn('output_truncated', presented)

    def test_large_ui_json_is_not_sliced_but_plain_output_still_is(self):
        payload = {'kind': 'ui', 'nodes': [{'text': 'x' * 10000}]}
        result = ue_cli._present_result({'output': json.dumps(payload)})
        self.assertEqual(json.loads(result['output']), payload)
        self.assertTrue(ue_cli._present_result({'output': 'x' * 10000})['output_truncated'])

    def test_unicode_separators_preserved_in_large_json_with_diagnostics(self):
        for separator in ('\u0085', '\u2028', '\u2029'):
            with self.subTest(separator=repr(separator)):
                payload = {'kind': 'text', 'text': ('A' + separator + 'B') * 4000}
                raw = 'start\n' + json.dumps(payload, ensure_ascii=False) + '\n[input-request] 1\n' + 'log' * 4000
                result = ue_cli._present_result({'status': 'ok', 'output': raw})
                records = [line for line in result['output'].split('\n') if line.startswith('{')]
                self.assertEqual(len(records), 1)
                self.assertEqual(json.loads(records[0]), payload)
                self.assertTrue(result['output_truncated'])

    def test_ui_summary_without_observation_is_rejected_before_connect(self):
        with mock.patch.object(sys, 'argv', ['ue_cli.py', 'exec', 'print(1)', '--ui-summary']), \
                mock.patch.object(ue_cli, '_run') as run, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                ue_cli.main()
            self.assertEqual(error.exception.code, 2)
            run.assert_not_called()

    def test_post_action_summary_is_passed_without_replaying(self):
        args = SimpleNamespace(observe_ui=True, ui_scope='window', ui_window='', ui_root='', ui_instance=None,
                               ui_depth=6, ui_limit=80, ui_summary=True, observe=None, screenshot=None)
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': repr(json.dumps({'kind': 'ui', 'scope': 'window', 'status': 'observed'}))}
        self.assertEqual(ue_cli._observe_after(bridge, {'status': 'ok'}, args)['status'], 'ok')
        self.assertIn('summary=True', bridge.evaluate.call_args.args[0])
        bridge.execute.assert_not_called()


if __name__ == '__main__':
    unittest.main()
