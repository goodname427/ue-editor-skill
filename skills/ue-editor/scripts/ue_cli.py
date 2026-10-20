#!/usr/bin/env python
"""
UE Editor CLI - Agent 通过 shell 调用 UE 编辑器的命令行接口。

用法:
  python ue_cli.py discover                          发现本地 UE 编辑器实例
  python ue_cli.py exec "<code>" [脚本参数...]        在编辑器内执行内联代码
  python ue_cli.py exec --file <path> [脚本参数...]   在编辑器内执行本地 .py 文件
  python ue_cli.py exec --action <name> [脚本参数...] 在编辑器内执行 actions/<name>.py 入口脚本
  python ue_cli.py screenshot [--rect=x,y,w,h]       截取 UE 编辑器窗口（本地 Win32，不经过编辑器）
  python ue_cli.py log mark/read/wait --file <path>  本地日志基线、增量读取和等待
  python ue_cli.py sequence --file <steps.json>     跨帧步骤清单；内置清单也可 --action <name>

lib/ 是编辑器内可 import 的模块（ue_input / ue_wbp / ue_common），工程 .codebuddy/ue-editor/lib/ 同理；每次执行前自动加进 sys.path。

exec 成功时直接输出脚本 print 的文本，失败时输出 JSON（含 error_type / message）并以退出码 1 结束；
screenshot / discover / log 输出 JSON；log 失败时退出码为 1。
"""

import ast
import sys
import os
import json
import time
import locale
import argparse
import re

# 将 scripts/ 目录加入 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_bridge import UEBridge, DEFAULT_DISCOVER_TIMEOUT as DISCOVER_TIMEOUT
import ue_log

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
# actions：CLI 执行的入口（读 ARGS/OPTS、做事、打印）；lib：编辑器内可 import 的模块（只定义函数，导入无副作用）
ACTIONS_DIR = os.path.join(_SCRIPTS, 'actions')
LIB_DIR = os.path.join(_SCRIPTS, 'lib')
# 每次执行前把 Skill lib 与工程 <工程>/.codebuddy/ue-editor/lib 加进 sys.path，并丢掉这两处模块的缓存，
# 改完或 git pull 后无需重启编辑器。工程目录在编辑器里求，不用另传。
# 两处 lib 的模块名同时绑成惰性引用：等待条件里可以直接写 ph_market.ready()，不依赖哪个入口先执行过
PRELUDE = '''def _ue_prelude():
    import importlib, os, sys, unreal
    dirs = [%r, os.path.normpath(os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), '.codebuddy', 'ue-editor', 'lib'))]
    for d in reversed(dirs):
        if d not in sys.path:
            sys.path.insert(0, d)
    roots = [os.path.normcase(d) + os.sep for d in dirs]
    for name, module in list(sys.modules.items()):
        path = os.path.normcase(getattr(module, '__file__', None) or '')
        if any(path.startswith(r) for r in roots):
            sys.modules.pop(name, None)

    class LazyModule:
        def __init__(self, name):
            self.__name = name

        def __getattr__(self, attr):
            return getattr(importlib.import_module(self.__name), attr)

        def __repr__(self):
            return '<lib %%s>' %% self.__name

    scope = globals()
    for d in dirs:
        for f in (os.listdir(d) if os.path.isdir(d) else ()):
            name = f[:-3]
            if f.endswith('.py') and name.isidentifier() and (name not in scope or type(scope[name]).__name__ == 'LazyModule' or isinstance(scope[name], type(sys))):
                scope[name] = LazyModule(name)
_ue_prelude()
del _ue_prelude
''' % LIB_DIR

# 控制台/管道统一按 UTF-8 输出，避免 gbk 下中文乱码或编码异常
sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')


def _print_json(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _decode(raw):
    """按 UTF-8（容忍 BOM）解码，失败回退系统编码。"""
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), errors='replace')


