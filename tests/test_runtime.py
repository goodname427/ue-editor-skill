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
sys.path.insert(0, str(ROOT / 'skills' / 'ue-editor' / 'scripts' / 'lib'))
import ue_cli


class FakeObject:
    def __init__(self, name, **properties):
        self.name = name
        self.properties = properties

    def get_path_name(self):
        return '/Runtime/' + self.name

    def get_name(self):
        return self.name

    def get_class(self):
        return SimpleNamespace(get_name=lambda: type(self).__name__)

    def get_editor_property(self, name):
        if name not in self.properties:
            raise ValueError('Property not reflected: ' + name)
        return self.properties[name]


class FakeEntry(FakeObject):
    def __init__(self, name, item):
        super().__init__(name)
        self.item = item

    def get_list_item_object_internal(self):
        return self.item


class FakeList(FakeObject):
    def __init__(self, items, entries=(), selected=None):
        super().__init__('List')
        self.items = items
        self.entries = entries
        self.selected = selected
        self.read_indices = []

    def get_num_items(self):
        return len(self.items)

    def get_item_at(self, index):
        self.read_indices.append(index)
        return self.items[index]

    def get_displayed_entry_widgets(self):
        return self.entries

    def bp_get_selected_item(self):
        return self.selected

    def get_index_for_item(self, item):
        return self.items.index(item) if item in self.items else -1


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.unreal = SimpleNamespace(Object=FakeObject, find_object=mock.Mock())
        self.find = mock.Mock()
        path = ROOT / 'skills' / 'ue-editor' / 'scripts' / 'lib' / 'ue_runtime.py'
        with mock.patch.dict(sys.modules, unreal=self.unreal, ue_input=SimpleNamespace(find=self.find)):
            spec = importlib.util.spec_from_file_location('runtime_under_test', path)
            self.runtime = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.runtime)
        self.getter_guard = self.runtime._native_getter
        patch = mock.patch.object(self.runtime, '_native_getter', side_effect=lambda obj, name: getattr(obj, name, None) if callable(getattr(obj, name, None)) else None)
        patch.start()
        self.addCleanup(patch.stop)

    def test_resolves_metadata_path_without_loading_or_guessing(self):
        obj = FakeObject('Button')
        self.find.return_value = [{'object_path': obj.get_path_name()}]
        self.unreal.find_object.return_value = obj
        self.assertIs(self.runtime.resolve(locator='name=Button'), obj)
        self.unreal.find_object.assert_called_once_with(None, '/Runtime/Button')

    def test_missing_or_ambiguous_locator_never_resolves_an_object(self):
        for nodes in ([], [{}, {}], [{}]):
            with self.subTest(nodes=nodes):
                self.find.return_value = nodes
                with self.assertRaises(RuntimeError):
                    self.runtime.resolve(locator='name=Button')
        self.unreal.find_object.assert_not_called()

    def test_path_and_locator_arguments_are_exclusive(self):
        for arguments in ({}, {'path': '/Runtime/A', 'locator': 'name=A'}, {'path': '/Runtime/A', 'index': 0}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.runtime.resolve(**arguments)

    def test_explicit_index_and_destroyed_object_are_checked(self):
        self.find.return_value = [{'object_path': '/Runtime/A'}, {'object_path': '/Runtime/B'}]
        self.unreal.find_object.return_value = None
        with self.assertRaises(RuntimeError):
            self.runtime.resolve(locator='name=A', index=1)
        self.unreal.find_object.assert_called_once_with(None, '/Runtime/B')
        for index in (-1, 2, True):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.runtime.resolve(locator='name=A', index=index)

    def test_only_requested_reflected_properties_are_read(self):
        obj = FakeObject('Item', value=7, owner=FakeObject('Owner'), complex=[1, 2])
        self.unreal.find_object.return_value = obj
        result = self.runtime.object_snapshot(path='/Runtime/Item', fields=('value', 'owner', 'missing', 'complex'))
        self.assertEqual(result['properties']['value'], 7)
        self.assertEqual(result['properties']['owner']['path'], '/Runtime/Owner')
        self.assertEqual(set(result['property_errors']), {'missing', 'complex'})
        self.assertNotIn('missing', result['properties'])

    def test_nonfinite_properties_are_errors_not_invalid_json(self):
        self.unreal.find_object.return_value = FakeObject('Item', value=float('nan'))
        result = self.runtime.object_snapshot(path='/Runtime/Item', fields=('value',))
        self.assertNotIn('value', result['properties'])
        self.assertIn('value', result['property_errors'])
        json.dumps(result, allow_nan=False)

    def test_native_guard_refuses_python_business_methods(self):
        self.unreal.Widget = FakeObject
        obj = FakeList([])
        self.assertIsNone(self.getter_guard(obj, 'get_num_items'))
        obj.get_num_items = mock.Mock()
        self.assertIsNone(self.getter_guard(obj, 'get_num_items'))
        obj.get_num_items.assert_not_called()

    def test_entry_scan_is_bounded_and_reports_incomplete_mapping(self):
        items = [FakeObject('Item%d' % i) for i in range(20)]
        entries = [FakeEntry('Entry%d' % i, item) for i, item in enumerate(items)]
        entries[-1].get_list_item_object_internal = mock.Mock(return_value=items[-1])
        self.unreal.find_object.return_value = FakeList(items, entries)
        result = self.runtime.list_snapshot(path='/Runtime/List', offset=19, limit=1)
        self.assertEqual(result['generated_entry_count'], 20)
        self.assertFalse(result['entry_scan_complete'])
        self.assertFalse(result['items'][0]['entry_mapping_complete'])
        self.assertEqual(result['items'][0]['entries'], [])
        entries[-1].get_list_item_object_internal.assert_not_called()

    def test_unmapped_entries_do_not_claim_no_entry(self):
        obj = FakeList([FakeObject('Item')], [FakeObject('UnknownEntry')])
        self.unreal.find_object.return_value = obj
        result = self.runtime.list_snapshot(path='/Runtime/List')
        self.assertFalse(result['entry_mapping_supported'])
        self.assertFalse(result['items'][0]['entry_mapping_complete'])

    def test_fields_and_sample_bounds_are_validated_before_resolution(self):
        for arguments in ({'fields': 'value'}, {'fields': ('',)}, {'fields': tuple(str(i) for i in range(17))},
                          {'offset': -1}, {'limit': 0}, {'limit': 101}, {'offset': True}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.runtime.list_snapshot(path='/Runtime/List', **arguments)
        self.unreal.find_object.assert_not_called()

    def test_logical_count_differs_from_generated_entries_and_sample(self):
        items = [FakeObject('Item%d' % i, value=i) for i in range(100)]
        entries = [FakeEntry('Entry0', items[20]), FakeEntry('Entry1', items[21])]
        obj = FakeList(items, entries, items[21])
        self.unreal.find_object.return_value = obj
        result = self.runtime.list_snapshot(path='/Runtime/List', offset=20, limit=3, fields=('value',))
        self.assertEqual(result['logical_item_count'], 100)
        self.assertEqual(result['generated_entry_count'], 2)
        self.assertEqual(result['selected_index'], 21)
        self.assertEqual(obj.read_indices, [20, 21, 22])
        self.assertEqual(result['items'][0]['entries'][0]['name'], 'Entry0')
        self.assertEqual(result['items'][2]['entries'], [])
        self.assertTrue(result['items_truncated'])
        self.assertEqual([i['properties']['value'] for i in result['items']], [20, 21, 22])

    def test_null_item_is_reported_not_dropped(self):
        self.unreal.find_object.return_value = FakeList([None, FakeObject('Item')])
        result = self.runtime.list_snapshot(path='/Runtime/List')
        self.assertEqual(result['logical_item_count'], 2)
        self.assertIsNone(result['items'][0]['item'])
        self.assertFalse(result['items_truncated'])

    def test_empty_and_unsupported_lists_are_distinct(self):
        self.unreal.find_object.return_value = FakeList([])
        self.assertEqual(self.runtime.list_snapshot(path='/Runtime/List')['logical_item_count'], 0)
        self.unreal.find_object.return_value = FakeObject('Panel')
        with self.assertRaises(RuntimeError):
            self.runtime.list_snapshot(path='/Runtime/Panel')

    def test_native_alternate_count_getter(self):
        obj = SimpleNamespace(get_path_name=lambda: '/Runtime/List', get_name=lambda: 'List',
                              get_class=lambda: SimpleNamespace(get_name=lambda: 'CustomList'),
                              get_item_count=lambda: 0, get_item_at=lambda index: None, get_displayed_entry_widgets=lambda: [])
        self.unreal.find_object.return_value = obj
        result = self.runtime.list_snapshot(path='/Runtime/List')
        self.assertEqual(result['count_getter'], 'get_item_count')
        self.assertIsNone(result['selected_index'])

    def test_object_list_json_records_are_not_sliced(self):
        for kind in ('object', 'list'):
            payload = {'kind': kind, 'value': 'x' * 10000}
            result = ue_cli._present_result({'output': json.dumps(payload)})
            self.assertEqual(json.loads(result['output']), payload)

    def test_ui_list_calls_only_snapshot_with_explicit_options(self):
        snapshot = mock.Mock(return_value={'kind': 'list'})
        source = (Path(ue_cli.ACTIONS_DIR) / 'ui.py').read_text(encoding='utf-8')
        module = SimpleNamespace(LIB=mock.Mock(), parse=json.loads, describe=str, MAX_HOLD=30)
        runtime = SimpleNamespace(list_snapshot=snapshot, object_snapshot=mock.Mock())
        with mock.patch.dict(sys.modules, ue_input=module, ue_runtime=runtime), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(source, 'actions/ui.py', 'exec'), {'ARGS': ['list', 'name=List'], 'OPTS': {'fields': 'value', 'offset': '5', 'limit': '2'}})
        snapshot.assert_called_once_with(path='', locator='name=List', window='', index=None, fields=('value',), offset=5, limit=2)


if __name__ == '__main__':
    unittest.main()
