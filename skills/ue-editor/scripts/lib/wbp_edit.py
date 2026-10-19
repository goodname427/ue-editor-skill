"""
Widget 蓝图写操作：新增 / 改名 / 改属性 / 换控件 / 移除，改完自动编译保存；也可只编译保存（save）。依赖 AgentTools 的 AgentWidgetBlueprintInfoFunctionLib。

  exec --lib wbp_edit list <WBP路径>                                       控件清单：名字 | 类型 | 是否变量 | 父控件
  exec --lib wbp_edit rename <WBP路径> <旧名> <新名>                        改控件名（自动名换成语义名）
  exec --lib wbp_edit set <WBP路径> <控件名> <属性>=<值> [<属性>=<值> ...]   改属性，值用 UE 文本格式：bIsVariable=True、Visibility=Collapsed
  exec --lib wbp_edit add <WBP路径> <父控件名|root> <新名> <类> [选项]       在面板下新增控件（追加到末尾，没有插入/替换 API）
  exec --lib wbp_edit replace <WBP路径> <旧控件名> <类> [选项]              同名同槽位换控件（旧实例移出到 Transient）
  exec --lib wbp_edit remove <WBP路径> <控件名>                             从父面板移除并移出 WidgetTree
  exec --lib wbp_edit save <WBP路径>... [--gen]                            只编译 + 保存，脚本改完蓝图后的收尾（--no-save 攒下的改动在这里统一落盘）

选项（add / replace）：
  --text=<文本>           同时新建 TextBlock 子控件并设文字（按钮等 Content 控件）
  --text-name=<名>        文字控件名，默认 Btn_Xxx → Text_Xxx
  --text-copy=<控件名>    文字控件复制该控件的 font
  --copy=<控件名>         复制该控件的外观属性（widget_style / font / item_style / scroll_bar_style / content_padding /
                          foreground_color / max_list_height 里两边都有的）
  --no-var                不勾"是变量"：add 默认勾上（保存会刷新 ue_bp.d.ts）；replace 默认沿用旧控件的变量状态
  --var                   replace 强制勾"是变量"
  --new-name=<名>         replace 时给新控件换名（默认沿用旧名，保持 TS 绑定）
  CanvasPanel 槽位：--anchor=minx,miny,maxx,maxy  --offset=l,t,r,b  --align=x,y      replace 不写时沿用旧控件槽位
  横向/纵向/Overlay 槽位：--padding=l,t,r,b  --size=值[,fill|auto]  --halign=left|center|right|fill  --valign=top|center|bottom|fill
  --no-save               只改内存不编译保存（留给后续 save 统一收尾）
  --gen / --no-gen        add / replace / remove 默认执行 Puerts.Gen（新增或换掉控件要刷新 TS 类型；非 Puerts 工程用 --no-gen）；rename / set / save 默认不执行

- 类写引擎/项目 UMG 类名（Button、TextBlock、MyButton）或蓝图路径（/Game/.../WBP_Foo）。
- 改前先签出资产（如 p4 edit），只读资产保存会失败；控件查找、槽位字段与排版手法见 references/widget_blueprint_edit.md。
"""
import json
import unreal

if getattr(unreal, 'AgentWidgetBlueprintInfoFunctionLib', None) is None:
    raise RuntimeError('AgentWidgetBlueprintInfoFunctionLib not found: compile and enable plugin AgentTools, then restart the editor')
LIB = unreal.AgentWidgetBlueprintInfoFunctionLib

_TRANSIENT = '/Engine/Transient'
_ATTACH = (('canvas', 'CanvasPanel', 'add_child_to_canvas'),
           ('hbox', 'HorizontalBox', 'add_child_to_horizontal_box'),
           ('vbox', 'VerticalBox', 'add_child_to_vertical_box'),
           ('overlay', 'Overlay', 'add_child_to_overlay'))
_HALIGN = {'left': 'H_ALIGN_LEFT', 'center': 'H_ALIGN_CENTER', 'right': 'H_ALIGN_RIGHT', 'fill': 'H_ALIGN_FILL'}
_VALIGN = {'top': 'V_ALIGN_TOP', 'center': 'V_ALIGN_CENTER', 'bottom': 'V_ALIGN_BOTTOM', 'fill': 'V_ALIGN_FILL'}
_COPY_PROPS = ('widget_style', 'font', 'item_style', 'scroll_bar_style', 'content_padding', 'foreground_color', 'max_list_height')


