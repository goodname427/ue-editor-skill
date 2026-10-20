"""本地日志基线、增量读取与等待；UTF-8 完整行，游标失效时明确报错。"""
import collections
import hashlib
import math
import os
import time

MAX_SCAN_BYTES = 1024 * 1024
MAX_OUTPUT_CHARS = 12000
MAX_LINE_CHARS = 2000


def _error(kind, message):
    return {'status': 'error', 'error_type': kind, 'message': message}


def _digest(fp, start, size):
    fp.seek(start)
    return hashlib.blake2s(fp.read(size), digest_size=8).hexdigest()


def _cursor(fp, offset, skip):
    stat = os.fstat(fp.fileno())
    if stat.st_size < offset:
        raise RuntimeError('日志已截断；旧基线失效，请重新取基线。')
    size = min(offset, 64)
    head = _digest(fp, 0, size)
    tail = _digest(fp, offset - size, size)
    return '1:%d:%d:%d:%d:%s:%s' % (stat.st_dev, stat.st_ino, offset, skip, head, tail)


def _parse_cursor(token):
    fields = token.split(':')
    if len(fields) != 7 or fields[0] != '1':
        raise ValueError('无效日志游标；使用 log mark/read 返回的 cursor。')
    device, inode, offset, skip = (int(value) for value in fields[1:5])
    if min(device, inode, offset) < 0 or skip not in (0, 1):
        raise ValueError('无效日志游标位置。')
    for digest in fields[5:]:
        if len(digest) != 16 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('无效日志游标校验值。')
    return device, inode, offset, skip, fields[5], fields[6]


def _verify(fp, path, state):
    device, inode, offset, skip, head, tail = state
    opened = os.fstat(fp.fileno())
    current = os.stat(path)
    if (opened.st_dev, opened.st_ino) != (device, inode) or (current.st_dev, current.st_ino) != (device, inode):
        raise RuntimeError('日志已轮转或游标属于另一文件；请重新取基线。')
    if opened.st_size < offset:
        raise RuntimeError('日志已截断；旧基线失效，请重新取基线。')
    size = min(offset, 64)
    if _digest(fp, 0, size) != head or _digest(fp, offset - size, size) != tail:
        raise RuntimeError('基线附近内容已改写，可能发生截断后重写；请重新取基线。')


def _bounded(rows):
    out, chars, trimmed = [], 0, False
    for line in reversed(rows):
        if len(line) > MAX_LINE_CHARS:
            suffix = ' ... [line truncated]'
            line = line[:MAX_LINE_CHARS - len(suffix)] + suffix
            trimmed = True
        if chars + len(line) + 1 > MAX_OUTPUT_CHARS:
            trimmed = True
            break
        out.append(line)
        chars += len(line) + 1
    return list(reversed(out)), trimmed


def mark(path):
    try:
        path = os.path.abspath(path)
        with open(path, 'rb', buffering=0) as fp:
            stat = os.fstat(fp.fileno())
            offset = stat.st_size
            fp.seek(max(0, offset - 1))
            skip = int(offset > 0 and fp.read(1) != b'\n')
            token = _cursor(fp, offset, skip)
            _verify(fp, path, _parse_cursor(token))
        return {'status': 'ok', 'file': path, 'cursor': token, 'offset': offset, 'partial_line': bool(skip)}
    except RuntimeError as e:
        return _error('LogChanged', str(e))
    except OSError as e:
        return _error('LogFileError', str(e))


