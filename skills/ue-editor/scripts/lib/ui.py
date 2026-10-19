"""
编辑器界面查看与操作，编辑器面板、弹出菜单与 PIE 界面通用。依赖 AgentTools 的 AgentSlateDriverFunctionLib，Locator 语法见 references/slate_driver.md。
兜底手段：能用 Python API 脚本完成的操作不要走这里（见 SKILL.md「选择方式」）。

  exec --lib ui windows                                         列出可见窗口
  exec --lib ui tree [根Locator] [--index=N] [--depth=N] [--window=标题] [--full] [--hidden] [--max=N]
  exec --lib ui find <Locator> [--window=标题] [--hidden]         隐藏查询结果仅作诊断，不复用下标/几何
  exec --lib ui focus                                           当前键盘焦点
  exec --lib ui click <Locator> [--index=N] [--right] [--double] [--hold=秒] [--expect-hit=<Locator>] [--no-check]    或 --at=x,y
  exec --lib ui type <文本> [--focus=<Locator>] [--index=N] [--enter] [--append]
  exec --lib ui key <键名> [--ctrl] [--shift] [--alt] [--hold=秒] [--focus=<Locator>] [--index=N]    键名如 Escape / Enter / F5 / A
  exec --lib ui scroll <Locator> [--index=N] [--delta=-3] [--frames=N]        或 --at=x,y；delta 正数向上
  按住 / 抬起 / 移动（同一条时间线，前一步完成才执行下一步，某步失败取消其后所有步骤）：
  exec --lib ui keydown <键名> [--ctrl] [--shift] [--alt] [--max-hold=30]           按住不放，直到 keyup / release；--max-hold 秒后自动抬起
  exec --lib ui keyup <键名>
  exec --lib ui mousedown <Locator> [--index=N] [--right|--middle] [--max-hold=30]   或 --at=x,y；控件模式校验落点未被遮挡
  exec --lib ui mouseup [--right|--middle]
  exec --lib ui move <Locator> [--index=N] [--frames=1]                      或 --at=x,y；按着鼠标键时就是拖动
  exec --lib ui drag <Locator> --to=x,y [--frames=20] [--right|--middle]     或 --at=x,y / --to-target=<Locator>
  exec --lib ui release                                                       取消排队中的按住类输入并抬起全部按键

- 坐标为桌面像素 [x,y,w,h]，可原样给 `screenshot --rect=x,y,w,h`（坐标可能为负，参数一律写成 --k=v）。
- 输入在下一帧执行：本次输出的焦点、状态都是输入执行前的。要在同一次调用里确认效果，加 CLI 的 --wait-until，
  如 click "text=Window" --wait-until "unreal.AgentSlateDriverFunctionLib.find_widgets('text=Enable Fullscreen','') != '[]'"
- tree 默认精简：只列有文字/提示/Tag、可点击/可聚焦的控件和 UserWidget 边界，按钮的唯一文字子节点并入按钮行；
  看纯布局/图片控件用 --full，或直接 find name=控件名。
- 输入文本前用 --focus 直接把焦点设到输入框（如 --focus="hint~=Search"），比先点击再输入可靠。
- 带 --focus 的 type 是原子替换：全选旧内容 → 输入 → 加 --enter 时提交 → 回读，实际值不一致直接判失败；
  数字/搜索框把新值追加到旧值后面（1→1100000）时不会再静默成功。只在提交时同步业务的框必须加 --enter；
  被业务上下限截断时 actual 是截断后的值。保留旧内容用 --append。
- click 默认校验光标下最上层控件是目标或其子节点：目标被抽屉/弹窗盖住、或文字是 HitTestInvisible 时会失败而不是点到别处；
  --expect-hit 另有严格断言（须唯一命中）。确实要点击穿透时用 --no-check。
- scroll 返回 handled / moved：handled 是事件路径上有没有控件处理滚轮，moved 才是内容是否移动；
  容器 ConsumeMouseWheel=Never 时 handled 可能为 true 而 moved=false。不能只看 queued。
- 长按：click / key 加 --hold=秒（按住这么久再抬起，命令在抬起后才返回）。按住直到某个条件成立：
  keydown/mousedown 加 CLI 的 --wait-until 等条件，再 keyup/mouseup；键盘有现成清单 sequence --lib hold-until。
  中途失败也不会一直按着：--max-hold 秒（默认 30）后自动抬起，或手动 ui release。
- --window 只匹配独立窗口的标题；停靠面板都在主窗口里，用根 Locator 定位（如 tree "type=SContentBrowser" --index=0）。

每行控件：名称<类型:UMG类> [x,y,w,h] #tag "文本" hint="输入框提示" label="无文字按钮的名称（折叠文字或 tooltip）" vis=.. owner=所属UMG @click *focus ^hover !disabled
"""
import json
import unreal