def _read_source(args, tokens):
    """按 --action / --file / --stdin / 内联代码取源码，返回 (源码, 名称)；失败时打印错误并返回 (None, None)。
    内联代码取 tokens 中第一个非选项参数（会从 tokens 中移除），其余 tokens 都是脚本参数。"""
    path = name = None
    if args.action:
        path, name = os.path.join(ACTIONS_DIR, args.action + '.py'), 'actions/' + args.action + '.py'
        if not os.path.isfile(path):
            names = sorted(f[:-3] for f in os.listdir(ACTIONS_DIR) if f.endswith('.py'))
            _print_json({'status': 'error', 'error_type': 'ScriptNotFound', 'message': f'actions 中没有脚本 {args.action!r}。',
                         'suggestion': '可用脚本: ' + ', '.join(names)})
            return None, None
    elif args.file:
        path, name = args.file, args.file
    if path:
        try:
            with open(path, 'rb') as fp:
                return _decode(fp.read()), name
        except OSError as e:
            _print_json({'status': 'error', 'error_type': 'FileReadError', 'message': f'读取 {path} 失败: {e}'})
            return None, None
    if args.stdin:
        # 检测 stdin 是否为 TTY（无管道/重定向输入），避免在交互式终端阻塞等待 EOF
        if sys.stdin is None or sys.stdin.isatty():
            _print_json({'status': 'error', 'error_type': 'NoStdinPipe',
                         'message': '指定了 --stdin 但未通过管道传入数据（如 `cmd | python ue_cli.py exec --stdin`）'})
            return None, None
        value = _decode(sys.stdin.buffer.read()).strip()
        if value:
            return value, '<stdin>'
        _print_json({'status': 'error', 'error_type': 'EmptyStdin', 'message': 'stdin 为空，请通过管道传入代码'})
        return None, None
    for i, token in enumerate(tokens):
        if not token.startswith('--'):
            return tokens.pop(i), '<exec>'
    _print_json({'status': 'error', 'error_type': 'NoInput',
                 'message': '未提供代码：用内联代码、--file、--action 或 --stdin 之一传入'})
    return None, None


def _make_bridge(args):
    """根据 CLI 参数构造 UEBridge 实例。"""
    kwargs = {}
    if args.multicast_group:
        host, port = args.multicast_group.rsplit(':', 1)
        kwargs['multicast_group'] = (host, int(port))
    if args.multicast_bind:
        kwargs['multicast_bind'] = args.multicast_bind
    if args.timeout:
        kwargs['command_timeout'] = args.timeout
    return UEBridge(**kwargs)


def _discover_timeout(args):
    """--timeout 主要控制命令等待；发现阶段正常 1 秒内完成，封顶 5 秒避免编辑器不在线时空等。"""
    return min(args.timeout or DISCOVER_TIMEOUT, DISCOVER_TIMEOUT)


def _run(args, action):
    """连接编辑器 → action(bridge) → 断开；未发现节点时额外发现一次，不重发已执行的命令。"""
    bridge = _make_bridge(args)
    discover_timeout = _discover_timeout(args)
    try:
        conn = bridge.connect(remote_node_id=args.node, timeout=discover_timeout)
        if conn.get('error_type') == 'NoEditorFound':
            print('[warning] 未发现编辑器，额外发现一次（至多 %ss）。' % discover_timeout, file=sys.stderr)
            conn = bridge.connect(remote_node_id=args.node, timeout=discover_timeout)
        if conn['status'] != 'ok':
            return conn
        return action(bridge)
    finally:
        bridge.disconnect()


def _condition_true(bridge, expr):
    r = bridge.evaluate('bool(%s)' % expr)
    return r['status'] == 'ok' and r['result'] == 'True'


def _poll(bridge, expr, deadline):
    """求值只读条件直到为真或到时间；单次求值超时时不重发，而是继续收那条还没回来的结果。"""
    while True:
        r = bridge.evaluate('bool(%s)' % expr)
        while r['status'] != 'ok' and r.get('resumable') and time.monotonic() < deadline:
            r = bridge.receive_command()
        if r['status'] != 'ok':
            return r
        if r['result'] == 'True':
            return {'status': 'ok', 'result': r['result']}
        if time.monotonic() >= deadline:
            return {'status': 'timeout', 'result': r['result']}
        time.sleep(max(0, min(0.5, deadline - time.monotonic())))


def _input_check(bridge, expr, result):
    response = bridge.evaluate(expr)
    if response['status'] != 'ok':
        return dict(response, output=result.get('output', ''), command_sent=True)
    try:
        state = json.loads(ast.literal_eval(response['result']))
        if not isinstance(state, dict) or not isinstance(state.get('ok'), bool):
            raise ValueError('input check must return a JSON object with ok')
    except (ValueError, SyntaxError) as e:
        return {'status': 'error', 'error_type': 'InvalidResponse', 'message': str(e), 'command_sent': True}
    if not state['ok']:
        return {'status': 'error', 'error_type': 'InputAssertionFailed', 'message': state.get('message') or 'Input check failed',
                'input': state, 'output': result.get('output', ''), 'command_sent': True}
    result['output'] = result.get('output', '') + '[input checked] ' + json.dumps(state, ensure_ascii=False) + '\n'
    return None


