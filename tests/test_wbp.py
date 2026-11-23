import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class WidgetBlueprintTests(unittest.TestCase):
    def setUp(self):
        class WidgetBlueprint:
            def get_outer(self):
                return 'package'

        self.bp = WidgetBlueprint()
        self.unreal = SimpleNamespace(
            WidgetBlueprint=WidgetBlueprint,
            AgentWidgetBlueprintInfoFunctionLib=mock.Mock(),
            EditorAssetLibrary=mock.Mock(),
            load_asset=mock.Mock(return_value=self.bp),
            find_object=mock.Mock(),
            BlueprintEditorLibrary=mock.Mock(),
            EditorLoadingAndSavingUtils=mock.Mock())
        self.unreal.EditorAssetLibrary.load_asset.return_value = None
        self.unreal.EditorLoadingAndSavingUtils.save_packages.return_value = True
        path = ROOT / 'skills' / 'ue-editor' / 'scripts' / 'lib'
        modules = mock.patch.dict(sys.modules, unreal=self.unreal)
        modules.start()
        self.addCleanup(modules.stop)
        paths = mock.patch.object(sys, 'path', [str(path)] + sys.path)
        paths.start()
        self.addCleanup(paths.stop)
        sys.modules.pop('ue_common', None)
        spec = importlib.util.spec_from_file_location('wbp_under_test', path / 'ue_wbp.py')
        self.wbp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.wbp)

    def test_blueprint_loads_package_and_object_paths_without_editor_asset_library(self):
        for path in ('/Game/UI/WBP_Main', '/Game/UI/WBP_Main.WBP_Main'):
            self.assertIs(self.wbp._blueprint(path), self.bp)
            self.unreal.load_asset.assert_called_with(path)
        self.unreal.EditorAssetLibrary.load_asset.assert_not_called()

    def test_blueprint_rejects_missing_and_non_widget_assets(self):
        for asset in (None, object()):
            self.unreal.load_asset.return_value = asset
            with self.assertRaisesRegex(RuntimeError, 'not a WidgetBlueprint'):
                self.wbp._blueprint('/Game/UI/WBP_Main')

    def test_widget_tree_loads_blueprint_before_lookup(self):
        path = '/Game/UI/WBP_Main.WBP_Main'
        self.assertIs(self.wbp.widget_tree(path), self.unreal.find_object.return_value)
        self.unreal.load_asset.assert_called_once_with(path)
        self.unreal.find_object.assert_called_once_with(None, path + ':WidgetTree')
        self.unreal.EditorAssetLibrary.load_asset.assert_not_called()

    def test_save_compiles_and_saves_loaded_package(self):
        self.assertTrue(self.wbp.save('/Game/UI/WBP_Main'))
        self.unreal.BlueprintEditorLibrary.compile_blueprint.assert_called_once_with(self.bp)
        self.unreal.EditorLoadingAndSavingUtils.save_packages.assert_called_once_with(['package'], False)
        self.unreal.EditorAssetLibrary.save_asset.assert_not_called()

    def test_save_failure_is_not_reported_as_success(self):
        self.unreal.EditorLoadingAndSavingUtils.save_packages.return_value = False
        self.assertFalse(self.wbp.save('/Game/UI/WBP_Main'))

    def test_save_missing_asset_does_not_compile_or_save(self):
        self.unreal.load_asset.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'not a WidgetBlueprint'):
            self.wbp.save('/Game/UI/WBP_Main')
        self.unreal.BlueprintEditorLibrary.compile_blueprint.assert_not_called()
        self.unreal.EditorLoadingAndSavingUtils.save_packages.assert_not_called()

    def test_tree_empty_is_list_and_root_fails(self):
        with mock.patch.object(self.wbp, 'widgets', return_value=[]):
            self.assertEqual(self.wbp.tree('path'), [])
            with self.assertRaisesRegex(RuntimeError, 'no root widget'):
                self.wbp.root('path')

    def test_tree_single_root_is_dict_with_sorted_children(self):
        items = [{'name': 'Root', 'parent': '', 'child_index': -1},
                 {'name': 'Second', 'parent': 'Root', 'child_index': 1},
                 {'name': 'First', 'parent': 'Root', 'child_index': 0}]
        with mock.patch.object(self.wbp, 'widgets', return_value=items):
            tree = self.wbp.tree('path')
            self.assertIsInstance(tree, dict)
            self.assertEqual([node['name'] for node in tree['children']], ['First', 'Second'])
            self.assertEqual(self.wbp.root('path'), 'Root')

    def test_tree_multiple_roots_is_list_and_root_returns_first(self):
        items = [{'name': 'Canvas', 'parent': '', 'child_index': -1},
                 {'name': 'Content', 'parent': '', 'child_index': -1}]
        with mock.patch.object(self.wbp, 'widgets', return_value=items):
            self.assertEqual([node['name'] for node in self.wbp.tree('path')], ['Canvas', 'Content'])
            self.assertEqual(self.wbp.root('path'), 'Canvas')


if __name__ == '__main__':
    unittest.main()