lib = getattr(unreal, 'AgentSlateDriverFunctionLib', None)
if lib is None:
    raise RuntimeError('AgentSlateDriverFunctionLib not found: compile and enable plugin AgentTools, then restart the editor')

MARKS = (('interactable', '@click'), ('focus', '*focus'), ('hover', '^hover'))


def parse(raw):
    data = json.loads(raw)
    if isinstance(data, dict) and (data.get('error') or data.get('success') is False):
        raise RuntimeError(data.get('error') or data.get('message'))
    return data


def line(n, prefix=''):
    if not n:
        return '(none)'
    kind = n['type'] + (':' + n['class'] if n.get('class') else '')
    parts = [prefix + n.get('name', '') + '<' + kind + '>', '[%d,%d,%d,%d]' % tuple(n['rect'])]
    if n.get('tag'):
        parts.append('#' + n['tag'])
    if n.get('text'):
        parts.append('"' + n['text'].replace('\n', '\\n') + '"')
    if n.get('hint'):
        parts.append('hint="%s"' % n['hint'])
    if n.get('label'):
        parts.append('label="%s"' % n['label'])
    if n.get('vis'):
        parts.append('vis=' + n['vis'])
    if n.get('owner') and n.get('owner') != n.get('name'):
        parts.append('owner=' + n['owner'])
    parts.extend(mark for key, mark in MARKS if n.get(key))
    if n.get('enabled') is False:
        parts.append('!disabled')
    if n.get('hidden_by'):
        parts.append('hidden_by=' + n['hidden_by'])
    if n.get('geometry_valid') is False:
        parts.append('!geometry')
    if n.get('query_only'):
        parts.append('!query-only')
    return ' '.join(parts)


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


def center(n):
    x, y, w, h = n['rect']
    return x + w / 2.0, y + h / 2.0


def need_target(what):
    if not ARGS[1:] and not OPTS.get('at'):
        raise RuntimeError('%s needs <Locator> or --at=x,y\n\n%s' % (what, __doc__))


def button_name():
    return 'Right' if OPTS.get('right') else 'Middle' if OPTS.get('middle') else 'Left'


def widget_center(locator):
    matches = parse(lib.find_widgets(locator, window))
    if index >= len(matches):
        raise RuntimeError('no widget at index %d (%d matched): %s' % (index, len(matches), locator))
    return center(matches[index])


def request(r, seconds=0.0):
    # CLI 按这一行跨帧回读结果；带秒数时多等这么久（按住的时长）
    if r.get('request_id'):
        print('[input-request] %d%s' % (r['request_id'], ' %g' % seconds if seconds else ''))


def max_hold(seconds=0.0):
    # 定时长按的看门狗至少比按住时长多 30 秒，不抢在定时抬起之前
    limit = float(OPTS.get('max_hold', 30))
    return max(limit, seconds + 30.0) if seconds else limit


cmd = ARGS[0] if ARGS else ''
for key in ('index', 'depth', 'max', 'delta', 'at', 'window', 'focus', 'expect_hit', 'hold', 'max_hold', 'frames', 'to', 'to_target'):
    if OPTS.get(key) is True:
        raise RuntimeError('--%s needs a value; use --%s=<value>, not --%s <value>' % (key, key, key))
window = OPTS.get('window', '')
index = int(OPTS.get('index', 0))

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