def _complete_input(bridge, result):
    """按脚本输出顺序等待 [input-request]，并在其前面的请求都完成后求值 [input-check]。"""
    if result['status'] != 'ok':
        return result
    marks = re.findall(r'^\[input-(request|check)\] (.+)$', result.get('output', ''), re.MULTILINE)
    for kind, value in marks:
        if kind == 'check':
            failure = _input_check(bridge, value, result)
            if failure:
                return failure
            continue
        request, _, extra = value.partition(' ')
        # 时间线上的等待步骤在等满后才出结果，回读上限要加上等待时长
        limit = 5 + (float(extra) if extra else 0)
        begin = time.monotonic()
        while True:
            response = bridge.evaluate('unreal.AgentSlateDriverFunctionLib.get_input_result(%s)' % request)
            if response['status'] != 'ok':
                return dict(response, output=result.get('output', ''), request_id=int(request), command_sent=True)
            try:
                state = json.loads(ast.literal_eval(response['result']))
                if not isinstance(state, dict) or not isinstance(state.get('pending'), bool):
                    raise ValueError('input result missing pending')
            except (ValueError, SyntaxError) as e:
                return {'status': 'error', 'error_type': 'InvalidResponse', 'message': str(e), 'command_sent': True}
            if not state['pending']:
                if not state.get('success'):
                    return {'status': 'error', 'error_type': 'InputAssertionFailed', 'message': state.get('message', 'Hit assertion failed'),
                            'input': state, 'request_id': int(request), 'output': result.get('output', ''), 'command_sent': True}
                result['output'] = result.get('output', '') + '[input checked] ' + json.dumps(state, ensure_ascii=False) + '\n'
                break
            if time.monotonic() - begin >= limit:
                return {'status': 'error', 'error_type': 'InputWaitTimeout', 'message': '输入仍在排队或执行；不要重发。',
                        'request_id': int(request), 'command_sent': True, 'output': result.get('output', '')}
            time.sleep(0.1)
    return result


def _execute_and_wait(bridge, code, args):
    """日志验证在执行前取基线；表达式验证先预检，执行后跨帧等待。"""
    if getattr(args, 'wait_log', None) is not None:
        if not args.log_file or not args.wait_log or args.wait < 0 or not 1 <= args.log_lines <= 200:
            return {'status': 'error', 'error_type': 'LogArguments',
                    'message': '--wait-log 需要 --log-file、非空关键词、非负 --wait 和 1~200 --log-lines。'}
        baseline = ue_log.mark(args.log_file)
        if baseline['status'] != 'ok':
            return baseline
        result = _complete_input(bridge, bridge.execute(code))
        if result['status'] != 'ok':
            return result
        log = ue_log.wait(args.log_file, baseline['cursor'], args.wait_log, args.wait, args.log_lines)
        if log['status'] != 'ok':
            log.update(output=result.get('output', ''), command_sent=True)
            return log
        result['log'] = log
        return result
    already = bool(args.wait_until) and _condition_true(bridge, args.wait_until)
    result = _wait_until(bridge, _complete_input(bridge, bridge.execute(code)), args)
    if already and result['status'] == 'ok':
        result['wait_note'] = '--wait-until 条件在执行前就已成立，这次等待不能证明操作生效；换一个只在操作后才成立的条件'
    return result


def _wait_until(bridge, result, args):
    """命令成功后跨帧轮询 --wait-until 表达式，直到为真或超过 --wait 秒（编辑器内的脚本无法跨帧等待）。"""
    if result['status'] != 'ok' or not args.wait_until:
        return result
    begin = time.time()
    r = _poll(bridge, args.wait_until, begin + args.wait)
    if r['status'] == 'ok':
        result['waited'] = round(time.time() - begin, 1)
        return result
    if r['status'] == 'timeout':
        return {'status': 'error', 'error_type': 'WaitTimeout', 'output': result.get('output', ''),
                'message': f'{args.wait}s 内 --wait-until 条件仍不成立。'}
    return r


def _split_script_args(tokens):
    """--k=v → OPTS[k]=v；--k → OPTS[k]=True；其余按顺序进 ARGS。"""
    positional, options = [], {}
    for token in tokens:
        if token.startswith('--') and len(token) > 2:
            key, sep, value = token[2:].partition('=')
            options[key.replace('-', '_')] = value if sep else True
        else:
            positional.append(token)
    return positional, options


