"""本地CDP对象检查；不导入业务模块、不暂停运行时、不调用对象getter或方法。"""
import ipaddress
import json
import math
import re
import time
import uuid
from urllib.parse import urlsplit
from lib import ue_projection


class InspectorError(Exception):
    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind


def validate_url(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'ws' or not parsed.hostname or not ipaddress.ip_address(parsed.hostname).is_loopback
                or not parsed.port or parsed.username or parsed.password or parsed.fragment):
            raise ValueError()
    except ValueError:
        raise InspectorError('InspectorArguments', 'Use an explicit loopback ws:// IP endpoint with a port; no remote hosts, credentials or fragments')
    return url


class InspectorSession:
    def __init__(self, url, timeout):
        self.url = validate_url(url)
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 60:
            raise InspectorError('InspectorArguments', 'timeout must be finite and in 1..60 seconds')
        self.deadline = time.monotonic() + timeout
        self.query_deadline = self.deadline - min(1, timeout / 4)
        self.socket = None
        self.sequence = 0
        self.contexts = {}
        self.group = 'agent-inspect-' + uuid.uuid4().hex
        self.group_used = False
        self.requests = 0
        self.exchanges = 0
        self.outstanding = set()

    def remaining(self, cleanup=False):
        remaining = (self.deadline if cleanup else self.query_deadline) - time.monotonic()
        if remaining <= 0:
            raise InspectorError('InspectorTimeout', 'Overall inspector time budget exhausted; no retry or resume performed')
        return remaining

    def connect(self):
        try:
            import websocket
        except ImportError:
            raise InspectorError('DependencyMissing', 'Install optional dependency: python -m pip install websocket-client==1.8.0')
        try:
            self.socket = websocket.create_connection(self.url, timeout=self.remaining(), suppress_origin=True,
                                                      http_no_proxy=['*'], redirect_limit=0)
        except Exception as error:
            raise InspectorError('InspectorConnection', str(error))

    def request(self, method, params=None, cleanup=False):
        return self._exchange([(method, params or {})], cleanup)[0]

    def properties_batch(self, object_ids):
        if (not isinstance(object_ids, (tuple, list)) or not 1 <= len(object_ids) <= 32
                or any(not isinstance(i, str) or not i or len(i) > 4096 for i in object_ids)):
            raise InspectorError('InspectorArguments', 'Property batch requires 1..32 explicit object IDs')
        return self._exchange([('Runtime.getProperties', {'objectId': i, 'ownProperties': True,
                                                         'generatePreview': False}) for i in object_ids])

    def _exchange(self, commands, cleanup=False):
        self.remaining(cleanup)
        self.exchanges += 1
        ids, replies = [], {}
        try:
            for method, params in commands:
                self.sequence += 1
                request_id = self.sequence
                ids.append(request_id)
                self.outstanding.add(request_id)
                self.socket.settimeout(self.remaining(cleanup))
                self.socket.send(json.dumps({'id': request_id, 'method': method, 'params': params}))
                self.requests += 1
            pending = set(ids)
            received_bytes = 0
            for _ in range(20000):
                self.socket.settimeout(self.remaining(cleanup))
                raw = self.socket.recv()
                size = len(raw.encode('utf-8')) if isinstance(raw, str) else 0
                received_bytes += size
                if not isinstance(raw, str) or not raw or size > 2 * 1024 * 1024:
                    raise InspectorError('InspectorResponse', 'Empty, non-text or oversized CDP response (maximum 2 MiB)')
                if received_bytes > 32 * 1024 * 1024:
                    raise InspectorError('InspectorResponse', 'CDP response/notification stream exceeds 32 MiB per exchange')
                reply = json.loads(raw)
                if 'id' in reply:
                    response_id = reply['id']
                    if response_id not in pending:
                        if cleanup and response_id in self.outstanding:
                            self.outstanding.remove(response_id)
                            continue
                        raise InspectorError('InspectorResponse', 'Unexpected or duplicate response ID')
                    self.outstanding.discard(response_id)
                    pending.remove(response_id)
                    if 'error' in reply:
                        raise InspectorError('InspectorProtocol', str(reply['error']))
                    if not isinstance(reply.get('result'), dict):
                        raise InspectorError('InspectorResponse', 'Missing or invalid response result')
                    replies[response_id] = reply['result']
                    if not pending:
                        return [replies[i] for i in ids]
                elif reply.get('method') == 'Runtime.executionContextCreated':
                    context = reply['params']['context']
                    self.contexts[context['id']] = context
                elif reply.get('method') == 'Runtime.executionContextDestroyed':
                    self.contexts.pop(reply['params']['executionContextId'], None)
                elif reply.get('method') == 'Runtime.executionContextsCleared':
                    self.contexts.clear()
            raise InspectorError('InspectorResponse', 'Too many notifications before requested response')
        except InspectorError:
            raise
        except Exception as error:
            raise InspectorError('InspectorTransport', str(error))

    def evaluate(self, expression, context):
        self.group_used = True
        result = self.request('Runtime.evaluate', {'expression': expression, 'contextId': context,
                              'objectGroup': self.group, 'returnByValue': False, 'awaitPromise': False,
                              'throwOnSideEffect': True, 'timeout': max(1, int(self.remaining() * 1000))})
        if result.get('exceptionDetails'):
            details = result['exceptionDetails']
            raise InspectorError('InspectorEvaluation', details.get('exception', {}).get('description', details.get('text', 'Evaluation refused')))
        if 'result' not in result:
            raise InspectorError('InspectorResponse', 'Missing evaluation result')
        return result['result']

    def close(self):
        cleanup = {'object_group': 'not_created', 'connection_closed': True}
        if self.socket is None:
            return cleanup
        try:
            if self.group_used:
                try:
                    self.request('Runtime.releaseObjectGroup', {'objectGroup': self.group}, cleanup=True)
                    cleanup['object_group'] = 'released'
                except Exception as error:
                    cleanup.update(object_group='unconfirmed', error=str(error))
        finally:
            try:
                self.socket.close(timeout=max(0, min(0.2, self.deadline - time.monotonic())))
            except Exception as error:
                cleanup.update(connection_closed=False, connection_error=str(error))
            self.socket = None
        return cleanup