elif cmd == 'focus':
    print(line(parse(lib.get_keyboard_focus())))

elif cmd == 'click':
    need_target('click')
    button = button_name()
    double = bool(OPTS.get('double'))
    if OPTS.get('hidden'):
        raise RuntimeError('click does not accept --hidden; find visible targets again')
    expected = (OPTS['expect_hit'],) if OPTS.get('expect_hit') else ()
    if 'expect_hit' in OPTS and not expected:
        raise RuntimeError('--expect-hit requires a non-empty Locator')
    if OPTS.get('hold'):
        # 长按 = 按下 → 等待 → 抬起，走按住类时间线；控件模式照样校验落点未被遮挡
        if double or expected:
            raise RuntimeError('--hold cannot be combined with --double / --expect-hit')
        seconds = float(OPTS['hold'])
        if OPTS.get('at'):
            r = parse(lib.mouse_down('', '', 0, *point(OPTS['at']) + (button, seconds, max_hold(seconds))))
        else:
            r = parse(lib.mouse_down(ARGS[1], window, index, 0.0, 0.0, button, seconds, max_hold(seconds)))
            print('target (%d matched): %s' % (r['match_count'], line(r['target'])))
        print('queued %s press for %gs at (%d,%d), topmost there: %s' % (button.lower(), seconds, r['pos'][0], r['pos'][1], line(r['hit'])))
        request(r, seconds)
    else:
        if OPTS.get('at'):
            r = parse(lib.click_at(*point(OPTS['at']) + (button, double) + expected))
        else:
            r = parse(lib.click_widget(ARGS[1], window, index, button, double, OPTS.get('expect_hit', ''), not OPTS.get('no_check')))
            print('target (%d matched): %s' % (r['match_count'], line(r['target'])))
        print('queued %s click at (%d,%d), topmost there: %s' % (button.lower(), r['pos'][0], r['pos'][1], line(r['hit'])))
        request(r)

elif cmd in ('type', 'key'):
    if len(ARGS) < 2:
        raise RuntimeError(__doc__)
    steps = []
    if cmd == 'type' and OPTS.get('focus'):
        # 焦点、全选、输入、提交、回读在同一次调用里完成，结果由 CLI 跨帧回读
        r = parse(lib.input_text(OPTS['focus'], window, index, ARGS[1], not OPTS.get('append'), bool(OPTS.get('enter'))))
        steps.append('input %r into %s' % (ARGS[1], line(r['editable'])))
        print('queued: ' + ' -> '.join(steps))
        if r.get('request_id'):
            print('[input-request] %d' % r['request_id'])
    elif cmd == 'type' and OPTS.get('append'):
        raise RuntimeError('--append needs --focus: 追加输入要先确定输入框，否则不知道往哪里写')
    else:
        if OPTS.get('focus'):
            r = parse(lib.focus_widget(OPTS['focus'], window, index))
            steps.append('focus %s' % line(r['target']))
        if cmd == 'type':
            r = parse(lib.type_text(ARGS[1]))
            steps.append('type %r' % ARGS[1])
            if OPTS.get('enter'):
                parse(lib.press_key('Enter', False, False, False))
                steps.append('Enter')
        else:
            mods = [m for m in ('ctrl', 'shift', 'alt') if OPTS.get(m)]
            if OPTS.get('hold'):
                seconds = float(OPTS['hold'])
                r = parse(lib.key_down(ARGS[1], bool(OPTS.get('ctrl')), bool(OPTS.get('shift')), bool(OPTS.get('alt')), seconds, max_hold(seconds)))
                steps.append('+'.join(mods + [ARGS[1]]) + ' held %gs' % seconds)
            else:
                r = parse(lib.press_key(ARGS[1], bool(OPTS.get('ctrl')), bool(OPTS.get('shift')), bool(OPTS.get('alt'))))
                steps.append('+'.join(mods + [ARGS[1]]))
        print('queued: ' + ' -> '.join(steps))
        if not OPTS.get('focus'):
            print('focus before input: ' + line(r['focus']))
        if cmd == 'key' and OPTS.get('hold'):
            request(r, float(OPTS['hold']))