def _sequence_steps(args):
    name = getattr(args, 'action', None)
    if name is not None:
        if not name or os.path.basename(name) != name or name in ('.', '..'):
            raise ValueError('--action 只接受非空清单名称；路径请使用 --file。')
        path = os.path.join(ACTIONS_DIR, name + '.sequence.json')
    else:
        path = os.path.abspath(args.file)
    with open(path, 'rb') as fp:
        manifest = json.loads(_decode(fp.read()))
        json.dumps(manifest, allow_nan=False)
    if not isinstance(manifest, dict) or set(manifest) != {'steps'} or not isinstance(manifest['steps'], list) or not manifest['steps']:
        raise ValueError('步骤清单必须是非空 {"steps": [...]}。')
    params = {}
    for item in args.param:
        key, sep, value = item.partition('=')
        if not sep or not key or key in params:
            raise ValueError('--param 必须为唯一的 name=value。')
        params[key] = value
    used = set()
    steps = []
    allowed = {'name', 'file', 'action', 'code', 'args', 'options', 'wait_before', 'wait_until', 'state', 'wait'}
    for index, step in enumerate(manifest['steps']):
        if not isinstance(step, dict) or set(step) - allowed:
            raise ValueError('步骤 %d 含未知字段或不是对象。' % (index + 1))
        source = [key for key in ('file', 'action', 'code') if key in step]
        if len(source) != 1 or not isinstance(step[source[0]], str) or not step[source[0]]:
            raise ValueError('步骤 %d 必须指定 file/action/code 之一。' % (index + 1))
        positional, options = step.get('args', []), step.get('options', {})
        seconds = step.get('wait', 60)
        if not isinstance(positional, list) or not isinstance(options, dict) or any(not isinstance(k, str) for k in options):
            raise ValueError('步骤 args 必须是列表，options 必须是字符串键对象。')

        placeholder = r'\{(\w+)(?:=([^{}]*))?\}'

        def value_of(match, number=index + 1):
            key, default = match.group(1), match.group(2)
            used.add(key)
            if key in params:
                return params[key]
            if default is None:
                raise ValueError('步骤 %d 需要 --param %s=<值>。' % (number, key))
            return default

        def fill(value):
            # 整个值写成 "{名字}" 或 "{名字=默认}" 时替换成 --param 的值；没默认值又没传时在启动前报错，不等跑到一半
            match = re.fullmatch(placeholder, value) if isinstance(value, str) else None
            return value_of(match) if match else value

        def fill_expr(expr):
            # 条件表达式：整值是占位符时原样替换（如 hold-until 的 "{until}"），表达式中间的占位符替换成字符串字面量
            match = re.fullmatch(placeholder, expr)
            return value_of(match) if match else re.sub(placeholder, lambda m: repr(value_of(m)), expr)

        positional = [fill(v) for v in positional]
        options = {k: fill(v) for k, v in options.items()}
        step = dict(step, **{key: fill_expr(step[key]) for key in ('wait_before', 'wait_until', 'state') if isinstance(step.get(key), str)})
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 0 <= seconds <= 3600:
            raise ValueError('步骤 wait 必须是 0~3600 的整数秒。')
        for key in ('name', 'wait_before', 'wait_until', 'state'):
            if key in step and (not isinstance(step[key], str) or not step[key]):
                raise ValueError('步骤 %s 必须是非空字符串。' % key)
        kind = source[0]
        filename = '<sequence:%d>' % (index + 1)
        if kind == 'code':
            text = step[kind]
        else:
            if kind == 'action':
                if os.path.basename(step[kind]) != step[kind]:
                    raise ValueError('action 只接受 Skill 入口名；项目脚本使用 file。')
                filename = os.path.join(ACTIONS_DIR, step[kind] + '.py')
            else:
                filename = os.path.abspath(os.path.join(os.path.dirname(path), step[kind]))
            with open(filename, 'rb') as fp:
                text = _decode(fp.read())
        compile(text, filename, 'exec')
        for key in ('wait_before', 'wait_until', 'state'):
            if key in step:
                compile(step[key], '<sequence:%s>' % key, 'eval')
        code = PRELUDE + 'ARGS, OPTS = %r, %r\nexec(compile(%r, %r, "exec"))\n' % (positional, options, text, filename)
        steps.append(dict(step, name=step.get('name', 'step-%d' % (index + 1)), code=code, wait=seconds,
                          parameters=PRELUDE + 'ARGS, OPTS = %r, %r' % (positional, options)))
    unknown = sorted(set(params) - used)
    if unknown:
        raise ValueError('清单里没有步骤用到 --param %s（参数只通过 args/options 里的 "{名字}" 传给脚本）。' % ', '.join(unknown))
    return steps