class ObjectReader:
    def __init__(self, session, depth, offset, limit):
        self.session = session
        self.depth = depth
        self.offset = offset
        self.limit = limit
        self.cache = {}
        self.seen = {}
        self.budget = 200

    def properties(self, obj):
        if obj.get('subtype') in ('proxy', 'map', 'set', 'weakmap', 'weakset'):
            raise InspectorError('InspectorReadRefused', 'Collection/Proxy expansion is not supported; no traps/getters executed by this reader')
        object_id = obj.get('objectId')
        if not object_id:
            raise InspectorError('InspectorReadRefused', 'Path requires an inspectable object')
        if object_id not in self.cache:
            response = self.session.request('Runtime.getProperties', {'objectId': object_id, 'ownProperties': True,
                                                                     'generatePreview': False})
            if response.get('exceptionDetails'):
                raise InspectorError('InspectorReadRefused', 'Property enumeration raised an exception')
            self.cache[object_id] = response.get('result', [])
        return self.cache[object_id]

    def prefetch(self, objects):
        missing = {}
        for obj in objects:
            object_id = obj.get('objectId')
            if (object_id and object_id not in self.cache and obj.get('type') == 'object'
                    and obj.get('subtype') in (None, 'array')):
                missing[object_id] = obj
        if len(self.cache) + len(missing) > 1000:
            raise InspectorError('InspectorProjectionLimit', 'Projection exceeds 1000 distinct descriptor objects; narrow fields/sample')
        ids = list(missing)
        for start in range(0, len(ids), 32):
            batch = ids[start:start + 32]
            responses = self.session.properties_batch(batch)
            for object_id, response in zip(batch, responses):
                if response.get('exceptionDetails') or not isinstance(response.get('result'), list):
                    raise InspectorError('InspectorReadRefused', 'Batched property enumeration failed; no partial projection reported complete')
                self.cache[object_id] = response['result']

    def project(self, array, fields):
        try:
            fields = ue_projection.validate_fields(fields)
        except ue_projection.ProjectionError as error:
            raise InspectorError('InspectorArguments', str(error))
        if not isinstance(self.limit, int) or isinstance(self.limit, bool) or not 1 <= self.limit <= 500:
            raise InspectorError('InspectorArguments', 'Projection limit must be in 1..500')
        if array.get('type') != 'object' or array.get('subtype') != 'array':
            raise InspectorError('InspectorReadRefused', 'Projection requires an existing ordinary array')
        props = self.properties(array)
        length = next((p.get('value', {}).get('value') for p in props if p.get('name') == 'length'), None)
        if isinstance(length, bool) or not isinstance(length, int) or length < 0:
            raise InspectorError('InspectorResponse', 'Array length unavailable')
        indexed = {p['name']: p for p in props if not p.get('symbol') and re.fullmatch(r'0|[1-9][0-9]*', p.get('name', ''))
                   and int(p['name']) < 4294967295}
        records, pending = [], []
        for index in range(self.offset, min(length, self.offset + self.limit)):
            row = ue_projection.new_record(index)
            records.append(row)
            prop = indexed.get(str(index))
            if prop is None:
                row['state'] = 'hole'
            elif 'value' not in prop:
                row.update(state='accessor', row_error='Array item is an accessor; not invoked')
            else:
                row['state'] = 'present'
                for pointer in fields:
                    pending.append((row, pointer, prop['value'], pointer[1:].split('/')))
        while pending:
            self.prefetch([obj for _, _, obj, _ in pending])
            following = []
            for row, pointer, obj, segments in pending:
                try:
                    if obj.get('type') != 'object' or obj.get('subtype') not in (None, 'array'):
                        raise InspectorError('InspectorReadRefused', 'Projection traverses ordinary own data only; no functions, collections or Proxy')
                    value = self.follow(obj, '/' + segments[0])
                    if len(segments) > 1:
                        following.append((row, pointer, value, segments[1:]))
                    elif value.get('objectId') or value.get('type') in ('object', 'function', 'symbol') and value.get('subtype') != 'null':
                        raise InspectorError('InspectorReadRefused', 'Projected field must be a scalar/null; select a deeper data field')
                    else:
                        row['fields'][pointer] = {k: value[k] for k in ('type', 'subtype', 'value', 'unserializableValue') if k in value}
                        if isinstance(value.get('value'), str) and len(value['value']) > 512:
                            row['fields'][pointer].update(value=value['value'][:512], value_truncated=True, length=len(value['value']))
                except InspectorError as error:
                    if error.kind not in ('InspectorPathMissing', 'InspectorReadRefused'):
                        raise
                    ue_projection.field_error(row, pointer, error.kind, error)
            pending = following
        try:
            result = ue_projection.finish(records, fields, length, self.offset, self.limit, 'cdp')
        except ue_projection.ProjectionError as error:
            raise InspectorError('InspectorOutputLimit', str(error))
        result.update(non_index_properties_omitted=len(props) - len(indexed) - 1,
                      coverage='Explicit scalar own-data fields of sampled array indices; holes and refusals retained, non-atomic. No getters, calls or pause.')
        return result

    def scopes(self, function):
        if function.get('type') != 'function' or function.get('subtype') == 'proxy' or not function.get('objectId'):
            raise InspectorError('InspectorScopeRefused', 'Scope inspection requires an existing non-Proxy function reference')
        response = self.session.request('Runtime.getProperties', {'objectId': function['objectId'], 'ownProperties': True,
                                                                 'generatePreview': False})
        if response.get('exceptionDetails'):
            raise InspectorError('InspectorScopeRefused', 'Function descriptor inspection failed')
        scopes = [p.get('value', {}) for p in response.get('internalProperties', []) if p.get('name') == '[[Scopes]]']
        if (len(scopes) != 1 or scopes[0].get('type') != 'object'
                or scopes[0].get('subtype') != 'internal#scopeList' or not scopes[0].get('objectId')):
            raise InspectorError('InspectorScopesUnavailable', 'Runtime did not expose a scope list for this function; no fallback invocation')
        return scopes[0]

    def follow_scope(self, function, path):
        index, separator, tail = path[1:].partition('/')
        scope = self.follow(self.scopes(function), '/' + index)
        if scope.get('type') != 'object' or scope.get('subtype') != 'internal#scope' or not scope.get('objectId'):
            raise InspectorError('InspectorScopeRefused', 'Selected entry is not an inspectable runtime scope')
        return self.follow(scope, '/' + tail if separator else '')

    def scope_summary(self, function):
        scopes = self.scopes(function)
        props = self.properties(scopes)
        indexed = sorted((p for p in props if re.fullmatch(r'0|[1-9][0-9]*', p.get('name', '')) and not p.get('symbol')),
                         key=lambda p: int(p['name']))
        selected = indexed[self.offset:self.offset + min(self.limit, 32)]
        values = [{'index': int(p['name']), 'description': p.get('value', {}).get('description', '')[:160],
                   'available': p.get('value', {}).get('type') == 'object'
                                and p.get('value', {}).get('subtype') == 'internal#scope'
                                and bool(p.get('value', {}).get('objectId'))} for p in selected]
        return {'kind': 'scopes', 'scopes': values, 'scope_count': len(indexed),
                'scopes_truncated': self.offset > 0 or self.offset + len(values) < len(indexed),
                'coverage': 'Runtime-exposed function scopes only; indices are session-local, no variable values or function calls.'}

    def follow(self, root, path):
        if not path:
            return root
        if not path.startswith('/'):
            raise InspectorError('InspectorArguments', 'path must be a JSON pointer such as /items/0/name')
        segments = path[1:].split('/')
        if len(segments) > 16:
            raise InspectorError('InspectorArguments', 'path has more than 16 segments')
        for segment in segments:
            name = segment.replace('~1', '/').replace('~0', '~')
            matches = [p for p in self.properties(root) if p.get('name') == name and not p.get('symbol')]
            if len(matches) != 1:
                raise InspectorError('InspectorPathMissing', 'Own property not found: ' + name)
            prop = matches[0]
            if 'value' not in prop:
                raise InspectorError('InspectorReadRefused', 'Accessor or unavailable property: ' + name)
            root = prop['value']
        return root

    def read(self, obj, depth=None, path=''):
        depth = self.depth if depth is None else depth
        self.budget -= 1
        result = {k: obj[k] for k in ('type', 'subtype', 'className', 'unserializableValue') if k in obj}
        if 'value' in obj:
            value = obj['value']
            result['value'] = value[:512] if isinstance(value, str) else value
            if isinstance(value, str) and len(value) > 512:
                result.update(value_truncated=True, length=len(value))
        if 'description' in obj and 'value' not in obj:
            result['description'] = obj['description'][:160]
        object_id = obj.get('objectId')
        if not object_id or obj.get('type') == 'function':
            return result
        if object_id in self.seen:
            return dict(result, reference=self.seen[object_id])
        if depth == 0 or self.budget <= 0:
            return dict(result, expansion='depth_or_node_limit')
        if obj.get('subtype') in ('proxy', 'map', 'set', 'weakmap', 'weakset'):
            return dict(result, expansion='unsupported_collection_or_proxy')
        self.seen[object_id] = path
        props = self.properties(obj)
        if obj.get('subtype') == 'array':
            length = next((p.get('value', {}).get('value') for p in props if p.get('name') == 'length'), None)
            if isinstance(length, bool) or not isinstance(length, int) or length < 0:
                raise InspectorError('InspectorResponse', 'Array length unavailable')
            indexed = [p for p in props if not p.get('symbol') and re.fullmatch(r'0|[1-9][0-9]*', p.get('name', ''))
                       and int(p['name']) < 4294967295]
            result.update(length=length, non_index_properties_omitted=len(props) - len(indexed) - 1,
                          property_coverage='Array index data/accessor descriptors only; holes are not present properties')
            omitted = self.offset > 0 or self.offset + self.limit < length
            props = sorted((p for p in indexed if self.offset <= int(p['name']) < self.offset + self.limit), key=lambda p: int(p['name']))
        else:
            omitted = self.offset > 0 or len(props) > self.offset + self.limit
            props = props[self.offset:self.offset + self.limit]
        values = []
        for prop in props:
            if self.budget <= 0:
                break
            item = {'name': prop['name']}
            if prop.get('symbol'):
                item['symbol'] = True
            if 'value' in prop:
                child_path = path + '/' + prop['name'].replace('~', '~0').replace('/', '~1')
                item['data'] = self.read(prop['value'], depth - 1, child_path)
            else:
                item.update(accessor=True, getter='get' in prop and prop['get'].get('type') == 'function',
                            setter='set' in prop and prop['set'].get('type') == 'function')
                self.budget -= 1
            values.append(item)
        result.update(properties=values, offset=self.offset, limit=self.limit,
                      properties_truncated=omitted or len(values) < len(props))
        return result


