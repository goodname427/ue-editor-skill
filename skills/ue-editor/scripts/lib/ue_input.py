"""
编辑器内的输入组合：点击、长按、按键、拖动、滚动、文本输入，都由 AgentSlateDriverFunctionLib 的原子步骤拼出来。
Skill 的 ui Lib 和项目脚本都 import 这里，不要在别处再拼一遍（ue_cli 每次执行前把本目录加进 sys.path）。

  import ue_input
  ue_input.click('name=Btn_OK')                     控件中心点击，默认校验落点没被遮挡
  ue_input.click(at=(x, y))                         坐标点击，不校验；要校验加 expect_hit=<Locator>
  ue_input.click('name=Btn', hold=1.5)              长按 1.5 秒
  ue_input.key('Escape') / key('S', ctrl=True) / key('E', hold=1.5)
  ue_input.input_text('name=EditableTextBox_Num', '5', commit=True)
  ue_input.scroll(x, y, -3)
  ue_input.drag((x0, y0), (x1, y1), frames=20)
  job = ue_input.analog({'Gamepad_LeftX': 1}, hold=0.5)
  ue_input.check('__import__("ue_input").check_analog(job)')

键鼠原子步骤排在 C++ 的同一条时间线上；AnalogInput 是同步单事件，配对与逐帧采样用本 lib 的 Slate 回调组合。
每步打印 `[input-request] <id> [秒]`，需要回读的组合再打印 `[input-check] <表达式>`；
ue_cli 执行完脚本后按顺序等这些结果，失败时报 InputAssertionFailed。调用方不要自己 sleep 或轮询。
"""
import json
import math
import time
import unreal
from ue_common import parse, require

LIB = require('AgentSlateDriverFunctionLib')

MAX_HOLD = 30.0
EDITABLE_TYPES = ('SEditableText', 'SEditableTextBox', 'SMultiLineEditableText', 'SMultiLineEditableTextBox')


def _queued(raw, seconds=0.0):
    r = parse(raw)
    print('[input-request] %d%s' % (r['request_id'], ' %g' % seconds if seconds else ''))
    return r


def check(expr):
    """前面的步骤都完成后，ue_cli 求值 expr；它须返回 JSON 字符串，ok=false 时判失败。"""
    print('[input-check] ' + expr)


# ---------- 查询 ----------

def find(locator, window=''):
    return parse(LIB.find_widgets(locator, window))


def find_one(locator, window=''):
    """第一个命中的控件，没有时返回 None。"""
    matches = find(locator, window)
    return matches[0] if matches else None


_MARKS = (('interactable', '@click'), ('focus', '*focus'), ('hover', '^hover'))


def describe(n, prefix=''):
    """控件节点的一行文字：名称<类型:UMG类> [x,y,w,h] #tag "文本" hint=.. label=.. vis=.. owner=.. @click *focus ^hover !disabled。"""
    if not n:
        return '(none)'
    kind = n['type'] + (':' + n['class'] if n.get('class') else '')
    parts = [prefix + n.get('name', '') + '<' + kind + '>', '[%d,%d,%d,%d]' % tuple(n['rect'])]
    if n.get('tag'):
        parts.append('#' + n['tag'])
    if n.get('text'):
        parts.append(json.dumps(n['text'], ensure_ascii=False))
    if n.get('hint'):
        parts.append('hint=' + json.dumps(n['hint'], ensure_ascii=False))
    if n.get('label'):
        parts.append('label=' + json.dumps(n['label'], ensure_ascii=False))
    if n.get('vis'):
        parts.append('vis=' + n['vis'])
    if n.get('owner') and n.get('owner') != n.get('name'):
        parts.append('owner=' + n['owner'])
    parts.extend(mark for key, mark in _MARKS if n.get(key))
    if n.get('enabled') is False:
        parts.append('!disabled')
    if n.get('hidden_by'):
        parts.append('hidden_by=' + n['hidden_by'])
    if n.get('clipped'):
        parts.append('visible=[%d,%d,%d,%d]' % tuple(n['visible_rect']))
        parts.append('!clipped')
    if n.get('geometry_valid') is False:
        parts.append('!geometry')
    if n.get('query_only'):
        parts.append('!query-only')
    return ' '.join(parts).replace('\r', '\\r').replace('\n', '\\n')