def _usage(message):
    raise RuntimeError(message + '\n\n' + __doc__)


def _nums(text, count, what):
    parts = str(text).split(',')
    if len(parts) != count:
        _usage('%s needs %d comma-separated numbers' % (what, count))
    try:
        return [float(p) for p in parts]
    except ValueError:
        _usage('%s values must be numbers' % what)


def _tree_path(path):
    return path + '.' + path.rsplit('/', 1)[-1] + ':WidgetTree'


def _flat(path):
    return json.loads(LIB.get_all_widgets_flat(path))


def _root_name(path):
    for item in _flat(path):
        if str(item.get('parent') or '') in ('', 'None'):
            return item['name']
    raise RuntimeError('no root widget found: ' + path)


def _load(path):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    tree = unreal.find_object(None, _tree_path(path))
    if asset is None or tree is None:
        raise RuntimeError('not a WidgetBlueprint asset: ' + path)
    return asset, tree


def _widget(path, name):
    obj = unreal.find_object(None, _tree_path(path) + '.' + name)
    if obj is None:
        raise RuntimeError('widget not found: %s (check names with list)' % name)
    return obj


def _panel_kind(obj):
    for kind, cls_name, add in _ATTACH:
        cls = getattr(unreal, cls_name, None)
        if cls is not None and isinstance(obj, cls):
            return kind, add
    return None, None


def _resolve_class(text):
    if text.startswith('/'):
        cls = unreal.EditorAssetLibrary.load_blueprint_class(text)
        if cls is None:
            raise RuntimeError('blueprint class not found: ' + text)
        return cls
    cls = getattr(unreal, text, None)
    if not isinstance(cls, type):
        raise RuntimeError('widget class not found: %s (use a UMG class name or a /Game blueprint path)' % text)
    return cls


def _create(path, tree, cls_text, name):
    if name in {item['name'] for item in _flat(path)}:
        raise RuntimeError('widget name already exists: ' + name)
    return unreal.new_object(_resolve_class(cls_text), tree, name)


def _copy_props(target, source, prop_names):
    copied = []
    for prop in prop_names:
        try:
            value = source.get_editor_property(prop)
            target.get_editor_property(prop)
        except Exception:
            continue
        try:
            target.set_editor_property(prop, value)
            copied.append(prop)
        except Exception:
            pass
    return copied


def _parse_slot(opts):
    """先解析槽位选项，参数不合法在改动资产之前就报错。"""
    values = {}
    for key, count in (('anchor', 4), ('offset', 4), ('align', 2), ('padding', 4)):
        if key in opts:
            values[key] = _nums(opts[key], count, '--' + key)
    if 'size' in opts:
        value, _, rule = str(opts['size']).partition(',')
        rule = (rule or 'auto').strip().lower()
        if rule not in ('auto', 'fill'):
            _usage('--size rule must be fill or auto')
        try:
            values['size'] = (float(value), rule)
        except ValueError:
            _usage('--size value must be a number')
    if 'halign' in opts:
        values['halign'] = _enum(unreal.HorizontalAlignment, _HALIGN, opts['halign'], '--halign')
    if 'valign' in opts:
        values['valign'] = _enum(unreal.VerticalAlignment, _VALIGN, opts['valign'], '--valign')
    return values


def _apply_slot(slot, kind, values):
    if kind == 'canvas':
        if not any(key in values for key in ('anchor', 'offset', 'align')):
            return
        anchor = values.get('anchor', [0, 0, 0, 0])
        offset = values.get('offset', [0, 0, 0, 0])
        align = values.get('align', [0, 0])
        layout = unreal.AnchorData()
        layout.anchors = unreal.Anchors(minimum=unreal.Vector2D(anchor[0], anchor[1]),
                                        maximum=unreal.Vector2D(anchor[2], anchor[3]))
        layout.offsets = unreal.Margin(offset[0], offset[1], offset[2], offset[3])
        layout.alignment = unreal.Vector2D(align[0], align[1])
        slot.set_layout(layout)
    else:
        if 'padding' in values:
            pad = values['padding']
            slot.set_padding(unreal.Margin(pad[0], pad[1], pad[2], pad[3]))
        if 'size' in values:
            value, rule = values['size']
            slot.set_size(unreal.SlateChildSize(value, unreal.SlateSizeRule.FILL if rule == 'fill'
                                                else unreal.SlateSizeRule.AUTOMATIC))
        if 'halign' in values:
            slot.set_horizontal_alignment(values['halign'])
        if 'valign' in values:
            slot.set_vertical_alignment(values['valign'])


