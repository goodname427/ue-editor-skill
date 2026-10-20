"""
编辑器界面查看与操作，编辑器面板、弹出菜单与 PIE 界面通用。依赖 AgentTools 的 AgentSlateDriverFunctionLib，Locator 语法见 references/slate_driver.md。
兜底手段：能用 Python API 脚本完成的操作不要走这里（见 SKILL.md「选择方式」）。

  exec --action ui windows                                         列出可见窗口
  exec --action ui tree [根Locator] [--index=N] [--depth=N] [--window=标题] [--full] [--hidden] [--max=N]
  exec --action ui find <Locator> [--window=标题] [--hidden]         隐藏查询结果仅作诊断，不复用下标/几何
  exec --action ui at <x,y>                                        坐标处最上层控件
  exec --action ui focus                                           当前键盘焦点
  exec --action ui click <Locator> [--index=N] [--right] [--double] [--hold=秒] [--expect-hit=<Locator>] [--no-check]    或 --at=x,y
  exec --action ui type <文本> [--focus=<Locator>] [--index=N] [--enter] [--append]
  exec --action ui key <键名> [--ctrl] [--shift] [--alt] [--hold=秒] [--focus=<Locator>] [--index=N]    键名如 Escape / Enter / F5 / A
  exec --action ui scroll <Locator> [--index=N] [--delta=-3] [--frames=8]        或 --at=x,y；delta 正数向上
  按住 / 抬起 / 移动：
  exec --action ui keydown <键名> [--ctrl] [--shift] [--alt] [--max-hold=30]           按住不放，直到 keyup / release；--max-hold 秒后自动抬起
  exec --action ui keyup <键名>
  exec --action ui mousedown <Locator> [--index=N] [--right|--middle] [--max-hold=30]   或 --at=x,y；控件模式校验落点未被遮挡
  exec --action ui mouseup [--right|--middle]
  exec --action ui move <Locator> [--index=N] [--frames=1]                      或 --at=x,y；按着鼠标键时就是拖动
  exec --action ui drag <Locator> --to=x,y [--frames=20] [--right|--middle]     或 --at=x,y / --to-target=<Locator>
  exec --action ui release                                                       取消排队中的输入并抬起全部按键

所有输入都由 Skill lib 的 ue_input（scripts/lib/ue_input.py）拼装，排在同一条时间线上：前一步完成才执行下一步，
某步失败时取消其后所有步骤；CLI 在脚本执行完后按顺序等每一步的结果。项目脚本也直接 import ue_input，不要自己再拼。

- 坐标为桌面像素 [x,y,w,h]，可原样给 `screenshot --rect=x,y,w,h`（坐标可能为负，参数一律写成 --k=v）。
- 输入在下一帧执行：本次输出的焦点、状态都是输入执行前的。要在同一次调用里确认效果，加 CLI 的 --wait-until，
  如 click "text=Window" --wait-until "unreal.AgentSlateDriverFunctionLib.find_widgets('text=Enable Fullscreen','') != '[]'"
- tree 默认精简：只列有文字/提示/Tag、可点击/可聚焦的控件和 UserWidget 边界，按钮的唯一文字子节点并入按钮行；
  看纯布局/图片控件用 --full，或直接 find name=控件名。
- 输入文本前用 --focus 直接把焦点设到输入框（如 --focus="hint~=Search"），比先点击再输入可靠。
- 带 --focus 的 type 是原子替换：全选旧内容 → 输入 → 加 --enter 时提交 → 回读，实际值不一致直接判失败；
  数字/搜索框把新值追加到旧值后面（1→1100000）时不会再静默成功。只在提交时同步业务的框必须加 --enter；
  被业务上下限截断时 actual 是截断后的值。保留旧内容用 --append。
- click 默认校验落点最上层控件是目标或其子节点、且目标可用：目标被抽屉/弹窗盖住、或文字是 HitTestInvisible 时会失败而不是点到别处；
  --expect-hit 换一个控件做同样的校验（--at 坐标点击时只有它会校验）。确实要点击穿透时用 --no-check。
- scroll 返回 handled / moved：handled 是事件路径上有没有控件处理滚轮，moved 才是内容是否移动；
  容器 ConsumeMouseWheel=Never 时 handled 可能为 true 而 moved=false。不能只看 queued。
- 长按：click / key 加 --hold=秒（按住这么久再抬起，命令在抬起后才返回）。按住直到某个条件成立：
  keydown/mousedown 加 CLI 的 --wait-until 等条件，再 keyup/mouseup；键盘有现成清单 sequence --action hold-until。
  中途失败也不会一直按着：--max-hold 秒（默认 30）后自动抬起，或手动 ui release。
- --window 只匹配独立窗口的标题；停靠面板都在主窗口里，用根 Locator 定位（如 tree "type=SContentBrowser" --index=0）。

每行控件：名称<类型:UMG类> [x,y,w,h] #tag "文本" hint="输入框提示" label="无文字按钮的名称（折叠文字或 tooltip）" vis=.. owner=所属UMG @click *focus ^hover !disabled
"""
import ue_input
from ue_input import LIB as lib, parse, describe as line


