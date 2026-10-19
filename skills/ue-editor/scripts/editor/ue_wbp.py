"""
Widget 蓝图的读写组合：C++ 的 AgentWidgetBlueprintInfoFunctionLib 只给原子能力，这里拼出常用视图与操作。
wbp_edit Lib 与项目脚本都 import 这里，不要在别处再拼一遍（ue_cli 每次执行前把本目录加进 sys.path）。

  import ue_wbp
  ue_wbp.widgets(path)            控件平铺列表（C++ 原子）      ue_wbp.tree(path)           嵌套树
  ue_wbp.root(path)               根控件名                       ue_wbp.variables(path)      勾了"是变量"的控件
  ue_wbp.props(path, name, slot=False)   属性 {名: UE 文本}     ue_wbp.set_prop / set_props 改属性（写后回读）
  ue_wbp.members(path)            "我的蓝图"成员变量              ue_wbp.animations / bindings / named_slots
  ue_wbp.graphs(path)             图表列表                       ue_wbp.nodes(path, graph, detailed) / node(path, graph, guid)
  ue_wbp.events(path)             事件图里的引擎事件与自定义事件   ue_wbp.functions(path, keyword) / function(path, name)
  ue_wbp.info(path)               概览                           ue_wbp.inheritance(path)    继承链（到 UserWidget）
  ue_wbp.list_dir(dir, recursive) 目录下的 WBP
  ue_wbp.rename_widget / add_function / remove_function / rename_function / add_param / set_description

所有写操作只改内存，编译保存用 wbp_edit save（或 BlueprintEditorLibrary.compile_blueprint + EditorAssetLibrary.save_asset）。
"""
import unreal
from ue_common import parse, require

LIB = require('AgentWidgetBlueprintInfoFunctionLib')

# 参数类型名 → BlueprintEditorLibrary.get_basic_type_by_name 的类别名（它对未知名字静默返回 int，所以先在这里校验）
_BASIC = {'bool': 'bool', 'byte': 'byte', 'int': 'int', 'int64': 'int64', 'float': 'real', 'real': 'real', 'double': 'real',
          'name': 'name', 'string': 'string', 'text': 'text'}


# ---------- 控件 ----------

def widgets(path):
    return parse(LIB.get_widgets(path))


def root(path):
    for w in widgets(path):
        if not w['parent']:
            return w['name']
    raise RuntimeError('no root widget: ' + path)


def tree(path):
    """嵌套树：每个节点 {name, type, is_variable, visibility, children}，按 child_index 排序。"""
    items = widgets(path)
    nodes = {w['name']: dict(w, children=[]) for w in items}
    roots = []
    for w in sorted(items, key=lambda w: w['child_index']):
        node = nodes[w['name']]
        (nodes[w['parent']]['children'] if w['parent'] in nodes else roots).append(node)
    for node in nodes.values():
        node.pop('parent')
        node.pop('child_index')
    return roots[0] if len(roots) == 1 else roots


def variables(path):
    return [{'name': w['name'], 'type': w['type']} for w in widgets(path) if w['is_variable']]


def props(path, name, slot=False):
    """控件（slot=True 时为它的插槽）全部可编辑属性 {名: UE 文本}，外加 '__type__' 为控件类或插槽类。"""
    data = parse(LIB.get_widget_properties(path, name, slot))
    result = {p['name']: p['value'] for p in data['properties']}
    result['__type__'] = data['type']
    return result


def set_prop(path, name, prop, value, slot=False):
    """用 UE 文本格式写一个属性，返回写入后回读的文本；解析失败抛异常。"""
    return parse(LIB.set_widget_property(path, name, prop, str(value), slot))['value']


def set_props(path, name, values, slot=False):
    """依次写多个属性，返回 {属性: 回读值}；任一失败立即抛异常，前面写过的保持写入。"""
    return {prop: set_prop(path, name, prop, value, slot) for prop, value in values.items()}