def _enum(cls, names, text, what):
    key = str(text).strip().lower()
    if key not in names:
        _usage('%s must be one of: %s' % (what, ', '.join(sorted(names))))
    value = getattr(cls, names[key], None)
    if value is None:
        raise RuntimeError('enum value missing: %s.%s' % (cls, names[key]))
    return value


def _capture_slot(widget):
    """换控件前把旧槽位读成普通值，移出后仍可复用。"""
    slot = widget.slot
    if slot is None:
        return None
    data = {}
    for prop in ('layout', 'padding', 'size', 'horizontal_alignment', 'vertical_alignment', 'auto_size', 'z_order'):
        try:
            data[prop] = slot.get_layout() if prop == 'layout' else slot.get_editor_property(prop)
        except Exception:
            pass
    return data


def _restore_slot(slot, data):
    if slot is None or not data:
        return
    for prop, value in data.items():
        try:
            if prop == 'layout':
                slot.set_layout(value)
            elif prop == 'padding':
                slot.set_padding(value)
            elif prop == 'size':
                slot.set_size(value)
            elif prop == 'horizontal_alignment':
                slot.set_horizontal_alignment(value)
            elif prop == 'vertical_alignment':
                slot.set_vertical_alignment(value)
            else:
                slot.set_editor_property(prop, value)
        except Exception:
            pass


def _text_name(name):
    return 'Text_' + name[4:] if name.startswith('Btn_') else 'Text_' + name


def _add_text(tree, target, opts, source=None):
    text = unreal.new_object(unreal.TextBlock, tree, str(opts.get('text_name') or _text_name(target.get_name())))
    if source is not None:
        _copy_props(text, source, ('font',))
    text.set_text(str(opts['text']))
    if not hasattr(target, 'add_child'):
        raise RuntimeError('%s cannot hold a text child; drop --text' % target.get_class().get_name())
    target.add_child(text)
    return text


def _set_var(path, name, value):
    """新建控件的 bIsVariable 默认值随类不同（本项目引擎里 Widget 基类是 true，Button 不覆盖，多数面板和 TextBlock 显式 false），
    要状态确定就得显式写，写完回读确认。"""
    result = json.loads(LIB.set_widget_property(path, name, 'bIsVariable', 'True' if value else 'False'))
    print('var %s: %s' % (name, result.get('message')))
    if not result.get('success'):
        raise RuntimeError('bIsVariable failed: ' + str(result))
    for item in _flat(path):
        if item['name'] == name:
            print('is_variable now: %s' % item['is_variable'])


def _gen(paths, opts, default_gen):
    if not (opts.get('gen') or (default_gen and not opts.get('no_gen'))):
        return
    for folder in sorted({p.rsplit('/', 1)[0] for p in paths}):
        unreal.SystemLibrary.execute_console_command(None, 'Puerts.Gen PATH=' + folder)
        print('Puerts.Gen ' + folder)


def _save(path):
    bp = unreal.EditorAssetLibrary.load_asset(path)
    if bp is None:
        print('NOT FOUND ' + path)
        return False
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    saved = unreal.EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)
    print(('saved ' if saved else 'SAVE FAIL ') + path)
    return bool(saved)


def _finish(path, opts, default_gen):
    if opts.get('no_save'):
        print('no-save: blueprint not compiled or saved')
        return
    if not _save(path):
        raise RuntimeError('save failed; check the asset is checked out and writable')
    _gen([path], opts, default_gen)


def _print_slot(path, name):
    print('slot ' + name + ': ' + json.dumps(json.loads(LIB.get_widget_slot_info(path, name)), ensure_ascii=False))


cmd = ARGS[0] if ARGS else ''
if cmd == 'list':
    if len(ARGS) < 2:
        _usage('list needs <WBP路径>')
    for item in _flat(ARGS[1]):
        print('%s | %s | var=%s | parent=%s' % (item['name'], item['type'], item['is_variable'], item['parent']))

elif cmd == 'rename':
    if len(ARGS) < 4:
        _usage('rename needs <WBP路径> <旧名> <新名>')
    result = json.loads(LIB.rename_child_widget(ARGS[1], ARGS[2], ARGS[3]))
    print(str(result.get('message')))
    if not result.get('success'):
        raise RuntimeError('rename failed: ' + str(result))
    _finish(ARGS[1], OPTS, False)