def fold_text_children(nodes):
    """控件只有一个纯文字子节点时省掉子节点：无文字的可点击控件把文字并到自己这一行；文字与自己相同（如标签页）直接丢弃。"""
    out, i = [], 0
    while i < len(nodes):
        n = nodes[i]
        nxt = nodes[i + 1] if i + 1 < len(nodes) else None
        after = nodes[i + 2] if i + 2 < len(nodes) else None
        sole_text = (nxt and nxt['d'] == n['d'] + 1 and nxt.get('text') and 'STextBlock' in nxt['type']
                     and not nxt.get('interactable') and not nxt.get('name') and (after is None or after['d'] <= n['d']))
        if sole_text and (n.get('text') == nxt['text'] or (n.get('interactable') and not n.get('text'))):
            n = dict(n, text=nxt['text'])
            n.pop('label', None)
            i += 1
        out.append(n)
        i += 1
    return out


def point(text):
    x, y = (float(v) for v in text.split(','))
    return x, y


def need_target(what):
    if not ARGS[1:] and not OPTS.get('at'):
        raise RuntimeError('%s needs <Locator> or --at=x,y\n\n%s' % (what, __doc__))


def target_point():
    """--at 优先，否则取 Locator 命中控件的中心；返回 (x, y, 命中控件或 None)。"""
    if OPTS.get('at'):
        return point(OPTS['at']) + (None,)
    node = ue_input.match(ARGS[1], window, index)
    return ue_input.center(node) + (node,)


def button_name():
    return 'Right' if OPTS.get('right') else 'Middle' if OPTS.get('middle') else 'Left'


def print_target(node):
    if node:
        print('target: ' + line(node))


cmd = ARGS[0] if ARGS else ''
for key in ('index', 'depth', 'max', 'delta', 'at', 'window', 'focus', 'expect_hit', 'hold', 'max_hold', 'frames', 'to', 'to_target'):
    if OPTS.get(key) is True:
        raise RuntimeError('--%s needs a value; use --%s=<value>, not --%s <value>' % (key, key, key))
window = OPTS.get('window', '')
index = int(OPTS.get('index', 0))
mods = (bool(OPTS.get('ctrl')), bool(OPTS.get('shift')), bool(OPTS.get('alt')))
max_hold = float(OPTS.get('max_hold', ue_input.MAX_HOLD))

if cmd == 'windows':
    for w in parse(lib.list_windows()):
        print('%s [%d,%d,%d,%d]%s' % ((w['title'] or '(untitled popup)',) + tuple(w['rect']) + (' active' if w['active'] else '',)))

elif cmd == 'tree':
    root = ARGS[1] if len(ARGS) > 1 else ''
    call = [window, root, int(OPTS.get('depth', 0)), bool(OPTS.get('hidden')), not OPTS.get('full'), int(OPTS.get('max', 3000))]
    if 'index' in OPTS:
        call.append(index)
    data = parse(lib.dump_slate_tree(*call))
    if root and data.get('root_match_count', 0) == 0:
        raise RuntimeError('Root Locator did not match: %s; use ui find to verify name/type/class and visibility' % root)
    out = []
    for win in data['windows']:
        out.append('== %s [%d,%d,%d,%d]' % ((win['title'] or '(untitled popup)',) + tuple(win['rect'])))
        nodes = win['nodes'] if OPTS.get('full') else fold_text_children(win['nodes'])
        out.extend(line(n, '  ' * n['d']) for n in nodes)
    if data.get('truncated'):
        out.append('... truncated at %d nodes, narrow with root Locator / --index / --depth' % data['node_count'])
    if root and data.get('root_match_count', 0) > 1 and 'index' not in OPTS:
        out.append('... root matched %d times, add --index=N to dump only one' % data['root_match_count'])
    print('\n'.join(out) or '(no match)')

elif cmd == 'find':
    if len(ARGS) < 2:
        raise RuntimeError(__doc__)
    matches = parse(lib.find_widgets(ARGS[1], window, True) if OPTS.get('hidden') else lib.find_widgets(ARGS[1], window))
    print('\n'.join('[%d] %s  (%s)' % (i, line(n), n['window'] or 'untitled popup') for i, n in enumerate(matches)) or '(no match)')
    if OPTS.get('hidden'):
        print('[query only] hidden-result indices/geometry cannot be reused for click or screenshot')

elif cmd == 'at':
    if len(ARGS) < 2:
        raise RuntimeError(__doc__)
    print(line(ue_input.widget_at(*point(ARGS[1]))))

