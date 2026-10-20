"""
批量移动/改名资产与引用检查（rename_asset 自动修引用，引用方会被编辑器自动签出）。

  exec --action asset_move check <源> <目标> [<源> <目标> ...]          只读：源/目标的存在性与类名、源的被引用方，移动前先看
  exec --action asset_move move <源> <目标> [...] [--save-referencers]  批量移动；跳过缺失的源与已存在的目标
  exec --action asset_move redirectors <目录> [--recursive]            列出改名后旧路径残留的 ObjectRedirector

- 改名/移动被其它资产引用时，编辑器会自动签出并改写引用方，过程可能卡 1~3 分钟：加 --timeout 300，返回 Timeout 也不要重发，
  用 exec "print(1)" 探测恢复后看 move 输出核对结果。
- move 后旧路径只剩 ObjectRedirector；确认旧路径无引用后本地清理（P4：p4 revert + p4 delete；被编辑器占用删不掉时关编辑器再删）。
- 目标目录先建好（make_directory）；改名的项目约束（如脚本绑定的同名冲突）见项目参考资料。
"""
import unreal

_REG = unreal.AssetRegistryHelpers.get_asset_registry()
_DEP = unreal.AssetRegistryDependencyOptions(True, True, True, True, True)


def _usage(message):
    raise RuntimeError(message + '\n\n' + __doc__)


def _pairs(start):
    rest = ARGS[start:]
    if not rest or len(rest) % 2:
        _usage('pass source/target asset paths in pairs')
    return list(zip(rest[0::2], rest[1::2]))


def _class_of(path):
    data = unreal.EditorAssetLibrary.find_asset_data(path)
    if data is None or not data.is_valid():
        return None
    return str(data.asset_class_path.asset_name)


def _referencers(path):
    return sorted(str(r) for r in (_REG.get_referencers(path, _DEP) or []))


def _report(path, label):
    cls = _class_of(path)
    print('%s %s exists=%s%s' % (label, path, bool(cls), ' class=' + cls if cls else ''))
    if cls:
        refs = _referencers(path)
        print('  referencers: %s' % (', '.join(refs) if refs else '(none)'))


cmd = ARGS[0] if ARGS else ''
if cmd == 'check':
    for src, dst in _pairs(1):
        _report(src, 'SRC')
        _report(dst, 'DST')

elif cmd == 'move':
    moved = []
    for src, dst in _pairs(1):
        if not unreal.EditorAssetLibrary.does_asset_exist(src):
            print('MISSING ' + src)
            continue
        if unreal.EditorAssetLibrary.does_asset_exist(dst):
            print('EXISTS ' + dst + ' (skip)')
            continue
        ok = unreal.EditorAssetLibrary.rename_asset(src, dst)
        print(('OK ' if ok else 'FAIL ') + src + ' -> ' + dst)
        if not ok:
            continue
        moved.append(dst)
        print('  save %s: %s' % (dst, unreal.EditorAssetLibrary.save_asset(dst, only_if_is_dirty=False)))
        if unreal.EditorAssetLibrary.does_asset_exist(src):
            print('  redirector left at %s (check references, then p4 revert + p4 delete)' % src)
    refs = sorted({r for dst in moved for r in _referencers(dst)})
    print('referencers to save: %s' % (', '.join(refs) if refs else '(none)'))
    if OPTS.get('save_referencers'):
        for ref in refs:
            print('  save %s: %s' % (ref, unreal.EditorAssetLibrary.save_asset(ref, only_if_is_dirty=False)))

elif cmd == 'redirectors':
    if len(ARGS) < 2:
        _usage('redirectors needs <目录>')
    found = []
    for path in unreal.EditorAssetLibrary.list_assets(ARGS[1], recursive=bool(OPTS.get('recursive')), include_folder=False):
        package = str(path).split('.')[0]
        if package not in found and _class_of(str(path)) == 'ObjectRedirector':
            found.append(package)
    print('\n'.join(found) if found else '(none)')

else:
    _usage('unknown or missing command: ' + repr(cmd))