def match(locator, window='', index=0):
    matches = find(locator, window)
    if not 0 <= index < len(matches):
        raise RuntimeError('no widget at index %d (%d matched): %s' % (index, len(matches), locator))
    return matches[index]


def center(node):
    x, y, w, h = node.get('visible_rect', node['rect'])
    return x + w / 2.0, y + h / 2.0


def widget_at(x, y):
    return json.loads(LIB.widget_at(x, y))


def read_text(locator, window='', index=0):
    """命中控件的文字；它不是输入框时取其中第一个输入框（与 FocusWidget 的取法一致）。控件不在时返回 None。"""
    matches = find(locator, window)
    if not 0 <= index < len(matches):
        return None
    node = matches[index]
    if node['type'] in EDITABLE_TYPES:
        return node.get('text', '')
    tree = parse(LIB.dump_slate_tree(window, locator, 5, False, False, 200, index))
    for win in tree['windows']:
        for n in win['nodes']:
            if n['type'] in EDITABLE_TYPES:
                return n.get('text', '')
    return node.get('text', '')


# ---------- 原子步骤 ----------

def key_down(name, ctrl=False, shift=False, alt=False, max_hold=MAX_HOLD, protect_cursor=True):
    end = {}
    guard = preserve_cursor(lambda: 'request_id' not in end or not json.loads(LIB.get_input_result(end['request_id'])).get('pending', False)) if protect_cursor else None
    result = _queued(LIB.key_down(name, ctrl, shift, alt, max_hold))
    end.update(result)
    if guard:
        result['cursor'] = guard
        wait(0, 3)
    return result


def key_up(name):
    return _queued(LIB.key_up(name))


def mouse_down(x, y, button='Left', double=False, check_locator='', window='', index=0, max_hold=MAX_HOLD):
    return _queued(LIB.mouse_down(x, y, button, double, check_locator, window, index, max_hold))


def mouse_up(button='Left'):
    return _queued(LIB.mouse_up(button))


def move(x, y, frames=1):
    return _queued(LIB.mouse_move(x, y, frames))


def wheel(x, y, delta):
    return _queued(LIB.mouse_wheel(x, y, delta))


def focus(locator, window='', index=0):
    return _queued(LIB.focus_widget(locator, window, index))


def select_all():
    return _queued(LIB.select_all_text())


def type_chars(text):
    return _queued(LIB.type_text(text))


def wait(seconds=0.0, frames=0):
    return _queued(LIB.wait_input(seconds, frames), seconds)


def release_all():
    return _queued(LIB.release_all_input())


# ---------- 组合 ----------

def preserve_cursor(done, timeout=35.0):
    """临时使用引擎虚拟光标，完成后至少留两帧和 0.2 秒；不回写系统鼠标位置。"""
    original = parse(LIB.use_platform_cursor_for_cursor_user(False))
    state = {'pending': True, 'ok': False, 'wait': timeout + 1}
    timer = {'handle': None, 'settled': 0, 'settle_start': None, 'deadline': time.monotonic() + timeout}
    try:
        parse(LIB.set_cursor_position(*original['pos']))
    except Exception:
        parse(LIB.use_platform_cursor_for_cursor_user(True))
        raise

    def restore(message=''):
        try:
            parse(LIB.set_cursor_visibility(original['visible']))
        except Exception as error:
            message = message or str(error)
        finally:
            try:
                parse(LIB.use_platform_cursor_for_cursor_user(True))
            except Exception as error:
                message = message or str(error)
            unreal.unregister_slate_post_tick_callback(timer['handle'])
            state.update(pending=False, ok=not message, message=message)

    def tick(delta):
        try:
            if time.monotonic() >= timer['deadline']:
                restore('Cursor isolation timed out')
            elif done():
                if timer['settle_start'] is None:
                    timer['settle_start'] = time.monotonic()
                timer['settled'] += 1
                if timer['settled'] >= 2 and time.monotonic() - timer['settle_start'] >= 0.2:
                    restore()
        except Exception as error:
            restore(str(error))

    try:
        timer['handle'] = unreal.register_slate_post_tick_callback(tick)
    except Exception:
        parse(LIB.use_platform_cursor_for_cursor_user(True))
        raise
    return state


