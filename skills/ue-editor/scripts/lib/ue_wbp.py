"""
Widget 蓝图的读写组合：C++ 的 AgentWidgetBlueprintInfoFunctionLib 只给原子能力，这里拼出常用视图与操作。
wbp_edit 入口与项目脚本都 import 这里，不要在别处再拼一遍（ue_cli 每次执行前把本目录加进 sys.path）。

  import ue_wbp
  ue_wbp.widgets(path)            控件平铺列表（C++ 原子）      ue_wbp.tree(path)           嵌套树
  ue_wbp.root(path)               根控件名                       ue_wbp.variables(path)      勾了"是变量"的控件
  ue_wbp.props(path, name, slot=False)   属性 {名: UE 文本}     ue_wbp.set_prop / set_props 改属性（写后回读）
  ue_wbp.rename_widget(path, old, new)   改名并同步引用          ue_wbp.widget(path, name)   控件对象
  ue_wbp.add_widget / replace_widget / remove_widget             增删换控件（插槽参数见 check_slot）
  ue_wbp.members(path)            "我的蓝图"成员变量              ue_wbp.animations / bindings / named_slots
  ue_wbp.graphs(path)             图表列表                       ue_wbp.nodes(path, graph, detailed) / node(path, graph, guid)
  ue_wbp.events(path)             事件图里的引擎事件与自定义事件   ue_wbp.functions(path, keyword) / function(path, name)
  ue_wbp.info(path)               概览                           ue_wbp.inheritance(path)    继承链（到 UserWidget）
  ue_wbp.list_dir(dir, recursive) 目录下的 WBP                   ue_wbp.save(path)           编译 + 保存
  ue_wbp.add_function / remove_function / rename_function / add_param / set_description

写操作只改内存，最后用 ue_wbp.save(path) 编译保存。
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


# ---------- 增删换控件（控件对象层，Python 直接操作 WidgetTree） ----------

_ATTACH = (('canvas', 'CanvasPanel', 'add_child_to_canvas'),
           ('hbox', 'HorizontalBox', 'add_child_to_horizontal_box'),
           ('vbox', 'VerticalBox', 'add_child_to_vertical_box'),
           ('overlay', 'Overlay', 'add_child_to_overlay'),
           ('content', 'ContentWidget', 'set_content'))
_HALIGN = {'left': 'H_ALIGN_LEFT', 'center': 'H_ALIGN_CENTER', 'right': 'H_ALIGN_RIGHT', 'fill': 'H_ALIGN_FILL'}
_VALIGN = {'top': 'V_ALIGN_TOP', 'center': 'V_ALIGN_CENTER', 'bottom': 'V_ALIGN_BOTTOM', 'fill': 'V_ALIGN_FILL'}
STYLE_PROPS = ('widget_style', 'font', 'item_style', 'scroll_bar_style', 'content_padding', 'foreground_color', 'max_list_height')
_SLOT_PROPS = ('layout', 'padding', 'size', 'horizontal_alignment', 'vertical_alignment', 'auto_size', 'z_order')


def _asset_name(path):
    return path.split('.')[0].rsplit('/', 1)[-1]


def widget_tree(path):
    """WidgetTree 对象；必须先 load_asset，find_object 才找得到。"""
    unreal.EditorAssetLibrary.load_asset(path.split('.')[0])
    tree = unreal.find_object(None, '%s.%s:WidgetTree' % (path.split('.')[0], _asset_name(path)))
    if tree is None:
        raise RuntimeError('not a WidgetBlueprint asset: ' + path)
    return tree


def widget(path, name):
    """控件对象。任意层级的控件都平铺挂在 WidgetTree 下，路径不带父控件名。"""
    tree = widget_tree(path)
    obj = unreal.find_object(None, '%s.%s' % (tree.get_path_name(), name))
    if obj is None:
        raise RuntimeError('widget not found: %s' % name)
    return obj


def widget_class(text):
    """UMG 类名（Button、TextBlock、项目类）或蓝图路径（/Game/.../WBP_Foo）→ 类。"""
    if text.startswith('/'):
        cls = unreal.EditorAssetLibrary.load_blueprint_class(text)
        if cls is None:
            raise RuntimeError('blueprint class not found: ' + text)
        return cls
    cls = getattr(unreal, text, None)
    if not isinstance(cls, type):
        raise RuntimeError('widget class not found: %s (use a UMG class name or a /Game blueprint path)' % text)
    return cls


def panel_kind(obj):
    """父控件类型 canvas / hbox / vbox / overlay / content 及挂子控件方法；不支持时为 (None, None)。"""
    for kind, cls_name, add in _ATTACH:
        cls = getattr(unreal, cls_name, None)
        if cls is not None and isinstance(obj, cls):
            return kind, add
    return None, None


def check_slot(slot):
    """校验插槽参数并转成引擎值，在改资产之前调用，参数不合法时什么都不会改。
    slot: {anchor: (minx, miny, maxx, maxy), offset: (l, t, r, b), align: (x, y), padding: (l, t, r, b),
           size: (值, 'fill'|'auto'), halign: left|center|right|fill, valign: top|center|bottom|fill}"""
    result = {}
    for key, count in (('anchor', 4), ('offset', 4), ('align', 2), ('padding', 4)):
        if key in slot:
            values = [float(v) for v in slot[key]]
            if len(values) != count:
                raise ValueError('%s needs %d numbers' % (key, count))
            result[key] = values
    if 'size' in slot:
        value, rule = slot['size']
        if rule not in ('fill', 'auto'):
            raise ValueError('size rule must be fill or auto')
        result['size'] = unreal.SlateChildSize(float(value), unreal.SlateSizeRule.FILL if rule == 'fill' else unreal.SlateSizeRule.AUTOMATIC)
    for key, names, enum in (('halign', _HALIGN, unreal.HorizontalAlignment), ('valign', _VALIGN, unreal.VerticalAlignment)):
        if key in slot:
            text = str(slot[key]).strip().lower()
            if text not in names:
                raise ValueError('%s must be one of: %s' % (key, ', '.join(sorted(names))))
            result[key] = getattr(enum, names[text])
    return result


def apply_slot(slot_obj, kind, slot):
    """把 check_slot 的结果写进插槽。CanvasPanel 槽位给了 anchor/offset/align 任一项就整体重设，没给的项按 0。"""
    if kind == 'canvas':
        if not any(key in slot for key in ('anchor', 'offset', 'align')):
            return
        a, o, al = slot.get('anchor', [0] * 4), slot.get('offset', [0] * 4), slot.get('align', [0] * 2)
        layout = unreal.AnchorData()
        layout.anchors = unreal.Anchors(minimum=unreal.Vector2D(a[0], a[1]), maximum=unreal.Vector2D(a[2], a[3]))
        layout.offsets = unreal.Margin(o[0], o[1], o[2], o[3])
        layout.alignment = unreal.Vector2D(al[0], al[1])
        slot_obj.set_layout(layout)
        return
    if 'padding' in slot:
        slot_obj.set_padding(unreal.Margin(*slot['padding']))
    if 'size' in slot:
        slot_obj.set_size(slot['size'])
    if 'halign' in slot:
        slot_obj.set_horizontal_alignment(slot['halign'])
    if 'valign' in slot:
        slot_obj.set_vertical_alignment(slot['valign'])


def capture_slot(obj):
    """把控件当前插槽读成普通值，控件移走后仍可用 restore_slot 写到新插槽。"""
    slot_obj = obj.slot
    data = {}
    if slot_obj is not None:
        for prop in _SLOT_PROPS:
            try:
                data[prop] = slot_obj.get_layout() if prop == 'layout' else slot_obj.get_editor_property(prop)
            except Exception:
                pass
    return data


def restore_slot(slot_obj, data):
    setters = {'layout': 'set_layout', 'padding': 'set_padding', 'size': 'set_size',
               'horizontal_alignment': 'set_horizontal_alignment', 'vertical_alignment': 'set_vertical_alignment'}
    for prop, value in data.items():
        try:
            if prop in setters:
                getattr(slot_obj, setters[prop])(value)
            else:
                slot_obj.set_editor_property(prop, value)
        except Exception:
            pass


def copy_props(target, source, names=STYLE_PROPS):
    """把两边都有的属性从 source 复制到 target，返回复制成功的属性名。"""
    copied = []
    for prop in names:
        try:
            value = source.get_editor_property(prop)
            target.get_editor_property(prop)
            target.set_editor_property(prop, value)
            copied.append(prop)
        except Exception:
            pass
    return copied


def _to_transient(obj, base):
    """移出 WidgetTree 放进 Transient。同名对象已在 Transient 时引擎重命名会直接 fatal，所以先找一个空着的名字。"""
    transient = unreal.find_object(None, '/Engine/Transient')
    name, n = base, 1
    while unreal.find_object(None, '/Engine/Transient.' + name) is not None:
        n += 1
        name = '%s_%d' % (base, n)
    obj.rename(name, transient)


def _create(path, cls_text, name):
    if name in {w['name'] for w in widgets(path)}:
        raise RuntimeError('widget name already exists: ' + name)
    return unreal.new_object(widget_class(cls_text), widget_tree(path), name)


def _finish_new(path, obj, text=None, text_name=None, text_font_from=None, copy_from=None, var=True):
    result = {'name': obj.get_name(), 'type': obj.get_class().get_name()}
    if text is not None:
        if not hasattr(obj, 'add_child'):
            raise RuntimeError('%s cannot hold a text child' % result['type'])
        label = unreal.new_object(unreal.TextBlock, widget_tree(path), text_name or ('Text_' + result['name'][4:] if result['name'].startswith('Btn_') else 'Text_' + result['name']))
        if text_font_from:
            copy_props(label, widget(path, text_font_from), ('font',))
        label.set_text(str(text))
        obj.add_child(label)
        result['text'] = label.get_name()
    if copy_from:
        result['copied'] = copy_props(obj, widget(path, copy_from))
    # 新建控件的 bIsVariable 默认值随类不同（Widget 基类 true，多数面板和 TextBlock 显式 false），要确定就显式写
    result['is_variable'] = set_prop(path, result['name'], 'bIsVariable', 'True' if var else 'False')
    return result


def add_widget(path, parent, name, cls_text, slot=None, var=True, text=None, text_name=None, text_font_from=None, copy_from=None, before=None, after=None):
    """在面板或空 ContentWidget 下新增控件；before/after 指定同父锚点，否则追加。slot 见 check_slot。"""
    values = check_slot(slot or {})
    parent_name = root(path) if parent == 'root' else parent
    parent_obj = widget(path, parent_name)
    kind, add = panel_kind(parent_obj)
    if kind is None:
        raise RuntimeError('parent is not a supported panel widget: %s (%s)' % (parent_name, parent_obj.get_class().get_name()))
    if before and after:
        raise ValueError('before and after are mutually exclusive')
    if kind == 'content' and parent_obj.get_content() is not None:
        raise RuntimeError('content parent already has a child; use replace_widget: ' + parent_name)
    anchor = widget(path, before or after) if before or after else None
    if anchor is not None and anchor.get_parent() != parent_obj:
        raise RuntimeError('insertion anchor must have the same parent')
    insert_index = parent_obj.get_child_index(anchor) + (1 if after else 0) if anchor else None
    obj = _create(path, cls_text, name)
    new_slot = getattr(parent_obj, add)(obj)
    if new_slot is None:
        raise RuntimeError('parent refused the new child: ' + parent_name)
    apply_slot(new_slot, kind, values)
    result = dict(_finish_new(path, obj, text, text_name, text_font_from, copy_from, var), parent=parent_name, kind=kind)
    if insert_index is not None:
        parse(LIB.shift_child(path, name, insert_index))
    return result


def insert_before(path, name, anchor):
    """将已有控件移到同父锚点前，保留插槽实例与属性。"""
    obj, target = widget(path, name), widget(path, anchor)
    parent = obj.get_parent()
    if parent is None or target.get_parent() != parent or obj == target:
        raise RuntimeError('child and anchor must be distinct siblings')
    index = parent.get_child_index(target) - (1 if parent.get_child_index(obj) < parent.get_child_index(target) else 0)
    return parse(LIB.shift_child(path, name, index))


def insert_after(path, name, anchor):
    """将已有控件移到同父锚点后，保留插槽实例与属性。"""
    obj, target = widget(path, name), widget(path, anchor)
    parent = obj.get_parent()
    if parent is None or target.get_parent() != parent or obj == target:
        raise RuntimeError('child and anchor must be distinct siblings')
    index = parent.get_child_index(target) + (0 if parent.get_child_index(obj) < parent.get_child_index(target) else 1)
    return parse(LIB.shift_child(path, name, index))


def replace_widget(path, old, cls_text, new_name=None, slot=None, var=None, text=None, text_name=None, text_font_from=None, copy_from=None):
    """同一父面板里换控件：旧实例移到 Transient，新控件沿用旧插槽（slot 中给出的项覆盖）；var=None 时沿用旧控件的"是变量"。
    新控件保留旧控件的同父索引；支持 ContentWidget 父控件。"""
    values = check_slot(slot or {})
    old_obj = widget(path, old)
    parent_obj = old_obj.get_parent()
    kind, add = panel_kind(parent_obj) if parent_obj else (None, None)
    if kind is None:
        raise RuntimeError('cannot replace the root widget or a widget whose parent is not a panel: ' + old)
    name = new_name or old
    if name != old and name in {w['name'] for w in widgets(path)}:
        raise RuntimeError('widget name already exists: ' + name)
    keep_var = is_variable(path, old) if var is None else var
    saved = capture_slot(old_obj)
    old_index = parent_obj.get_child_index(old_obj)
    parent_obj.remove_child(old_obj)
    _to_transient(old_obj, old + '_Removed')
    obj = _create(path, cls_text, name)
    new_slot = getattr(parent_obj, add)(obj)
    restore_slot(new_slot, saved)
    apply_slot(new_slot, kind, values)
    result = dict(_finish_new(path, obj, text, text_name, text_font_from, copy_from, keep_var), parent=parent_obj.get_name(), kind=kind)
    parse(LIB.shift_child(path, name, old_index))
    return result


def remove_widget(path, name):
    obj = widget(path, name)
    parent_obj = obj.get_parent()
    if parent_obj is None:
        raise RuntimeError('cannot remove the root widget: ' + name)
    if not hasattr(parent_obj, 'remove_child'):
        raise RuntimeError('parent is not a panel widget (%s)' % parent_obj.get_class().get_name())
    parent_obj.remove_child(obj)
    _to_transient(obj, name + '_Removed')


def save(path):
    """编译并保存，返回是否保存成功（只读资产会失败）。"""
    bp = unreal.EditorAssetLibrary.load_asset(path.split('.')[0])
    if bp is None:
        raise RuntimeError('asset not found: ' + path)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    return bool(unreal.EditorAssetLibrary.save_asset(path.split('.')[0], only_if_is_dirty=False))


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
