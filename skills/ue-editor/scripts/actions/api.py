"""
UE Python API 内省。

  exec --action api search <关键词>          按名称搜索类与方法（不区分大小写，最多 200 条；方法只列在定义它的类上）
  exec --action api methods <类名>           列出类的公开方法
  exec --action api help <类名> [方法名]      打印签名与 docstring
"""
import unreal

mode = ARGS[0] if ARGS else ''

if mode == 'search' and len(ARGS) > 1:
    keyword = ARGS[1].lower()
    results = []
    for name in dir(unreal):
        if name.startswith('_'):
            continue
        if keyword in name.lower():
            results.append(name)
        obj = getattr(unreal, name, None)
        # 只列类自身定义的成员，子类继承来的同名方法不重复列出
        if isinstance(obj, type):
            results.extend(name + '.' + m for m in vars(obj) if not m.startswith('_') and keyword in m.lower())
    print('\n'.join(results[:200]))
    if len(results) > 200:
        print('... 共 %d 条，只显示前 200 条，请换更具体的关键词' % len(results))
elif mode == 'methods' and len(ARGS) > 1:
    cls = getattr(unreal, ARGS[1], None)
    if cls is None:
        raise RuntimeError('Class not found: ' + ARGS[1])
    print('\n'.join(m for m in sorted(dir(cls)) if not m.startswith('_')))
elif mode == 'help' and len(ARGS) > 1:
    target = getattr(unreal, ARGS[1], None)
    if target is None:
        raise RuntimeError('Class not found: ' + ARGS[1])
    if len(ARGS) > 2:
        target = getattr(target, ARGS[2], None)
        if target is None:
            raise RuntimeError('Method not found: %s.%s' % (ARGS[1], ARGS[2]))
    print(target.__doc__ or '(no docstring)')
else:
    raise RuntimeError(__doc__)