elif cmd == 'focus':
    print(line(parse(lib.get_keyboard_focus())))

elif cmd == 'click':
    need_target('click')
    if OPTS.get('hidden'):
        raise RuntimeError('click does not accept --hidden; find visible targets again')
    if 'expect_hit' in OPTS and not OPTS['expect_hit']:
        raise RuntimeError('--expect-hit requires a non-empty Locator')
    hold = float(OPTS.get('hold', 0))
    at = point(OPTS['at']) if OPTS.get('at') else None
    r = ue_input.click(None if at else ARGS[1], at, window, index, button_name(), bool(OPTS.get('double')), hold,
                       not OPTS.get('no_check'), OPTS.get('expect_hit'))
    print_target(r['target'])
    print('queued %s %s at (%d,%d), topmost there: %s' % (button_name().lower(), 'press %gs' % hold if hold else 'click', r['pos'][0], r['pos'][1], line(r['hit'])))

elif cmd == 'type':
    if len(ARGS) < 2:
        raise RuntimeError(__doc__)
    if OPTS.get('focus'):
        r = ue_input.input_text(OPTS['focus'], ARGS[1], window, index, not OPTS.get('append'), bool(OPTS.get('enter')))
        print('queued: input %r into %s' % (ARGS[1], line(r['focusable'])))
    elif OPTS.get('append'):
        raise RuntimeError('--append needs --focus: 追加输入要先确定输入框，否则不知道往哪里写')
    else:
        r = ue_input.type_chars(ARGS[1])
        if OPTS.get('enter'):
            ue_input.key('Enter')
        print('queued: type %r%s; focus before input: %s' % (ARGS[1], ' -> Enter' if OPTS.get('enter') else '', line(r['focus'])))

elif cmd == 'key':
    if len(ARGS) < 2:
        raise RuntimeError(__doc__)
    if OPTS.get('focus'):
        print('queued: focus ' + line(ue_input.focus(OPTS['focus'], window, index)['focusable']))
    hold = float(OPTS.get('hold', 0))
    r = ue_input.key(ARGS[1], *mods, hold=hold)
    name = '+'.join([m for m, on in zip(('ctrl', 'shift', 'alt'), mods) if on] + [ARGS[1]])
    print('queued: %s%s; focus before input: %s' % (name, ' held %gs' % hold if hold else '', line(r['focus'])))

elif cmd in ('keydown', 'keyup'):
    if len(ARGS) < 2:
        raise RuntimeError(__doc__)
    if cmd == 'keydown':
        r = ue_input.key_down(ARGS[1], *mods, max_hold=max_hold)
        print('queued: hold %s (auto release after %gs if not released); focus before input: %s' % (ARGS[1], max_hold, line(r['focus'])))
    else:
        ue_input.key_up(ARGS[1])
        print('queued: release %s' % ARGS[1])

elif cmd == 'mousedown':
    need_target('mousedown')
    x, y, node = target_point()
    print_target(node)
    r = ue_input.mouse_down(x, y, button_name(), False, ARGS[1] if node else '', window, index, max_hold)
    print('queued %s press at (%d,%d) (auto release after %gs if not released), topmost there: %s'
          % (button_name().lower(), x, y, max_hold, line(r['hit'])))

elif cmd == 'mouseup':
    ue_input.mouse_up(button_name())
    print('queued %s release at current pointer' % button_name().lower())

elif cmd == 'move':
    need_target('move')
    x, y, _ = target_point()
    frames = int(OPTS.get('frames', 1))
    ue_input.move(x, y, frames)
    print('queued pointer move to (%d,%d) over %d frame(s)' % (x, y, frames))

elif cmd == 'drag':
    need_target('drag')
    if not OPTS.get('to') and not OPTS.get('to_target'):
        raise RuntimeError('drag needs --to=x,y or --to-target=<Locator>')
    x, y, node = target_point()
    to = point(OPTS['to']) if OPTS.get('to') else ue_input.center(ue_input.match(OPTS['to_target'], window))
    frames = int(OPTS.get('frames', 20))
    print_target(node)
    r = ue_input.drag((x, y), to, frames, button_name(), ARGS[1] if node else '', window, index)
    print('queued %s drag (%d,%d) -> (%d,%d) over %d frames, topmost at start: %s'
          % (button_name().lower(), x, y, to[0], to[1], frames, line(r['hit'])))

elif cmd == 'release':
    ue_input.release_all()
    print('queued: cancel pending input and release every held key and button')

elif cmd == 'scroll':
    need_target('scroll')
    x, y, _ = target_point()
    delta = float(OPTS.get('delta', -3))
    _, before = ue_input.scroll(x, y, delta, int(OPTS.get('frames', 8)))
    print('queued scroll %g at (%d,%d), topmost there: %s' % (delta, x, y, line(before)))

else:
    raise RuntimeError(__doc__)