def inspect(url, expression=None, context_id=None, path='', depth=1, offset=0, limit=20, timeout=8,
            scope_paths=(), list_scopes=False, project_fields=()):
    session = None
    result = {'status': 'error'}
    try:
        try:
            project_fields = ue_projection.validate_fields(project_fields, allow_empty=True)
        except ue_projection.ProjectionError as error:
            raise InspectorError('InspectorArguments', str(error))
        if project_fields and (list_scopes or expression is None):
            raise InspectorError('InspectorArguments', 'Projection fields must be unique and require an array reference, not a scopes/context listing')
        max_limit = 500 if project_fields else 100
        if (any(isinstance(n, bool) for n in (depth, offset, limit)) or not isinstance(depth, int) or not 0 <= depth <= 3
                or not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= max_limit):
            raise InspectorError('InspectorArguments', 'depth in 0..3, offset nonnegative, limit in 1..%d' % max_limit)
        if context_id is not None and (isinstance(context_id, bool) or not isinstance(context_id, int) or context_id <= 0):
            raise InspectorError('InspectorArguments', 'context must be a positive integer')
        if expression is not None and (not isinstance(expression, str) or len(expression) > 4096
                or not re.fullmatch(r'[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*|\[(?:[0-9]+|"(?:[^"\\\r\n]|\\.)*")\])*', expression)):
            raise InspectorError('InspectorArguments', 'Use only an existing global reference/property path; calls, assignments and arbitrary code are not accepted')
        if not isinstance(scope_paths, (tuple, list)) or len(scope_paths) > 4 or not isinstance(list_scopes, bool):
            raise InspectorError('InspectorArguments', 'At most four explicit scope paths are supported')
        for pointer in (path, *scope_paths):
            if (not isinstance(pointer, str) or (pointer and not pointer.startswith('/')) or len(pointer) > 4096
                    or (pointer and len(pointer[1:].split('/')) > 16) or re.search(r'~(?![01])', pointer)):
                raise InspectorError('InspectorArguments', 'path must be a valid JSON pointer up to 4096 characters and 16 segments')
        if any(not re.match(r'^/(?:0|[1-9][0-9]*)(?:/|$)', p) for p in scope_paths):
            raise InspectorError('InspectorArguments', 'Each scope path must begin with an explicit scope index')
        if (scope_paths or list_scopes) and expression is None:
            raise InspectorError('InspectorArguments', 'Scope inspection requires a function reference')
        if list_scopes and path:
            raise InspectorError('InspectorArguments', 'scopes lists labels only; use scope-path to select a function')
        reference = ''
        if expression is not None:
            names = []
            for match in re.finditer(r'[A-Za-z_$][A-Za-z0-9_$]*|\[([0-9]+|"(?:[^"\\\r\n]|\\.)*")\]', expression):
                token = match.group(1) or match.group(0)
                names.append(json.loads(token) if token.startswith('"') else token)
            if names and names[0] == 'globalThis':
                names = names[1:]
            if len(names) > 16:
                raise InspectorError('InspectorArguments', 'Root reference has more than 16 segments')
            reference = ''.join('/' + name.replace('~', '~0').replace('/', '~1') for name in names)
        session = InspectorSession(url, timeout)
        session.connect()
        session.request('Runtime.enable')
        contexts = list(session.contexts.values())
        if expression is None:
            result = {'status': 'ok', 'contexts': contexts}
        else:
            if not isinstance(expression, str) or not expression.strip() or len(expression) > 4096:
                raise InspectorError('InspectorArguments', 'A nonempty expression up to 4096 characters is required')
            selected = context_id
            if selected is None:
                if len(contexts) != 1:
                    raise InspectorError('InspectorContextRequired', 'Select an execution context; no unique context available')
                selected = contexts[0]['id']
            if selected not in session.contexts:
                raise InspectorError('InspectorContextMissing', 'Requested context not available')
            reader = ObjectReader(session, depth, offset, limit)
            root = reader.follow(session.evaluate('globalThis', selected), reference)
            for scope_path in scope_paths:
                root = reader.follow_scope(root, scope_path)
            if list_scopes:
                result = dict(status='ok', context=selected, scope_paths=list(scope_paths), **reader.scope_summary(root))
            else:
                root = reader.follow(root, path)
                result = {'status': 'ok', 'context': selected, 'path': path, 'scope_paths': list(scope_paths),
                          'data': reader.project(root, project_fields) if project_fields else reader.read(root),
                          'coverage': 'Own data descriptors and explicitly selected runtime scopes only, bounded and non-atomic; no getters, module loading, business calls or pause/resume. Map/Set/Proxy expansion not supported.'}
        if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 65536:
            raise InspectorError('InspectorOutputLimit', 'Output exceeds 64 KiB; narrow path/depth/sample. No partial result reported as complete.')
    except InspectorError as error:
        result = {'status': 'error', 'error_type': error.kind, 'message': str(error)[:1024]}
        if session:
            contexts = list(session.contexts.values())
            result['contexts'] = [{k: (v[:128] if isinstance(v, str) else v) for k, v in c.items() if k in ('id', 'name', 'origin')}
                                  for c in contexts[:32]]
            result['contexts_limited'] = True
    except Exception as error:
        result = {'status': 'error', 'error_type': 'InspectorFailure', 'message': str(error)[:1024]}
    finally:
        if session:
            result['cleanup'] = session.close()
            result['requests'] = session.requests
            result['exchanges'] = session.exchanges
            if result['status'] == 'ok' and (result['cleanup'].get('object_group') == 'unconfirmed' or not result['cleanup']['connection_closed']):
                result.update(status='error', error_type='InspectorCleanup', message='Cleanup could not be confirmed')
    if len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')) > 65536:
        result = {'status': 'error', 'error_type': 'InspectorOutputLimit', 'message': 'Final result exceeds 64 KiB; narrow fields/sample',
                  'cleanup': result.get('cleanup', {}), 'requests': result.get('requests', 0), 'exchanges': result.get('exchanges', 0)}
    return result
