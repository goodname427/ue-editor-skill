# 资产操作 API 参考

> 本文档收录 UE Editor Python API 中最常用的资产操作接口。

## EditorAssetLibrary

### does_asset_exist

```python
exists = unreal.EditorAssetLibrary.does_asset_exist(asset_path)
```

- **参数**: `asset_path` (`str`) — 资产路径，如 `/Game/Meshes/SM_Chair`
- **返回**: `bool`

### find_asset_data

```python
asset_data = unreal.EditorAssetLibrary.find_asset_data(asset_path)
```

- **参数**: `asset_path` (`str`)
- **返回**: `unreal.AssetData`

### load_asset

```python
asset = unreal.EditorAssetLibrary.load_asset(asset_path)
```

- **参数**: `asset_path` (`str`)
- **返回**: `unreal.Object`

```python
mesh = unreal.EditorAssetLibrary.load_asset('/Game/Meshes/SM_Chair')
```

### list_assets

```python
assets = unreal.EditorAssetLibrary.list_assets(directory_path, recursive=True, include_folder=False)
```

- **参数**:
  - `directory_path` (`str`) — 目录路径，如 `/Game/Meshes`
  - `recursive` (`bool`) — 是否递归子目录
  - `include_folder` (`bool`) — 是否包含文件夹
- **返回**: `list[str]` — 资产路径列表

```python
all_meshes = unreal.EditorAssetLibrary.list_assets('/Game/Meshes', recursive=True)
```

### duplicate_asset

```python
result = unreal.EditorAssetLibrary.duplicate_asset(source_asset_path, destination_asset_path)
```

- **参数**:
  - `source_asset_path` (`str`)
  - `destination_asset_path` (`str`)
- **返回**: `bool`

### delete_asset

```python
result = unreal.EditorAssetLibrary.delete_asset(asset_path)
```

- **参数**: `asset_path` (`str`)
- **返回**: `bool`

> ⚠️ 破坏性操作，使用前应向用户确认。

### rename_asset

```python
result = unreal.EditorAssetLibrary.rename_asset(source_asset_path, destination_asset_path)
```

- **参数**:
  - `source_asset_path` (`str`)
  - `destination_asset_path` (`str`)
- **返回**: `bool`
- **提示**: 批量移动、移动前查引用方、列旧路径残留的 ObjectRedirector 用 `exec --action asset_move check/move/redirectors`；手法与 P4 历史保留见 [widget_blueprint_edit.md](widget_blueprint_edit.md#移动或改名资产)。

### make_directory

```python
result = unreal.EditorAssetLibrary.make_directory(directory_path)
```

- **参数**: `directory_path` (`str`) — 如 `/Game/NewFolder`
- **返回**: `bool`

## AssetToolsHelpers / AssetTools

### import_asset_tasks

批量导入资产。

```python
task = unreal.AssetImportTask()
task.set_editor_property('filename', 'D:/Models/chair.fbx')
task.set_editor_property('destination_path', '/Game/Meshes')
task.set_editor_property('automated', True)
task.set_editor_property('save', True)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
```

### export_assets

```python
asset = unreal.EditorAssetLibrary.load_asset('/Game/Meshes/SM_Chair')
task = unreal.AssetExportTask()
task.set_editor_property('object', asset)
task.set_editor_property('filename', 'D:/Export/SM_Chair.fbx')
task.set_editor_property('automated', True)
unreal.Exporter.run_asset_export_tasks([task])
```

## AssetRegistry

### get_assets_by_path

```python
registry = unreal.AssetRegistryHelpers.get_asset_registry()
assets = registry.get_assets_by_path('/Game/Meshes', recursive=True)
```

- **返回**: `list[unreal.AssetData]`

### get_assets_by_class

```python
assets = registry.get_assets_by_class('StaticMesh')
```

- **返回**: `list[unreal.AssetData]`