elif cmd in ('keydown', 'keyup'):
    if len(ARGS) < 2:
        raise RuntimeError(__doc__)
    if cmd == 'keydown':
        r = parse(lib.key_down(ARGS[1], bool(OPTS.get('ctrl')), bool(OPTS.get('shift')), bool(OPTS.get('alt')), 0.0, max_hold()))
        print('queued: hold %s (auto release after %gs if not released); focus before input: %s' % (ARGS[1], max_hold(), line(r['focus'])))
    else:
        r = parse(lib.key_up(ARGS[1]))
        print('queued: release %s' % ARGS[1])
    request(r)

elif cmd == 'mousedown':
    need_target('mousedown')
    button = button_name()
    if OPTS.get('at'):
        r = parse(lib.mouse_down('', '', 0, *point(OPTS['at']) + (button, 0.0, max_hold())))
    else:
        r = parse(lib.mouse_down(ARGS[1], window, index, 0.0, 0.0, button, 0.0, max_hold()))
        print('target (%d matched): %s' % (r['match_count'], line(r['target'])))
    print('queued %s press at (%d,%d) (auto release after %gs if not released), topmost there: %s'
          % (button.lower(), r['pos'][0], r['pos'][1], max_hold(), line(r['hit'])))
    request(r)

elif cmd == 'mouseup':
    r = parse(lib.mouse_up(button_name()))
    print('queued %s release at current pointer' % button_name().lower())
    request(r)

elif cmd == 'move':
    need_target('move')
    x, y = point(OPTS['at']) if OPTS.get('at') else widget_center(ARGS[1])
    frames = int(OPTS.get('frames', 1))
    r = parse(lib.mouse_move(x, y, frames))
    print('queued pointer move to (%d,%d) over %d frame(s)' % (x, y, frames))
    request(r)

elif cmd == 'drag':
    # 拖动 = 按下（校验落点）→ 分帧移动 → 抬起，三步排在同一条时间线上，按下失败时后两步自动取消
    need_target('drag')
    if not OPTS.get('to') and not OPTS.get('to_target'):
        raise RuntimeError('drag needs --to=x,y or --to-target=<Locator>')
    button = button_name()
    to = point(OPTS['to']) if OPTS.get('to') else widget_center(OPTS['to_target'])
    frames = int(OPTS.get('frames', 20))
    if OPTS.get('at'):
        down = parse(lib.mouse_down('', '', 0, *point(OPTS['at']) + (button, 0.0, max_hold())))
    else:
        down = parse(lib.mouse_down(ARGS[1], window, index, 0.0, 0.0, button, 0.0, max_hold()))
        print('target (%d matched): %s' % (down['match_count'], line(down['target'])))
    move = parse(lib.mouse_move(to[0], to[1], frames))
    up = parse(lib.mouse_up(button))
    print('queued %s drag (%d,%d) -> (%d,%d) over %d frames, topmost at start: %s'
          % (button.lower(), down['pos'][0], down['pos'][1], to[0], to[1], frames, line(down['hit'])))
    for r in (down, move, up):
        request(r)

elif cmd == 'release':
    r = parse(lib.release_all_input())
    print('queued: cancel pending hold/move input and release every held key and button')
    request(r)

elif cmd == 'scroll':
    need_target('scroll')
    if OPTS.get('at'):
        x, y = point(OPTS['at'])
    else:
        matches = parse(lib.find_widgets(ARGS[1], window))
        if index >= len(matches):
            raise RuntimeError('no widget at index %d (%d matched)' % (index, len(matches)))
        x, y = center(matches[index])
    r = parse(lib.scroll_at(x, y, float(OPTS.get('delta', -3)), int(OPTS.get('frames', 8))))
    print('queued scroll %s at (%d,%d), topmost there: %s' % (OPTS.get('delta', -3), x, y, line(r['hit'])))
    if r.get('request_id'):
        print('[input-request] %d' % r['request_id'])

else:
    raise RuntimeError(__doc__)