def _sequence_wait(bridge, step, phase):
    expression = step.get(phase)
    if not expression:
        return {'status': 'ok'}
    begin = time.monotonic()
    result = _poll(bridge, expression, begin + step['wait'])
    if result['status'] == 'ok':
        return {'status': 'ok', 'waited': round(time.monotonic() - begin, 2)}
    if result['status'] != 'timeout':
        return result
    failure = {'status': 'error', 'error_type': 'SequenceWaitTimeout',
               'message': '%s 等待 %ss 后条件仍未成立；未重发操作。' % (step['name'], step['wait']),
               'condition': expression, 'last_condition': result.get('result')}
    if step.get('state'):
        state = bridge.evaluate(step['state'])
        if state['status'] == 'ok':
            failure['last_state'] = str(state.get('result', ''))[:4000]
        else:
            failure['state_error'] = state
    return failure


def _run_sequence(bridge, steps):
    completed = []
    for index, step in enumerate(steps):
        print('[sequence %d/%d] %s' % (index + 1, len(steps), step['name']), file=sys.stderr)
        initial = bridge.execute(step['parameters'])
        if initial['status'] != 'ok':
            return dict(initial, step=step['name'], step_index=index, phase='parameters', completed=completed)
        output = ''
        timings = {}
        for phase in ('wait_before', 'execute', 'wait_until'):
            begin = time.monotonic()
            result = _complete_input(bridge, bridge.execute(step['code'])) if phase == 'execute' else _sequence_wait(bridge, step, phase)
            timings[phase] = round(time.monotonic() - begin, 2)
            if phase == 'execute':
                output = result.get('output', '')[:8000]
            if result['status'] != 'ok':
                if result.get('error_type') == 'ExecutionError' and step.get('state'):
                    state = bridge.evaluate(step['state'])
                    if state['status'] == 'ok':
                        result['last_state'] = str(state.get('result', ''))[:4000]
                    else:
                        result['state_error'] = state
                if 'NameError' in str(result.get('message', '')) and phase != 'execute':
                    result['hint'] = ('条件里用到的函数没有定义。条件只调 lib 模块里的函数（如 ph_market.ready()，'
                                      '模块名会预先绑好不用 import），不要依赖入口脚本里定义的函数')
                # 前面的步骤可能按住了键/鼠标（如 hold-until），中途失败时放开，不让它一直按着
                if any('[input-request]' in c['output'] for c in completed) or '[input-request]' in output:
                    released = bridge.evaluate('unreal.AgentSlateDriverFunctionLib.release_all_input() '
                                               'if hasattr(unreal, "AgentSlateDriverFunctionLib") else ""')
                    result['input_released'] = released['status'] == 'ok'
                return dict(result, step=step['name'], step_index=index, phase=phase,
                            command_sent=phase != 'wait_before', output=output, completed=completed, timings=timings)
        completed.append({'step': step['name'], 'output': output, 'waited': result.get('waited', 0), 'timings': timings})
        print('[timings] before=%ss execute=%ss after=%ss' % (timings['wait_before'], timings['execute'], timings['wait_until']), file=sys.stderr)
    return {'status': 'ok', 'completed': completed}


def cmd_sequence(args):
    try:
        steps = _sequence_steps(args)
    except (OSError, ValueError, SyntaxError) as e:
        _print_json({'status': 'error', 'error_type': 'SequenceFileError', 'message': str(e)})
        sys.exit(1)
    result = _run(args, lambda bridge: _run_sequence(bridge, steps))
    _print_json(result)
    if result['status'] != 'ok':
        sys.exit(1)


def cmd_discover(args):
    bridge = _make_bridge(args)
    result = bridge.discover(timeout=args.timeout or DISCOVER_TIMEOUT)
    _print_json(result)


def cmd_exec(args, tokens):
    src, name = _read_source(args, tokens)
    if src is None:
        sys.exit(1)
    positional, options = _split_script_args(tokens)
    # 先注入参数再以 compile 执行源码：报错行号与脚本一致，模块 docstring 仍会写入 __doc__ 供用法提示
    code = PRELUDE + 'ARGS, OPTS = %r, %r\nexec(compile(%r, %r, "exec"))\n' % (positional, options, src, name)
    result = _run(args, lambda b: _execute_and_wait(b, code, args))
    # 成功时直接输出脚本 print 的文本（省去 JSON 转义，多行可读）；失败时输出 JSON 并以退出码 1 结束
    if result['status'] != 'ok':
        _print_json(result)
        sys.exit(1)
    text = (result.get('output') or '').rstrip('\n')
    if text:
        print(text)
    if 'waited' in result:
        print('[waited %ss]' % result['waited'])
    if 'wait_note' in result:
        print('[warning] ' + result['wait_note'])
    elif not text and 'log' not in result:
        print('[ok]')
    if 'log' in result:
        log = result['log']
        print('[log waited %ss]' % log['waited'])
        print('\n'.join(log['lines']))
        if log['truncated']:
            print('[warning] 日志输出已限量截断。')