elif cmd == 'set':
    if len(ARGS) < 4:
        _usage('set needs <WBP路径> <控件名> <属性>=<值> ...')
    path, name = ARGS[1], ARGS[2]
    failed = []
    for item in ARGS[3:]:
        prop, sep, value = item.partition('=')
        if not sep or not prop:
            _usage('set values are written as <属性>=<值>')
        result = json.loads(LIB.set_widget_property(path, name, prop, value))
        print('%s=%s -> %s' % (prop, value, result.get('message')))
        if not result.get('success'):
            failed.append(prop)
    if failed:
        raise RuntimeError('set failed: ' + ', '.join(failed))
    if any(item.startswith('bIsVariable=') for item in ARGS[3:]):
        for w in _flat(path):
            if w['name'] == name:
                print('is_variable now: %s' % w['is_variable'])
    _finish(path, OPTS, False)

elif cmd in ('add', 'replace'):
    if len(ARGS) < (5 if cmd == 'add' else 4):
        _usage('%s needs %s' % (cmd, '<WBP路径> <父控件名|root> <新名> <类>' if cmd == 'add' else '<WBP路径> <旧控件名> <类>'))
    path = ARGS[1]
    slot_values = _parse_slot(OPTS)
    asset, tree = _load(path)
    if cmd == 'add':
        parent_name = ARGS[2]
        name, cls_text = ARGS[3], ARGS[4]
        parent = _widget(path, _root_name(path) if parent_name == 'root' else parent_name)
        kind, add = _panel_kind(parent)
        if kind is None:
            raise RuntimeError('parent is not a panel widget: %s (%s)' % (parent_name, parent.get_class().get_name()))
        target = _create(path, tree, cls_text, name)
        slot = getattr(parent, add)(target)
        print('added %s <%s> into %s (%s)' % (name, target.get_class().get_name(), parent_name, kind))
    else:
        old_name = ARGS[2]
        old = _widget(path, old_name)
        parent = old.get_parent()
        kind, add = _panel_kind(parent) if parent else (None, None)
        if kind is None:
            raise RuntimeError('cannot replace root widget or a widget whose parent is not a panel: ' + old_name)
        was_var = next(item['is_variable'] for item in _flat(path) if item['name'] == old_name)
        name = str(OPTS.get('new_name') or old_name)
        cls_text = ARGS[3]
        data = _capture_slot(old)
        parent.remove_child(old)
        old.rename(old_name + '_Removed', unreal.find_object(None, _TRANSIENT))
        target = _create(path, tree, cls_text, name)
        slot = getattr(parent, add)(target)
        _restore_slot(slot, data)
        print('replaced %s with <%s>, old instance moved to Transient' % (name, target.get_class().get_name()))
    _apply_slot(slot, kind, slot_values)
    _print_slot(path, name)
    if OPTS.get('text') is not None:
        _add_text(tree, target, OPTS, _widget(path, str(OPTS['text_copy'])) if OPTS.get('text_copy') else None)
    if OPTS.get('copy'):
        copied = _copy_props(target, _widget(path, str(OPTS['copy'])), _COPY_PROPS)
        print('copied %s from %s' % (', '.join(copied) or '(none)', OPTS['copy']))
    if cmd == 'add':
        _set_var(path, name, not OPTS.get('no_var'))
    elif cmd == 'replace':
        _set_var(path, name, bool(OPTS.get('var')) or (was_var and not OPTS.get('no_var')))
    _finish(path, OPTS, True)

elif cmd == 'remove':
    if len(ARGS) < 3:
        _usage('remove needs <WBP路径> <控件名>')
    path, name = ARGS[1], ARGS[2]
    target = _widget(path, name)
    parent = target.get_parent()
    if parent is None:
        raise RuntimeError('cannot remove the root widget: ' + name)
    if not hasattr(parent, 'remove_child'):
        raise RuntimeError('parent is not a panel widget (%s); remove it in the WBP designer' % parent.get_class().get_name())
    parent.remove_child(target)
    target.rename(name + '_Removed', unreal.find_object(None, _TRANSIENT))
    print('removed %s from WidgetTree' % name)
    _finish(path, OPTS, True)

elif cmd == 'save':
    if len(ARGS) < 2:
        _usage('save needs <WBP路径>...')
    failed = [path for path in ARGS[1:] if not _save(path)]
    _gen(ARGS[1:], OPTS, False)
    if failed:
        raise RuntimeError('failed: ' + ', '.join(failed))

else:
    _usage('unknown or missing command: ' + repr(cmd))
