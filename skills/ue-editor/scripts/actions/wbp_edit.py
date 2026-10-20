"""
Widget 蓝图写操作：新增 / 改名 / 改属性 / 换控件 / 移除，改完自动编译保存；也可只编译保存（save）。
本入口只解析参数与打印，逻辑都在 Skill lib 的 ue_wbp（脚本里直接 import ue_wbp，见 references/widget_blueprint_info.md）。

  exec --action wbp_edit list <WBP路径>                                       控件清单：名字 | 类型 | 是否变量 | 父控件
  exec --action wbp_edit rename <WBP路径> <旧名> <新名>                        改控件名，同步变量引用、属性/动画/导航绑定
  exec --action wbp_edit set <WBP路径> <控件名> <属性>=<值> [<属性>=<值> ...] [--slot]   改属性（--slot 改它所在插槽），值用 UE 文本格式：
                                                                           bIsVariable=True、Visibility=Collapsed；写后回读，解析失败直接报错
  exec --action wbp_edit add <WBP路径> <父控件名|root> <新名> <类> [选项]       在面板下新增控件（追加到末尾，没有插入/替换 API）
  exec --action wbp_edit replace <WBP路径> <旧控件名> <类> [选项]              同父面板换控件（旧实例移出到 Transient；新控件追加到末尾）
  exec --action wbp_edit remove <WBP路径> <控件名>                             从父面板移除并移出 WidgetTree
  exec --action wbp_edit save <WBP路径>...                                    只编译 + 保存，脚本改完蓝图后的收尾（--no-save 攒下的改动在这里统一落盘）

选项（add / replace）：
  --text=<文本>           同时新建 TextBlock 子控件并设文字（按钮等 Content 控件）
  --text-name=<名>        文字控件名，默认 Btn_Xxx → Text_Xxx
  --text-copy=<控件名>    文字控件复制该控件的 font
  --copy=<控件名>         复制该控件的外观属性（widget_style / font / item_style / scroll_bar_style / content_padding /
                          foreground_color / max_list_height 里两边都有的）
  --no-var                不勾"是变量"：add 默认勾上；replace 默认沿用旧控件的变量状态
  --var                   replace 强制勾"是变量"
  --new-name=<名>         replace 时给新控件换名（默认沿用旧名，保持按名字的引用）
  CanvasPanel 槽位：--anchor=minx,miny,maxx,maxy  --offset=l,t,r,b  --align=x,y      replace 不写时沿用旧控件槽位
  横向/纵向/Overlay 槽位：--padding=l,t,r,b  --size=值[,fill|auto]  --halign=left|center|right|fill  --valign=top|center|bottom|fill
  --no-save               只改内存不编译保存（留给后续 save 统一收尾）

- 类写引擎/项目 UMG 类名（Button、TextBlock、MyButton）或蓝图路径（/Game/.../WBP_Foo）。
- 改前先签出资产（如 p4 edit），只读资产保存会失败；控件查找、槽位字段与排版手法见 references/widget_blueprint_edit.md。
"""
import ue_wbp


def _usage(message):
    raise RuntimeError(message + '\n\n' + __doc__)


def _nums(key):
    try:
        return [float(p) for p in str(OPTS[key]).split(',')]
    except ValueError:
        _usage('--%s values must be numbers' % key)


def _slot_opts():
    """命令行槽位选项 → ue_wbp.check_slot 的参数；先校验，参数不合法时资产一点都不改。"""
    slot = {key: _nums(key) for key in ('anchor', 'offset', 'align', 'padding') if key in OPTS}
    if 'size' in OPTS:
        value, _, rule = str(OPTS['size']).partition(',')
        try:
            slot['size'] = (float(value), (rule or 'auto').strip().lower())
        except ValueError:
            _usage('--size value must be a number')
    slot.update({key: OPTS[key] for key in ('halign', 'valign') if key in OPTS})
    try:
        ue_wbp.check_slot(slot)
        return slot
    except ValueError as e:
        error = str(e)
    _usage('--' + error)