def cmd_log(args):
    if args.log_command == 'mark':
        result = ue_log.mark(args.file)
    elif args.log_command == 'read':
        result = ue_log.read(args.file, args.since, args.filter, args.lines)
    else:
        result = ue_log.wait(args.file, args.since, args.text, args.wait, args.lines)
    _print_json(result)
    if result['status'] != 'ok':
        sys.exit(1)


def _widget_rect(args):
    """在编辑器里按 Locator 查控件，返回第 --index 个命中的桌面矩形；失败返回错误 dict。"""
    expr = 'unreal.AgentSlateDriverFunctionLib.find_widgets(%r, %r)' % (args.widget, args.window or '')
    r = _run(args, lambda b: b.evaluate(expr))
    if r['status'] != 'ok':
        return r
    try:
        matches = json.loads(ast.literal_eval(r['result']))
    except (ValueError, SyntaxError):
        return {'status': 'error', 'error_type': 'CommandError', 'message': str(r['result'])}
    if not isinstance(matches, list) or len(matches) <= args.index:
        return {'status': 'error', 'error_type': 'WidgetNotFound',
                'message': f'--widget {args.widget!r} 命中 {len(matches) if isinstance(matches, list) else 0} 个，没有第 {args.index} 个。'}
    return matches[args.index]['rect']


def _pie_viewports(args):
    r = _run(args, lambda b: b.evaluate('unreal.AgentSlateDriverFunctionLib.list_pie_viewports()'))
    if r['status'] != 'ok':
        return r
    try:
        rows = json.loads(ast.literal_eval(r['result']))
        if not isinstance(rows, list):
            raise ValueError('PIE viewport response is not a list')
        return rows
    except (ValueError, SyntaxError) as e:
        return {'status': 'error', 'error_type': 'InvalidResponse', 'message': str(e)}


def _screenshot_out(args):
    if args.out:
        if args.archive:
            raise ValueError('--out 与 --archive 不能同时使用。')
        return args.out
    name = args.name or 'screenshot'
    if name.split('.')[0].upper() in ('CON', 'PRN', 'AUX', 'NUL', *('COM%d' % i for i in range(1, 10)), *('LPT%d' % i for i in range(1, 10))):
        raise ValueError('--name 不能使用 Windows 保留文件名。')
    if name in ('.', '..') or re.search(r'[<>:"/\\\\|?*\x00-\x1f]', name) or name.endswith((' ', '.')):
        raise ValueError('--name 只接受合法文件名，不含路径或扩展名。')
    directory = args.archive or os.path.join(os.getcwd(), '.codebuddy', 'temp', 'ue_screenshots')
    return os.path.join(directory, '%s_%s_%09d.png' % (name, time.strftime('%Y%m%d_%H%M%S'), time.time_ns() % 1000000000))


