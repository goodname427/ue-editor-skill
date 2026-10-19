"""
编辑器界面查看与操作，编辑器面板、弹出菜单与 PIE 界面通用。依赖 AgentTools 的 AgentSlateDriverFunctionLib，Locator 语法见 references/slate_driver.md。
兜底手段：能用 Python API 脚本完成的操作不要走这里（见 SKILL.md「选择方式」）。

  exec --lib ui windows                                         列出可见窗口
  exec --lib ui tree [根Locator] [--index=N] [--depth=N] [--window=标题] [--full] [--hidden] [--max=N]
  exec --lib ui find <Locator> [--window=标题] [--hidden]         隐藏查询结果仅作诊断，不复用下标/几何
  exec --lib ui focus                                           当前键盘焦点
  exec --lib ui click <Locator> [--index=N] [--right] [--double] [--expect-hit=<Locator>]    或 --at=x,y；断言必须唯一命中
  exec --lib ui type <文本> [--focus=<Locator>] [--index=N] [--enter]
  exec --lib ui key <键名> [--ctrl] [--shift] [--alt] [--focus=<Locator>] [--index=N]    键名如 Escape / Enter / F5 / A
  exec --lib ui scroll <Locator> [--index=N] [--delta=-3]        或 --at=x,y；delta 正数向上

- 坐标为桌面像素 [x,y,w,h]，可原样给 `screenshot --rect=x,y,w,h`（坐标可能为负，参数一律写成 --k=v）。
- 输入在下一帧执行：本次输出的焦点、状态都是输入执行前的。要在同一次调用里确认效果，加 CLI 的 --wait-until，
  如 click "text=Window" --wait-until "unreal.AgentSlateDriverFunctionLib.find_widgets('text=Enable Fullscreen','') != '[]'"
- tree 默认精简：只列有文字/提示/Tag、可点击/可聚焦的控件和 UserWidget 边界，按钮的唯一文字子节点并入按钮行；
  看纯布局/图片控件用 --full，或直接 find name=控件名。
- 输入文本前用 --focus 直接把焦点设到输入框（如 --focus="hint~=Search"），比先点击再输入可靠。
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


cmd = ARGS[0] if ARGS else ''
for key in ('index', 'depth', 'max', 'delta', 'at', 'window', 'focus', 'expect_hit'):
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
    button = 'Right' if OPTS.get('right') else 'Middle' if OPTS.get('middle') else 'Left'
    double = bool(OPTS.get('double'))
    if OPTS.get('hidden'):
        raise RuntimeError('click does not accept --hidden; find visible targets again')
    expected = (OPTS['expect_hit'],) if OPTS.get('expect_hit') else ()
    if 'expect_hit' in OPTS and not expected:
        raise RuntimeError('--expect-hit requires a non-empty Locator')
    if OPTS.get('at'):
        r = parse(lib.click_at(*point(OPTS['at']) + (button, double) + expected))
    else:
        r = parse(lib.click_widget(ARGS[1], window, index, button, double, *expected))
        print('target (%d matched): %s' % (r['match_count'], line(r['target'])))
    print('queued %s click at (%d,%d), topmost there: %s' % (button.lower(), r['pos'][0], r['pos'][1], line(r['hit'])))
    if expected:
        print('[input-request] %d' % r['request_id'])

elif cmd in ('type', 'key'):
    if len(ARGS) < 2:
        raise RuntimeError(__doc__)
    steps = []
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
        r = parse(lib.press_key(ARGS[1], bool(OPTS.get('ctrl')), bool(OPTS.get('shift')), bool(OPTS.get('alt'))))
        steps.append('+'.join([m for m in ('ctrl', 'shift', 'alt') if OPTS.get(m)] + [ARGS[1]]))
    print('queued: ' + ' -> '.join(steps))
    if not OPTS.get('focus'):
        print('focus before input: ' + line(r['focus']))

elif cmd == 'scroll':
    need_target('scroll')
    if OPTS.get('at'):
        x, y = point(OPTS['at'])
    else:
        matches = parse(lib.find_widgets(ARGS[1], window))
        if index >= len(matches):
            raise RuntimeError('no widget at index %d (%d matched)' % (index, len(matches)))
        x, y = center(matches[index])
    r = parse(lib.scroll_at(x, y, float(OPTS.get('delta', -3))))
    print('queued scroll %s at (%d,%d), topmost there: %s' % (OPTS.get('delta', -3), x, y, line(r['hit'])))

else:
    raise RuntimeError(__doc__)