def _new_opts():
    return dict(slot=_slot_opts(), text=OPTS.get('text'), text_name=OPTS.get('text_name'),
                text_font_from=OPTS.get('text_copy'), copy_from=OPTS.get('copy'))


def _finish(path):
    if OPTS.get('no_save'):
        print('no-save: blueprint not compiled or saved')
    elif ue_wbp.save(path):
        print('saved ' + path)
    else:
        raise RuntimeError('save failed; check the asset is checked out and writable: ' + path)


def _report(result, verb, path):
    extra = ''.join(' %s=%s' % (k, result[k]) for k in ('text', 'copied') if result.get(k))
    print('%s %s <%s> in %s (%s), is_variable=%s%s'
          % (verb, result['name'], result['type'], result['parent'], result['kind'], result['is_variable'], extra))
    slot = ue_wbp.props(path, result['name'], slot=True)
    kind = slot.pop('__type__')
    print('slot <%s>: %s' % (kind, '  '.join('%s=%s' % item for item in sorted(slot.items()))))


cmd = ARGS[0] if ARGS else ''
if cmd == 'list':
    if len(ARGS) < 2:
        _usage('list needs <WBP路径>')
    for item in ue_wbp.widgets(ARGS[1]):
        print('%s | %s | var=%s | parent=%s' % (item['name'], item['type'], item['is_variable'], item['parent']))

elif cmd == 'rename':
    if len(ARGS) < 4:
        _usage('rename needs <WBP路径> <旧名> <新名>')
    print(ue_wbp.rename_widget(ARGS[1], ARGS[2], ARGS[3]))
    _finish(ARGS[1])

elif cmd == 'set':
    if len(ARGS) < 4:
        _usage('set needs <WBP路径> <控件名> <属性>=<值> ...')
    values = {}
    for item in ARGS[3:]:
        prop, sep, value = item.partition('=')
        if not sep or not prop:
            _usage('set values are written as <属性>=<值>')
        values[prop] = value
    for prop, value in ue_wbp.set_props(ARGS[1], ARGS[2], values, bool(OPTS.get('slot'))).items():
        print('%s -> %s' % (prop, value))
    _finish(ARGS[1])

elif cmd == 'add':
    if len(ARGS) < 5:
        _usage('add needs <WBP路径> <父控件名|root> <新名> <类>')
    _report(ue_wbp.add_widget(ARGS[1], ARGS[2], ARGS[3], ARGS[4], var=not OPTS.get('no_var'), **_new_opts()), 'added', ARGS[1])
    _finish(ARGS[1])

elif cmd == 'replace':
    if len(ARGS) < 4:
        _usage('replace needs <WBP路径> <旧控件名> <类>')
    var = True if OPTS.get('var') else False if OPTS.get('no_var') else None
    _report(ue_wbp.replace_widget(ARGS[1], ARGS[2], ARGS[3], new_name=OPTS.get('new_name'), var=var, **_new_opts()),
            'replaced with', ARGS[1])
    _finish(ARGS[1])

elif cmd == 'remove':
    if len(ARGS) < 3:
        _usage('remove needs <WBP路径> <控件名>')
    ue_wbp.remove_widget(ARGS[1], ARGS[2])
    print('removed %s from WidgetTree' % ARGS[2])
    _finish(ARGS[1])

elif cmd == 'save':
    if len(ARGS) < 2:
        _usage('save needs <WBP路径>...')
    failed = []
    for path in ARGS[1:]:
        ok = ue_wbp.save(path)
        print(('saved ' if ok else 'SAVE FAIL ') + path)
        if not ok:
            failed.append(path)
    if failed:
        raise RuntimeError('failed: ' + ', '.join(failed))

else:
    _usage('unknown or missing command: ' + repr(cmd))