def _press_point(locator, at, window, index, check, expect_hit):
    """落点与校验对象：给 at 时用坐标、只按 expect_hit 校验；否则用控件中心、默认校验该控件。"""
    if at is not None:
        return at[0], at[1], None, (expect_hit or ''), 0
    target = match(locator, window, index)
    x, y = center(target)
    if expect_hit:
        return x, y, target, expect_hit, 0
    return x, y, target, (locator if check else ''), index


def click(locator=None, at=None, window='', index=0, button='Left', double=False, hold=0.0, check=True, expect_hit=None):
    """单击 / 双击 / 长按。返回 {'target', 'pos', 'hit'}（hit 为排队时落点最上层控件）。"""
    x, y, target, check_locator, check_index = _press_point(locator, at, window, index, check, expect_hit)
    down = mouse_down(x, y, button, False, check_locator, window, check_index, MAX_HOLD + hold)
    if hold:
        wait(hold)
    mouse_up(button)
    if double:
        mouse_down(x, y, button, True, check_locator, window, check_index)
        mouse_up(button)
    return {'target': target, 'pos': (x, y), 'hit': down.get('hit')}


def key(name, ctrl=False, shift=False, alt=False, hold=0.0, protect_cursor=True):
    """按下/等待/抬起；默认隔离系统光标，测试真实光标行为时设 protect_cursor=False。"""
    end = {}
    def done():
        return 'request_id' not in end or not json.loads(LIB.get_input_result(end['request_id'])).get('pending', False)
    guard = preserve_cursor(done, MAX_HOLD + hold + 5) if protect_cursor else None
    try:
        down = key_down(name, ctrl, shift, alt, MAX_HOLD + hold, protect_cursor=False)
        wait(hold, 1)
        end.update(key_up(name))
    except Exception:
        end.clear()
        raise
    if guard:
        down['cursor'] = guard
        wait(0, 3)
    return down


def analog_input(name, value, device_id=-1):
    """同步发送单个轴事件；这是原子操作，非零值由调用方负责归零。"""
    return parse(LIB.analog_input(name, value, device_id))


def _analog_values(values):
    axes = ('Gamepad_LeftX', 'Gamepad_LeftY', 'Gamepad_RightX', 'Gamepad_RightY',
            'Gamepad_LeftTriggerAxis', 'Gamepad_RightTriggerAxis')
    if not isinstance(values, dict) or not values:
        raise ValueError('analog needs a nonempty key/value dict')
    out = {}
    for name, value in values.items():
        value = float(value)
        minimum = 0 if name.endswith('TriggerAxis') else -1
        if name not in axes or not math.isfinite(value) or not minimum <= value <= 1:
            raise ValueError('invalid gamepad axis/value: %s' % name)
        out[name] = value
    for x, y in (axes[:2], axes[2:4]):
        if x in out or y in out:
            out.setdefault(x, 0.0)
            out.setdefault(y, 0.0)
    return out


def analog_set(values, device_id=-1, protect_cursor=True):
    """校验整批后同帧发单轴事件，摇杆补齐另一轴；不保持、不自动归零。"""
    values = _analog_values(values)
    sent, result = [], {'values': values, 'handled': False}
    if protect_cursor:
        result['cursor'] = preserve_cursor(lambda: True)
    try:
        for name, value in values.items():
            event = analog_input(name, value, device_id)
            device_id = event['device_id']
            sent.append(name)
            result.update(device_id=device_id, platform_user=event['platform_user'], slate_user=event['slate_user'])
            result['handled'] |= event['handled']
    except Exception as error:
        cleanup_errors = []
        for name in sent:
            try:
                analog_input(name, 0.0, device_id)
            except Exception as cleanup_error:
                cleanup_errors.append(str(cleanup_error))
        if cleanup_errors:
            raise RuntimeError('%s; neutralizing failed: %s' % (error, '; '.join(cleanup_errors))) from error
        raise
    return result


