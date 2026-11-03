import contextlib
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import test_runtime as runtime_tests
import test_pie_observation as pie_tests
from lib import ue_projection

ROOT = Path(__file__).resolve().parents[1]


class SharedProjectionTests(unittest.TestCase):
    def test_plain_dictionary_paths_do_not_call_object_getters(self):
        class Business:
            @property
            def secret(self):
                raise AssertionError('getter invoked')
        with self.assertRaises(ue_projection.ProjectionError):
            ue_projection.dict_field({'object': Business()}, '/object/secret')
        self.assertEqual(ue_projection.dict_field({'a/b': {'x': [7]}}, '/a~1b/x/0'), 7)

    def test_shared_budget_and_truncation(self):
        row = ue_projection.new_record(0)
        row['fields']['/text'] = ue_projection.bounded_value('x' * 600)
        result = ue_projection.finish([row], ['/text'], 1, 0, 1, 'dict')
        self.assertFalse(result['complete'])
        self.assertTrue(result['records'][0]['fields']['/text']['value_truncated'])
        with self.assertRaises(ue_projection.ProjectionError):
            ue_projection.check_output({'data': 'x' * 70000})


class NodeAdapterTests(unittest.TestCase):
    setUp = runtime_tests.RuntimeTests.setUp

    def test_node_columns_and_reflection_share_identity_and_contract(self):
        obj = runtime_tests.FakeObject('Button', is_enabled=True)
        self.unreal.find_object.return_value = obj
        nodes = [{'name': 'Button', 'type': 'SButton', 'd': 2, 'window': 'Editor', 'query_only': True,
                  'object_path': obj.get_path_name(), 'text': 'ok'}] * 2
        result = self.runtime.project_nodes(nodes, columns=('text',), properties=('is_enabled',), indices=[4, 9])
        self.assertEqual([r['index'] for r in result['records']], [4, 9])
        self.assertEqual(result['fields'], ['/node/text', '/property/is_enabled'])
        self.assertTrue(result['complete'])
        self.assertTrue(result['records'][0]['identity']['query_only'])
        self.assertEqual(result['records'][0]['identity']['d'], 2)
        self.assertTrue(result['records'][0]['fields']['/property/is_enabled'])
        self.unreal.find_object.assert_called_once_with(None, '/Runtime/Button')
        ue_projection.validate_fields(result['fields'])

    def test_pure_slate_and_stale_sources_do_not_become_zero_properties(self):
        self.unreal.find_object.return_value = None
        result = self.runtime.project_nodes([{'type': 'SBorder'}, {'type': 'SButton', 'object_path': '/Runtime/Stale'}],
                                            properties=('is_enabled',))
        self.assertFalse(result['complete'])
        self.assertEqual(result['reflected_object_count'], 0)
        self.assertTrue(all('/property/is_enabled' in r['field_errors'] for r in result['records']))
        self.assertEqual(result['records'][0]['fields'], {})

    def test_column_selection_has_no_reflection_reads(self):
        result = self.runtime.project_nodes([{'name': 'Button', 'rect': [1, 2, 3, 4]}], columns=('name', 'rect'))
        self.assertTrue(result['complete'])
        self.assertEqual(result['records'][0]['fields']['/node/rect'], [1, 2, 3, 4])
        self.unreal.find_object.assert_not_called()

    def test_missing_columns_and_source_truncation_are_visible(self):
        result = self.runtime.project_nodes([{'name': 'A'}], columns=('text',), truncated=True)
        self.assertFalse(result['complete'])
        self.assertTrue(result['records_truncated'])
        self.assertIn('/node/text', result['records'][0]['field_errors'])

    def test_invalid_fields_before_object_resolution(self):
        for options in ({'columns': ('name', 'name')}, {'properties': ('',)}, {'columns': ('name',), 'limit': 501},
                        {'columns': ('name',), 'offset': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.runtime.project_nodes([{'object_path': '/Runtime/Item'}], **options)
        self.unreal.find_object.assert_not_called()


class UIActionTests(unittest.TestCase):
    def setUp(self):
        self.lib = mock.Mock()
        self.input = SimpleNamespace(LIB=self.lib, parse=json.loads, describe=lambda n, prefix='': prefix + n['type'],
                                     MAX_HOLD=30, fold_text_children=lambda n: n)
        self.runtime = SimpleNamespace(project_nodes=mock.Mock(return_value={'kind': 'projection', 'records': [], 'complete': True}))
        self.action = (ROOT / 'skills/ue-editor/scripts/actions/ui.py').read_text(encoding='utf-8')

    def run_ui(self, args, opts):
        output = io.StringIO()
        with mock.patch.dict(sys.modules, ue_input=self.input, ue_runtime=self.runtime, ue_projection=ue_projection), contextlib.redirect_stdout(output):
            exec(compile(self.action, 'ui.py', 'exec'), {'ARGS': args, 'OPTS': opts})
        return output.getvalue()

    def test_tree_keeps_depth_window_hidden_and_root_ambiguity(self):
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'title': 'Editor', 'rect': [0, 0, 100, 100],
                                                                       'nodes': [{'type': 'SBorder', 'd': 2}]}],
                                                           'root_match_count': 2, 'truncated': True, 'node_count': 1})
        result = json.loads(self.run_ui(['tree', 'type=SBorder'], {'columns': 'type', 'hidden': True}))
        self.assertTrue(result['query_only'])
        self.assertEqual(result['root_match_count'], 2)
        self.assertTrue(result['truncated'])
        nodes = self.runtime.project_nodes.call_args.args[0]
        self.assertEqual(nodes[0]['d'], 2)
        self.assertEqual(nodes[0]['window'], 'Editor')
        self.assertIn('recovery', result)

    def test_find_keeps_original_indices_after_row_filter(self):
        nodes = [{'type': 'SButton', 'window': 'Editor'}, {'type': 'SButton', 'window': 'Editor'}]
        self.lib.find_widgets.return_value = json.dumps(nodes)
        self.input.in_row = lambda matches, locator, window: [(1, matches[1])]
        result = json.loads(self.run_ui(['find', 'type=SButton'], {'columns': 'type', 'in_row_of': 'name=Row'}))
        self.assertEqual(result['match_count'], 2)
        self.assertEqual(self.runtime.project_nodes.call_args.args[5], [1])

    def test_observe_projects_only_after_successful_scope_selection(self):
        self.input.observe_ui = mock.Mock(return_value={'kind': 'ui', 'status': 'observed', 'nodes': [{'type': 'SBorder'}], 'truncated': False})
        result = json.loads(self.run_ui(['observe'], {'columns': 'type'}))
        self.assertEqual(result['nodes'], [])
        self.assertIn('projection', result)
        self.runtime.project_nodes.assert_called_once()

    def test_default_tree_is_text_without_property_reads(self):
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'title': 'Editor', 'rect': [0, 0, 100, 100], 'nodes': [{'type': 'SBorder', 'd': 0}]}]})
        self.assertIn('SBorder', self.run_ui(['tree'], {}))
        self.runtime.project_nodes.assert_not_called()

    def test_summary_and_projection_conflict_before_observation(self):
        self.input.observe_ui = mock.Mock()
        with self.assertRaises(RuntimeError):
            self.run_ui(['observe'], {'columns': 'type', 'summary': True})
        self.input.observe_ui.assert_not_called()


class ObserveMetadataTests(unittest.TestCase):
    def test_observe_retains_source_identity_for_projection(self):
        pie_tests.PieObservationTests.setUp(self)
        self.lib.dump_slate_tree.return_value = json.dumps({'windows': [{'title': 'Editor', 'nodes': [
            {'type': 'SBorder', 'd': 1, 'rect': [0, 0, 20, 20], 'pie_instance': 1, 'visible_path': True, 'geometry_valid': True}
        ]}]})
        result = self.input.observe_ui(scope='pie')
        self.assertEqual(result['nodes'][0]['window'], 'Editor')
        self.assertEqual(result['nodes'][0]['pie_instance'], 1)
        self.assertTrue(result['nodes'][0]['geometry_valid'])


if __name__ == '__main__':
    unittest.main()