def cmd_screenshot(args):
    try:
        out = _screenshot_out(args)
    except ValueError as e:
        _print_json({'status': 'error', 'error_type': 'ScreenshotArguments', 'message': str(e)})
        sys.exit(1)
    try:
        import ue_screenshot
    except ImportError as e:
        _print_json({'status': 'error', 'error_type': 'DependencyMissing', 'message': str(e),
                     'suggestion': 'pip install pywin32 pillow'})
        return
    pie = None
    if args.pie:
        rows = _pie_viewports(args)
        if isinstance(rows, dict):
            _print_json(rows)
            sys.exit(1)
        rows = [row for row in rows if (args.instance is None or row['instance'] == args.instance)
                and (not args.window or args.window.lower() in row['window'].lower())]
        if args.list:
            _print_json({'status': 'ok', 'result': rows})
            return
        if len(rows) != 1:
            _print_json({'status': 'error', 'error_type': 'PIEViewportNotFound' if not rows else 'PIEViewportAmbiguous',
                         'message': '需要一个已排布的本进程 PIE 视口；用 --pie --list 查看并用 --instance 选择。', 'viewports': rows})
            sys.exit(1)
        pie = rows[0]
    elif args.instance is not None:
        _print_json({'status': 'error', 'error_type': 'ScreenshotArguments', 'message': '--instance 仅与 --pie 使用。'})
        sys.exit(1)
    elif args.list:
        _print_json({'status': 'ok', 'result': [{'title': w['title'] or '(untitled popup)', 'rect': w['rect']} for w in ue_screenshot.list_windows()]})
        return

    win = None
    # --rect 给的是桌面坐标：选包含该区域的窗口，再换算成窗口内裁剪区域
    rect = pie['rect'] if pie else [int(float(v)) for v in args.rect.split(',')] if args.rect else None
    if args.widget:
        rect = _widget_rect(args)
        if isinstance(rect, dict):
            _print_json(rect)
            return
    if args.popup:
        win = ue_screenshot.top_popup()
        if win is None:
            _print_json({'status': 'error', 'error_type': 'WindowNotFound', 'message': '当前没有打开的弹出菜单/弹出层。'})
            return
    elif rect:
        win = ue_screenshot.window_at(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2)
    if win is None:
        win = ue_screenshot.find_window(args.title)
    if win is None:
        _print_json({'status': 'error', 'error_type': 'WindowNotFound',
                     'message': f'未找到标题包含 {args.title!r} 的 UE 窗口。' if args.title else '未找到 UE 编辑器窗口。',
                     'suggestion': '可用窗口: ' + ', '.join(w['title'] for w in ue_screenshot.list_windows())})
        return

    crop = [int(v) for v in args.crop.split(',')] if args.crop else None
    if rect:
        wl, wt, ww, wh = win['rect']
        left, top = max(rect[0] - wl, 0), max(rect[1] - wt, 0)
        crop = [left, top, min(rect[0] + rect[2] - wl, ww) - left, min(rect[1] + rect[3] - wt, wh) - top]

    if crop and (crop[2] <= 0 or crop[3] <= 0):
        _print_json({'status': 'error', 'error_type': 'CaptureFailed', 'message': '截图区域不在目标窗口内。'})
        sys.exit(1)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    try:
        res = ue_screenshot.capture(win['hwnd'], out, crop=crop, max_width=args.max_width)
    except Exception as e:
        _print_json({'status': 'error', 'error_type': 'CaptureFailed', 'message': str(e)})
        return
    res['window'] = win['title']
    if pie:
        res.update(world=pie['world'], instance=pie['instance'], rect=pie['rect'])
    _print_json(dict(status='ok', **res))


