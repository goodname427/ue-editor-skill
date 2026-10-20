"""
打开资产编辑器（WBP 设计器、蓝图、材质等）。打开后渲染需要 1~2 秒，截图前先等待。

  exec --action open_asset <资产路径>...      如 /Game/UI/XXX/WBP_Foo
"""
import unreal

if not ARGS:
    raise RuntimeError(__doc__)
assets = []
for path in ARGS:
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if asset is None:
        raise RuntimeError('Asset not found: ' + path)
    assets.append(asset)
unreal.get_editor_subsystem(unreal.AssetEditorSubsystem).open_editor_for_assets(assets)
print('opened %d asset(s)' % len(assets))