def read(path, since=None, filter_text='', max_lines=80, match_text=None):
    if not 1 <= max_lines <= 200:
        return _error('LogArguments', 'lines 必须在 1~200 之间。')
    try:
        path = os.path.abspath(path)
        with open(path, 'rb', buffering=0) as fp:
            end = os.fstat(fp.fileno()).st_size
            end_state = _parse_cursor(_cursor(fp, end, 0))
            full_history = since is None and bool(filter_text)
            if since is None:
                offset = 0 if full_history else max(0, end - MAX_SCAN_BYTES)
                fp.seek(max(0, offset - 1))
                skip = int(offset > 0 and fp.read(1) != b'\n')
                since = _cursor(fp, offset, skip)
                history_truncated = offset > 0
            else:
                history_truncated = False
            state = _parse_cursor(since)
            _verify(fp, path, state)
            offset, skip = state[2:4]
            rows, matches = collections.deque(maxlen=max_lines), collections.deque(maxlen=max_lines)
            count, match_count, scanned_lines, consumed, pending_bytes, scanned_bytes = 0, 0, 0, 0, 0, 0
            filter_bytes = filter_text.encode('utf-8')
            match_bytes = match_text.encode('utf-8') if match_text is not None else None
            tail_size = max(len(filter_bytes), len(match_bytes or b''), 1) - 1
            tail, preview = b'', b''
            line_matches, wait_matches = not filter_bytes, False
            fp.seek(offset)
            while True:
                data = fp.read(min(MAX_SCAN_BYTES, end - offset - scanned_bytes))
                if not data and scanned_bytes < end - offset:
                    raise RuntimeError('扫描期间日志已截断；请重新取基线。')
                scanned_bytes += len(data)
                parts = data.split(b'\n')
                for index, raw in enumerate(parts):
                    probe = tail + raw
                    line_matches = line_matches or filter_bytes in probe
                    wait_matches = wait_matches or (match_bytes is not None and match_bytes in probe)
                    preview += raw[:max(0, MAX_LINE_CHARS * 4 - len(preview))]
                    pending_bytes += len(raw)
                    tail = probe[-tail_size:] if tail_size else b''
                    if index == len(parts) - 1:
                        break
                    if not skip:
                        scanned_lines += 1
                        line = preview.decode('utf-8-sig', errors='replace').rstrip('\r')
                        if pending_bytes > len(preview):
                            line += ' ... [line truncated]'
                        if line_matches:
                            rows.append(line)
                            count += 1
                        if wait_matches:
                            matches.append(line)
                            match_count += 1
                    skip = 0
                    consumed += pending_bytes + 1
                    pending_bytes = 0
                    tail, preview = b'', b''
                    line_matches, wait_matches = not filter_bytes, False
                if not full_history or scanned_bytes >= end - offset:
                    break
            if pending_bytes >= MAX_SCAN_BYTES:
                return _error('LogLineTooLong', '未换行的单行超过 1 MiB，无法安全推进完整行游标。')
            _verify(fp, path, state)
            _verify(fp, path, end_state)
            token = _cursor(fp, offset + consumed, skip)
        lines, trimmed = _bounded(rows)
        result = {'status': 'ok', 'file': path, 'cursor': token, 'lines': lines,
                  'line_count': count, 'truncated': history_truncated or count > len(lines) or trimmed,
                  'scan_truncated': end - offset > consumed + pending_bytes, 'pending_bytes': pending_bytes,
                  'start_offset': offset, 'end_offset': offset + consumed, 'file_size': end,
                  'scanned_lines': scanned_lines, 'scan_from_line': 1 if offset == 0 else None,
                  'history_truncated': history_truncated}
        if count == 0 and (history_truncated or result['scan_truncated'] or pending_bytes):
            result['note'] = '仅搜索字节区间 [%d, %d) 的 %d 个完整行；零匹配不代表全日志没有。' % (offset, offset + consumed, scanned_lines)
        if match_text is not None:
            match_lines, match_trimmed = _bounded(matches)
            result.update(matched=match_count > 0, match_lines=match_lines,
                          match_truncated=match_count > len(match_lines) or match_trimmed)
        return result
    except (ValueError, AttributeError) as e:
        return _error('LogCursorInvalid', str(e))
    except RuntimeError as e:
        return _error('LogChanged', str(e))
    except FileNotFoundError as e:
        return _error('LogChanged' if since is not None else 'LogFileError', str(e))
    except OSError as e:
        return _error('LogFileError', str(e))


def wait(path, since, text, seconds=60, max_lines=40):
    if not since or not text or not math.isfinite(seconds) or seconds < 0 or not 1 <= max_lines <= 200:
        return _error('LogArguments', '等待日志需要非空 since/text、有限非负 wait 和 1~200 lines。')
    begin = time.monotonic()
    cursor = since
    recent = collections.deque(maxlen=max_lines)
    truncated = False
    while True:
        result = read(path, cursor, max_lines=max_lines, match_text=text)
        if result['status'] != 'ok':
            result.update(cursor=cursor, lines=_bounded(recent)[0], waited=round(time.monotonic() - begin, 2))
            return result
        cursor = result['cursor']
        truncated = truncated or result['truncated'] or len(recent) + len(result['lines']) > max_lines
        recent.extend(result['lines'])
        elapsed = time.monotonic() - begin
        if result['matched']:
            return {'status': 'ok', 'file': result['file'], 'cursor': cursor, 'matched': True,
                    'lines': result['match_lines'], 'truncated': result['match_truncated'], 'waited': round(elapsed, 2)}
        if elapsed >= seconds:
            lines, trimmed = _bounded(recent)
            return dict(_error('LogWaitTimeout', '%ss 内没有新增日志包含 %r；未重发任何操作。' % (seconds, text)),
                        file=result['file'], cursor=cursor, lines=lines, truncated=truncated or trimmed,
                        waited=round(elapsed, 2))
        if not result['scan_truncated']:
            time.sleep(min(0.2, seconds - elapsed))