def is_variable(path, name):
    for w in widgets(path):
        if w['name'] == name:
            return w['is_variable']
    raise RuntimeError('widget not found: ' + name)


def rename_widget(path, old, new):
    return parse(LIB.rename_child_widget(path, old, new))['message']


# ---------- 蓝图数据 ----------

def members(path):
    return parse(LIB.get_blueprint_variables(path))


def animations(path):
    return parse(LIB.get_widget_animations(path))


def bindings(path):
    return parse(LIB.get_property_bindings(path))


def named_slots(path):
    """本蓝图的 NamedSlot 控件（content 为放进去的子控件）+ 父类 NamedSlot 在这里填入的内容（source=binding）。"""
    items = widgets(path)
    result = []
    for w in items:
        if w['type'] == 'NamedSlot':
            content = next((c for c in items if c['parent'] == w['name']), None)
            result.append({'name': w['name'], 'source': 'widget',
                           'content_name': content['name'] if content else '', 'content_type': content['type'] if content else ''})
    result.extend(dict(b, source='binding') for b in parse(LIB.get_named_slot_bindings(path)))
    return result


# ---------- 图表与函数 ----------

def graphs(path):
    return parse(LIB.get_all_graphs(path))


def nodes(path, graph, detailed=False):
    return parse(LIB.get_graph_nodes(path, graph, detailed))


def node(path, graph, guid):
    for n in nodes(path, graph, True):
        if n['guid'].lower() == guid.lower():
            return n
    raise RuntimeError('node not found in %s: %s' % (graph, guid))


def events(path):
    """事件图里的事件节点：{name（事件名）, type: CustomEvent|EngineEvent, graph, title}。"""
    result = []
    for g in graphs(path):
        if g['type'] != 'EventGraph':
            continue
        for n in nodes(path, g['name']):
            if 'function_name' in n:
                result.append({'name': n['function_name'], 'type': 'CustomEvent' if n['node_class'] == 'K2Node_CustomEvent' else 'EngineEvent',
                               'graph': g['name'], 'title': n['title']})
    return result


def functions(path, keyword=''):
    """函数签名列表；keyword 非空时按函数名子串过滤（不区分大小写）。"""
    items = parse(LIB.get_blueprint_functions(path))
    return [f for f in items if keyword.lower() in f['name'].lower()] if keyword else items


def function(path, name):
    for f in functions(path):
        if f['name'] == name:
            return f
    raise RuntimeError('function not found: ' + name)


def _blueprint(path):
    bp = unreal.EditorAssetLibrary.load_asset(path)
    if not isinstance(bp, unreal.WidgetBlueprint):
        raise RuntimeError('not a WidgetBlueprint: ' + path)
    return bp


def add_function(path, name):
    if any(g['name'] == name for g in graphs(path)):
        raise RuntimeError('graph name already exists: ' + name)
    graph = unreal.BlueprintEditorLibrary.add_function_graph(_blueprint(path), name)
    if graph is None:
        raise RuntimeError('failed to add function: ' + name)
    return graph.get_name()


def remove_function(path, name):
    function(path, name)
    unreal.BlueprintEditorLibrary.remove_function_graph(_blueprint(path), name)


def rename_function(path, old, new):
    function(path, old)
    if any(g['name'] == new for g in graphs(path)):
        raise RuntimeError('graph name already exists: ' + new)
    graph = unreal.BlueprintEditorLibrary.find_graph(_blueprint(path), old)
    unreal.BlueprintEditorLibrary.rename_graph(graph, new)
    if function(path, new)['name'] != new:
        raise RuntimeError('rename did not take effect: %s -> %s' % (old, new))