def analog(values, hold=0.0, device_id=-1, protect_cursor=True):
    """Slate 回调逐帧采样后归零；返回本次组合结果，调用方用 check_analog 等待。"""
    values = _analog_values(values)
    hold = float(hold)
    if not math.isfinite(hold) or not 0 <= hold <= MAX_HOLD:
        raise ValueError('analog hold must be in [0, %g]' % MAX_HOLD)
    gate = wait(0, 1)
    result = {'pending': True, 'ok': False, 'wait': hold + 5, 'samples': 0, 'handled': False, 'values': values}
    if protect_cursor:
        result['cursor'] = preserve_cursor(lambda: not result['pending'], hold + 5)
    timer = {'handle': None, 'start': None, 'device': device_id, 'cancelled': False}
    editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    was_pie = editor.is_in_play_in_editor()

    def finish(message=''):
        if not result['pending']:
            return
        try:
            if result['samples']:
                for name in values:
                    try:
                        analog_input(name, 0.0, timer['device'])
                    except Exception as error:
                        message = message or str(error)
        finally:
            unreal.unregister_slate_post_tick_callback(timer['handle'])
            result.update(pending=False, ok=not message, message=message)

    def tick(delta):
        try:
            if timer['cancelled']:
                finish('Analog input cancelled')
                return
            if was_pie and not editor.is_in_play_in_editor():
                finish('PIE ended during analog input')
                return
            state = json.loads(LIB.get_input_result(gate['request_id']))
            tail_state = json.loads(LIB.get_input_result(timer['tail']['request_id']))
            if not state.get('success') or not tail_state.get('success'):
                finish(state.get('message') or tail_state.get('message', 'Input timeline was cancelled'))
                return
            if state.get('pending'):
                return
            if timer['start'] is None:
                timer['start'] = time.monotonic()
            if result['samples'] and time.monotonic() - timer['start'] >= hold:
                finish()
                return
            event = analog_set(values, timer['device'], protect_cursor=False)
            timer['device'] = event['device_id']
            result.update(device_id=event['device_id'], platform_user=event['platform_user'], slate_user=event['slate_user'])
            result['handled'] |= event['handled']
            result['samples'] += 1
        except Exception as error:
            finish(str(error))

    result['cancel'] = lambda: timer.update(cancelled=True)
    timer['handle'] = unreal.register_slate_post_tick_callback(tick)
    timer['tail'] = wait(hold, 2)
    return result


def check_analog(result):
    state = {key: value for key, value in result.items() if key != 'cancel'}
    guard = result.get('cursor')
    if guard and not result['pending']:
        state['pending'] = guard['pending']
        state['ok'] = result['ok'] and guard['ok']
        if not guard['ok'] and not guard['pending']:
            state['message'] = guard.get('message', 'Cursor isolation failed')
    return json.dumps(state, ensure_ascii=False)


def drag(start, end, frames=20, button='Left', check_locator='', window='', index=0):
    down = mouse_down(start[0], start[1], button, False, check_locator, window, index)
    move(end[0], end[1], frames)
    mouse_up(button)
    return down


def scroll(x, y, delta, frames=8):
    """滚一次滚轮，等 frames 帧后回读落点最上层控件有没有变（moved）。返回 (排队结果, 滚动前落点控件)。"""
    before = widget_at(x, y)
    r = wheel(x, y, delta)
    wait(0, frames)
    check('__import__("ue_input").check_moved(%r, %r, %r)' % (x, y, json.dumps(before)))
    return r, before


def check_moved(x, y, before_json):
    before, after = json.loads(before_json), widget_at(x, y)
    moved = before is None or after is None or any(before.get(k) != after.get(k) for k in ('type', 'name', 'rect'))
    return json.dumps({'ok': True, 'moved': moved, 'hit': after}, ensure_ascii=False)


def input_text(locator, text, window='', index=0, replace=True, commit=False):
    """聚焦 → 全选（replace）→ 输入 → 回车（commit）→ 等两帧回读；回读值不等于预期时判失败。
    只在提交时同步业务的框要 commit=True；被业务截断（上下限、格式化）时失败里的 actual 就是截断后的值。"""
    expected = text if replace else (read_text(locator, window, index) or '') + text
    r = focus(locator, window, index)
    if replace:
        select_all()
    type_chars(text)
    if commit:
        key('Enter')
    wait(0, 2)
    check('__import__("ue_input").check_text(%r, %r, %d, %r)' % (locator, window, index, expected))
    return r


def check_text(locator, window, index, expected):
    actual = read_text(locator, window, index)
    if actual is None:
        # 提交后控件消失（如搜索框所在弹窗关闭），无法回读，不当作失败
        return json.dumps({'ok': True, 'expected': expected, 'actual': '(target destroyed)'}, ensure_ascii=False)
    ok = actual == expected
    return json.dumps({'ok': ok, 'expected': expected, 'actual': actual,
                       'message': '' if ok else 'Text readback does not match the requested value'}, ensure_ascii=False)