def main():
    # 公共参数定义在 parent_parser，子命令通过 parents 继承，使参数可放在子命令之后
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument('--node', default=None, help='指定连接的 UE 编辑器节点 ID')
    parent_parser.add_argument('--timeout', type=int, default=None, help='等待命令结果的秒数 (默认 30)；discover 下为发现超时 (默认 5)')
    parent_parser.add_argument('--multicast-group', default=None, help='组播地址 (如 239.0.0.1:6766)，默认从项目 ini 自动读取')
    parent_parser.add_argument('--multicast-bind', default=None, help='组播绑定地址 (如 127.0.0.1)，默认从项目 ini 自动读取')

    parser = argparse.ArgumentParser(description='UE Editor CLI')
    sub = parser.add_subparsers(dest='subcommand', required=True)

    # discover
    sub.add_parser('discover', parents=[parent_parser], help='发现本地 UE 编辑器实例')

    # sequence
    p_sequence = sub.add_parser('sequence', parents=[parent_parser], allow_abbrev=False, help='执行通用跨帧步骤清单')

    # 清单来源
    sequence_source = p_sequence.add_mutually_exclusive_group(required=True)
    sequence_source.add_argument('--file', default=None, help='JSON 步骤清单路径，脚本相对路径以此文件为基准')
    sequence_source.add_argument('--action', default=None, help='读取 scripts/actions/<名称>.sequence.json 内置步骤清单')

    # 流程参数
    p_sequence.add_argument('--param', action='append', default=[], help='可重复的 name=value，替换步骤 args/options 里的 "{name}"')

    # exec：代码来源四选一；CLI 不认识的参数都传给脚本（--k=v / --k 进 OPTS，其余进 ARGS）
    # 关闭前缀匹配，避免脚本参数（如 --fi）被误认成 CLI 参数
    p_exec = sub.add_parser('exec', parents=[parent_parser], allow_abbrev=False,
                            help='在编辑器内执行 Python：内联代码 / --file / --action / --stdin')

    # 代码来源
    source = p_exec.add_mutually_exclusive_group()
    source.add_argument('--file', default=None, help='执行本地 .py 文件（UTF-8，可含中文）')
    source.add_argument('--action', default=None, help='执行 scripts/actions/<name>.py 入口脚本，用法见脚本 docstring')
    source.add_argument('--stdin', action='store_true', help='从 stdin 管道读取代码')

    # 执行后等待
    condition = p_exec.add_mutually_exclusive_group()
    condition.add_argument('--wait-until', default=None, help='执行成功后跨帧轮询该 Python 表达式，直到为真（如 PIE 启动完成）')
    condition.add_argument('--wait-log', default=None, help='执行前取日志基线，执行后等待新增完整行包含该关键词')
    p_exec.add_argument('--log-file', default=None, help='--wait-log 的本地 UTF-8 日志路径')
    p_exec.add_argument('--log-lines', type=int, default=40, help='匹配日志/超时近期日志最多输出行数 (1~200，默认 40)')
    p_exec.add_argument('--wait', type=int, default=60, help='--wait-until / --wait-log 的最长等待秒数 (默认 60)')

    # log
    p_log = sub.add_parser('log', allow_abbrev=False, help='本地日志基线、读取与等待，不连接编辑器')
    log_sub = p_log.add_subparsers(dest='log_command', required=True)

    p_mark = log_sub.add_parser('mark', allow_abbrev=False, help='记录当前日志末尾基线')
    p_mark.add_argument('--file', required=True, help='本地 UTF-8 日志路径')

    p_read = log_sub.add_parser('read', allow_abbrev=False, help='增量读取；不带基线时读取近期日志')
    p_read.add_argument('--file', required=True, help='本地 UTF-8 日志路径')
    p_read.add_argument('--since', default=None, help='mark/read 返回的 cursor')
    p_read.add_argument('--filter', default='', help='区分大小写的字面关键词，不使用正则')
    p_read.add_argument('--lines', type=int, default=80, help='最多输出行数 (1~200，默认 80)')

    p_wait = log_sub.add_parser('wait', allow_abbrev=False, help='从指定基线等待新增匹配日志')
    p_wait.add_argument('--file', required=True, help='本地 UTF-8 日志路径')
    p_wait.add_argument('--since', required=True, help='操作前 mark 返回的 cursor')
    p_wait.add_argument('--text', required=True, help='完整行中需出现的字面关键词')
    p_wait.add_argument('--wait', type=int, default=60, help='最长等待秒数 (默认 60)')
    p_wait.add_argument('--lines', type=int, default=40, help='最多输出行数 (1~200，默认 40)')

    # screenshot
    p_ss = sub.add_parser('screenshot', parents=[parent_parser], help='截取 UE 编辑器窗口（Win32 抓取，不阻塞编辑器）')

    # 截图目标
    p_ss.add_argument('--title', default=None, help='按窗口标题子串选择窗口（如 PIE 独立窗口）')
    screenshot_target = p_ss.add_mutually_exclusive_group()
    screenshot_target.add_argument('--rect', default=None, help='只截桌面坐标区域 x,y,w,h（与 AgentSlateDriver 返回的 rect 一致）')
    screenshot_target.add_argument('--popup', action='store_true', help='截最上层的弹出菜单/弹出层（打开菜单后直接截）')
    screenshot_target.add_argument('--pie', action='store_true', help='只截当前进程 PIE 视口（需重编 AgentTools）')
    p_ss.add_argument('--instance', type=int, default=None, help='--pie 选择 PIE 实例编号；多个视口时必选')
    p_ss.add_argument('--list', action='store_true', help='仅列出可截取的 UE 窗口')

    # 控件定位
    screenshot_target.add_argument('--widget', default=None, help='按 Locator 查控件并只截它（需 AgentTools），如 --widget="type=SContentBrowser"')
    p_ss.add_argument('--index', type=int, default=0, help='--widget 命中多个时取第几个 (默认 0)')
    p_ss.add_argument('--window', default=None, help='--widget 只在标题包含该子串的独立窗口里查找')

    # 输出处理
    screenshot_output = p_ss.add_mutually_exclusive_group()
    screenshot_output.add_argument('--out', default=None, help='精确输出 PNG 路径')
    screenshot_output.add_argument('--name', default=None, help='语义文件名，自动追加时间戳和 .png')
    p_ss.add_argument('--archive', default=None, help='直接输出到该证据目录，不再复制归档')
    p_ss.add_argument('--crop', default=None, help='裁剪区域 x,y,w,h（相对窗口的原始像素）')
    p_ss.add_argument('--max-width', type=int, default=1600, help='保存前缩放到的最大宽度，0 为不缩放 (默认 1600)')

    # 参数解析与命令分派
    args, extra = parser.parse_known_args()
    if args.subcommand == 'exec':
        cmd_exec(args, extra)
        return
    if extra:
        parser.error('unrecognized arguments: ' + ' '.join(extra))
    {'discover': cmd_discover, 'screenshot': cmd_screenshot, 'log': cmd_log, 'sequence': cmd_sequence}[args.subcommand](args)


if __name__ == '__main__':
    main()