def pin_type(text):
    """参数类型：bool/byte/int/int64/float/name/string/text，或 object:<类路径>、class:<类路径>、struct:<结构体路径>；末尾加 [] 为数组。"""
    text = text.strip()
    is_array = text.endswith('[]')
    text = text[:-2] if is_array else text
    kind, _, target = text.partition(':')
    lib = unreal.BlueprintEditorLibrary
    if kind.lower() in _BASIC and not target:
        result = lib.get_basic_type_by_name(_BASIC[kind.lower()])
    elif kind in ('object', 'class'):
        cls = unreal.load_class(None, target)
        if cls is None:
            raise RuntimeError('class not found: ' + target)
        result = lib.get_object_reference_type(cls) if kind == 'object' else lib.get_class_reference_type(cls)
    elif kind == 'struct':
        struct = unreal.load_object(None, target)
        if not isinstance(struct, unreal.ScriptStruct):
            raise RuntimeError('struct not found: ' + target)
        result = lib.get_struct_type(struct)
    else:
        raise RuntimeError('unknown param type %r; use %s, object:/class:/struct:<path>, optional []' % (text, '/'.join(sorted(_BASIC))))
    return lib.get_array_type(result) if is_array else result


def add_param(path, func, name, type_text, output=False):
    return parse(LIB.add_function_param(path, func, name, pin_type(type_text), output))['param']


def set_description(path, func, text):
    parse(LIB.set_function_description(path, func, text))


# ---------- 资产层面 ----------

def _parent_class_path(asset_path):
    """资产注册表 ParentClass 标签，形如 /Script/CoreUObject.Class'/Game/UI/WBP_Base.WBP_Base_C' 或直接是类路径。"""
    tag = str(unreal.EditorAssetLibrary.find_asset_data(asset_path).get_tag_value('ParentClass') or '')
    return tag.split("'")[1] if "'" in tag else tag


def inheritance(path):
    """从本类到 UserWidget 的继承链：[{name, path, is_blueprint}]。
    蓝图层读资产注册表的 ParentClass 标签（Blueprint.ParentClass 和蓝图生成类的 static_class 都不对 Python 公开），到原生类后用 Python 类型的 __mro__。"""
    _blueprint(path)
    asset = path.split('.')[0]
    chain = [{'name': asset.rsplit('/', 1)[-1] + '_C', 'path': '%s.%s_C' % (asset, asset.rsplit('/', 1)[-1]), 'is_blueprint': True}]
    parent = _parent_class_path(asset)
    for _ in range(32):
        if not parent or parent.startswith('/Script/'):
            break
        chain.append({'name': parent.rsplit('.', 1)[-1], 'path': parent, 'is_blueprint': True})
        parent = _parent_class_path(parent.split('.')[0])
    native = getattr(unreal, parent.rsplit('.', 1)[-1], None) if parent else None
    for t in (native.__mro__ if isinstance(native, type) else ()):
        static = getattr(t, 'static_class', None)
        c = static() if static else None
        if c is None:
            continue
        chain.append({'name': c.get_name(), 'path': c.get_path_name(), 'is_blueprint': False})
        if t is unreal.UserWidget:
            break
    return chain


def list_dir(directory, recursive=True):
    """目录下的 Widget 蓝图（含子类资产）：[{name, path, package_path}]。"""
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath('/Script/UMGEditor', 'WidgetBlueprint')],
                          package_paths=[directory], recursive_paths=recursive, recursive_classes=True)
    assets = unreal.AssetRegistryHelpers.get_asset_registry().get_assets(flt)
    return [{'name': str(a.asset_name), 'path': '%s.%s' % (a.package_name, a.asset_name), 'package_path': str(a.package_path)} for a in assets]


def info(path):
    items = widgets(path)
    chain = inheritance(path)
    root_widget = next((w for w in items if not w['parent']), None)
    return {'name': path.rsplit('/', 1)[-1].split('.')[0], 'path': path,
            'parent_class': chain[1]['name'] if len(chain) > 1 else '',
            'widget_count': len(items), 'animation_count': len(animations(path)),
            'binding_count': len(bindings(path)), 'function_count': len(functions(path)),
            'root_widget_type': root_widget['type'] if root_widget else ''}
