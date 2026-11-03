import contextlib
import importlib.util
import io
import json
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills' / 'ue-editor' / 'scripts'))
import ue_cli
import ue_inspector as inspector


class FakeSocket:
    def __init__(self):
        self.sent = []
        self.messages = []
        self.closed = False
        self.protocol_error = None
        self.evaluation_error = None
        self.cleanup_error = False
        self.contexts = [{'id': 1, 'name': 'sample'}]

    def settimeout(self, seconds):
        pass

    def send(self, raw):
        req = json.loads(raw)
        self.sent.append(req)
        if req['method'] == 'Runtime.enable':
            self.messages.extend(json.dumps({'method': 'Runtime.executionContextCreated', 'params': {'context': c}}) for c in self.contexts)
            result = {}
        elif req['method'] == 'Runtime.evaluate':
            result = {'result': {'type': 'object', 'objectId': 'global'}}
            if self.evaluation_error:
                result['exceptionDetails'] = {'text': self.evaluation_error}
        elif req['method'] == 'Runtime.getProperties':
            result = {'result': ([{'name': 'fixture', 'value': {'type': 'object', 'objectId': 'fixture'}}]
                                 if req['params']['objectId'] == 'global' else
                                 [{'name': 'count', 'value': {'type': 'number', 'value': 7}},
                                  {'name': 'danger', 'get': {'type': 'function', 'objectId': 'getter'}}])}
        else:
            result = {}
        reply = {'id': req['id'], 'result': result}
        if self.protocol_error and req['method'] == 'Runtime.evaluate':
            reply = {'id': req['id'], 'error': {'message': self.protocol_error}}
        if self.cleanup_error and req['method'] == 'Runtime.releaseObjectGroup':
            reply = {'id': req['id'], 'error': {'message': 'cannot release'}}
        self.messages.append(json.dumps(reply))

    def recv(self):
        return self.messages.pop(0)

    def close(self, timeout=0):
        self.closed = True


class InspectorTests(unittest.TestCase):
    def setUp(self):
        self.socket = FakeSocket()
        self.ws = mock.patch.dict(sys.modules, websocket=mock.Mock(create_connection=mock.Mock(return_value=self.socket)))
        self.ws.start()
        self.addCleanup(self.ws.stop)
        self.url = 'ws://127.0.0.1:9230/test'

    def test_root_protection_and_cleanup_are_mandatory(self):
        result = inspector.inspect(self.url, 'fixture.count')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['data']['value'], 7)
        evaluate = next(r for r in self.socket.sent if r['method'] == 'Runtime.evaluate')
        self.assertTrue(evaluate['params']['throwOnSideEffect'])
        self.assertEqual(evaluate['params']['expression'], 'globalThis')
        self.assertFalse(evaluate['params']['returnByValue'])
        self.assertFalse(evaluate['params']['awaitPromise'])
        self.assertEqual(result['cleanup']['object_group'], 'released')
        self.assertTrue(self.socket.closed)
        self.assertTrue(all(r['method'].startswith('Runtime.') for r in self.socket.sent))

    def test_side_effect_rejection_does_not_retry_unprotected(self):
        self.socket.evaluation_error = 'Possible side-effect in debug-evaluate'
        result = inspector.inspect(self.url, 'fixture.danger')
        self.assertEqual(result['error_type'], 'InspectorEvaluation')
        self.assertEqual(sum(r['method'] == 'Runtime.evaluate' for r in self.socket.sent), 1)
        self.assertEqual(result['cleanup']['object_group'], 'released')

    def test_unsupported_protection_fails_closed(self):
        self.socket.protocol_error = 'Unsupported throwOnSideEffect'
        result = inspector.inspect(self.url, 'fixture')
        self.assertEqual(result['error_type'], 'InspectorProtocol')
        self.assertEqual(sum(r['method'] == 'Runtime.evaluate' for r in self.socket.sent), 1)
        self.assertTrue(self.socket.closed)

    def test_context_ambiguity_and_missing_never_evaluate(self):
        self.socket.contexts.append({'id': 2, 'name': 'other'})
        result = inspector.inspect(self.url, 'fixture')
        self.assertEqual(result['error_type'], 'InspectorContextRequired')
        self.assertFalse(any(r['method'] == 'Runtime.evaluate' for r in self.socket.sent))
        self.socket.sent.clear()
        result = inspector.inspect(self.url, 'fixture', context_id=3)
        self.assertEqual(result['error_type'], 'InspectorContextMissing')
        self.assertFalse(any(r['method'] == 'Runtime.evaluate' for r in self.socket.sent))

    def test_context_list_does_not_evaluate_or_create_group(self):
        result = inspector.inspect(self.url)
        self.assertEqual(result['contexts'], [{'id': 1, 'name': 'sample'}])
        self.assertEqual(result['cleanup']['object_group'], 'not_created')
        self.assertEqual([r['method'] for r in self.socket.sent], ['Runtime.enable'])

    def test_failed_release_changes_success_to_cleanup_failure(self):
        self.socket.cleanup_error = True
        result = inspector.inspect(self.url, 'fixture')
        self.assertEqual(result['error_type'], 'InspectorCleanup')
        self.assertEqual(result['cleanup']['object_group'], 'unconfirmed')
        self.assertTrue(self.socket.closed)

    def test_root_accessor_refused_without_evaluating_business_field(self):
        result = inspector.inspect(self.url, 'fixture.danger')
        self.assertEqual(result['error_type'], 'InspectorReadRefused')
        self.assertEqual(result['cleanup']['object_group'], 'released')
        evaluations = [r for r in self.socket.sent if r['method'] == 'Runtime.evaluate']
        self.assertEqual([r['params']['expression'] for r in evaluations], ['globalThis'])

    def test_large_context_output_is_rejected_not_silently_truncated(self):
        self.socket.contexts[0]['name'] = 'x' * 70000
        result = inspector.inspect(self.url)
        self.assertEqual(result['error_type'], 'InspectorOutputLimit')
        self.assertTrue(self.socket.closed)

    def test_final_output_budget_includes_cleanup_metadata(self):
        template = {'status': 'ok', 'context': 1, 'path': '', 'scope_paths': [], 'data': {'text': ''},
                    'coverage': 'Own data descriptors and explicitly selected runtime scopes only, bounded and non-atomic; no getters, module loading, business calls or pause/resume. Map/Set/Proxy expansion not supported.'}
        size = len(json.dumps(template, ensure_ascii=False).encode('utf-8'))
        data = {'text': 'x' * (65536 - size - 10)}
        with mock.patch.object(inspector.ObjectReader, 'read', return_value=data):
            result = inspector.inspect(self.url, 'fixture')
        self.assertEqual(result['error_type'], 'InspectorOutputLimit')
        self.assertEqual(result['cleanup']['object_group'], 'released')
        self.assertLessEqual(len(json.dumps(result).encode('utf-8')), 65536)

    def test_rejects_remote_credentials_and_invalid_endpoint(self):
        for url in ('ws://example.com:9229/', 'wss://127.0.0.1:9229/', 'ws://192.168.0.1:9229/',
                    'ws://user@127.0.0.1:9229/', 'ws://127.0.0.1/', 'ws://127.0.0.1:9229/#fragment'):
            with self.subTest(url=url):
                self.assertEqual(inspector.inspect(url)['error_type'], 'InspectorArguments')
        self.assertEqual(self.socket.sent, [])
        self.assertEqual(inspector.validate_url('ws://[::1]:9229/target'), 'ws://[::1]:9229/target')

    def test_rejects_calls_assignments_and_invalid_bounds(self):
        for expression in ('require("foo")', 'fixture.calls++', 'fixture.count=1', 'JSON.stringify(fixture)', '(fixture)', ''):
            with self.subTest(expression=expression):
                self.assertEqual(inspector.inspect(self.url, expression)['error_type'], 'InspectorArguments')
        for opts in ({'timeout': 0}, {'timeout': float('nan')}, {'depth': 4}, {'limit': 101}, {'offset': -1}, {'context_id': True}):
            with self.subTest(opts=opts):
                self.assertEqual(inspector.inspect(self.url, 'fixture', **opts)['error_type'], 'InspectorArguments')
        self.assertEqual(self.socket.sent, [])

    def test_deadline_exhaustion_does_not_issue_request(self):
        session = inspector.InspectorSession(self.url, 8)
        session.socket = self.socket
        session.query_deadline = 0
        with self.assertRaises(inspector.InspectorError):
            session.request('Runtime.evaluate')
        self.assertEqual(self.socket.sent, [])

    def test_timeout_during_read_still_attempts_own_release(self):
        original = self.socket.recv
        def receive():
            if self.socket.sent[-1]['method'] == 'Runtime.evaluate':
                self.socket.messages.clear()
                raise TimeoutError('read deadline')
            return original()
        self.socket.recv = receive
        result = inspector.inspect(self.url, 'fixture')
        self.assertEqual(result['error_type'], 'InspectorTransport')
        self.assertEqual(result['cleanup']['object_group'], 'released')
        self.assertTrue(self.socket.closed)

    def test_late_query_response_does_not_block_release_confirmation(self):
        original = self.socket.recv
        def receive():
            if self.socket.sent[-1]['method'] == 'Runtime.evaluate':
                raise TimeoutError('query timed out; response arrives during cleanup')
            return original()
        self.socket.recv = receive
        result = inspector.inspect(self.url, 'fixture')
        self.assertEqual(result['error_type'], 'InspectorTransport')
        self.assertEqual(result['cleanup']['object_group'], 'released')
        self.assertTrue(self.socket.closed)

    def test_console_backlog_more_than_1000_events_does_not_hide_reply(self):
        original = self.socket.send
        def send(raw):
            request = json.loads(raw)
            if request['method'] == 'Runtime.enable':
                self.socket.messages.extend(json.dumps({'method': 'Runtime.consoleAPICalled', 'params': {}}) for _ in range(1200))
            original(raw)
        self.socket.send = send
        result = inspector.inspect(self.url, 'fixture.count')
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['data']['value'], 7)
        self.assertEqual(result['cleanup']['object_group'], 'released')

    def test_console_stream_bytes_remain_bounded(self):
        original = self.socket.recv
        event = json.dumps({'method': 'Runtime.consoleAPICalled', 'params': {'text': 'x' * 1000000}})
        self.socket.recv = lambda: event
        result = inspector.inspect(self.url)
        self.assertEqual(result['error_type'], 'InspectorResponse')
        self.assertIn('32 MiB', result['message'])
        self.assertTrue(self.socket.closed)

    def test_transport_disables_proxy_and_redirects(self):
        import websocket
        self.assertEqual(inspector.inspect('ws://127.0.0.2:9230/test')['status'], 'ok')
        kwargs = websocket.create_connection.call_args.kwargs
        self.assertEqual(kwargs['http_no_proxy'], ['*'])
        self.assertEqual(kwargs['redirect_limit'], 0)

    def test_invalid_pointer_is_rejected_before_connecting(self):
        for path in ('/x~2', '/' + '/'.join('x' for _ in range(17))):
            with self.subTest(path=path):
                self.assertEqual(inspector.inspect(self.url, 'fixture', path=path)['error_type'], 'InspectorArguments')
        self.assertEqual(self.socket.sent, [])

    def test_invalid_scope_paths_are_rejected_before_connection(self):
        for options in ({'scope_paths': ['/x']}, {'scope_paths': ['/0'] * 5},
                        {'scope_paths': ['/0/x~2']}, {'scope_paths': 'not-list'},
                        {'list_scopes': True, 'path': '/x'}):
            with self.subTest(options=options):
                result = inspector.inspect(self.url, 'fixture', **options)
                self.assertEqual(result['error_type'], 'InspectorArguments')
        self.assertEqual(self.socket.sent, [])

    def test_scope_read_failure_releases_own_group(self):
        result = inspector.inspect(self.url, 'fixture', scope_paths=['/0'])
        self.assertEqual(result['error_type'], 'InspectorScopeRefused')
        self.assertEqual(result['cleanup']['object_group'], 'released')
        self.assertTrue(self.socket.closed)

    def test_local_cli_does_not_create_ue_bridge(self):
        args = ['ue_cli.py', 'inspector', 'inspect', '--url', self.url, '--expression', 'fixture.count']
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', args), mock.patch.object(ue_cli, '_make_bridge') as bridge, contextlib.redirect_stdout(output):
            ue_cli.main()
        bridge.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['data']['value'], 7)

    def test_log_cli_without_ue_parameters_still_works(self):
        with mock.patch.object(sys, 'argv', ['ue_cli.py', 'log', 'mark', '--file', 'test.log']), \
                mock.patch.object(ue_cli.ue_log, 'mark', return_value={'status': 'ok'}), contextlib.redirect_stdout(io.StringIO()):
            ue_cli.main()


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.session = mock.Mock()
        self.root = {'type': 'object', 'objectId': 'root'}

    def reader(self, props, **opts):
        self.session.request.return_value = {'result': props}
        return inspector.ObjectReader(self.session, opts.get('depth', 1), opts.get('offset', 0), opts.get('limit', 20))

    def test_accessor_is_reported_and_never_called(self):
        reader = self.reader([{'name': 'danger', 'get': {'type': 'function', 'objectId': 'getter'}}])
        result = reader.read(self.root)
        self.assertTrue(result['properties'][0]['getter'])
        self.session.request.assert_called_once_with('Runtime.getProperties', {'objectId': 'root', 'ownProperties': True, 'generatePreview': False})
        with self.assertRaises(inspector.InspectorError):
            reader.follow(self.root, '/danger')
        self.assertEqual(self.session.request.call_count, 1)

    def test_path_traverses_data_only_and_escapes(self):
        reader = self.reader([{'name': 'a/b', 'value': {'type': 'number', 'value': 42}}])
        self.assertEqual(reader.follow(self.root, '/a~1b')['value'], 42)
        with self.assertRaises(inspector.InspectorError):
            reader.follow(self.root, '/missing')

    def test_array_paging_preserves_sparse_indices(self):
        props = [{'name': 'length', 'value': {'type': 'number', 'value': 6}},
                 {'name': '0', 'value': {'type': 'number', 'value': 1}},
                 {'name': '3', 'value': {'type': 'number', 'value': 4}},
                 {'name': '5', 'value': {'type': 'number', 'value': 6}}]
        result = self.reader(props, offset=2, limit=2).read(dict(self.root, subtype='array'))
        self.assertEqual(result['length'], 6)
        self.assertEqual([p['name'] for p in result['properties']], ['3'])
        self.assertTrue(result['properties_truncated'])

    def test_array_non_index_properties_are_reported_as_omitted(self):
        props = [{'name': 'length', 'value': {'type': 'number', 'value': 0}},
                 {'name': '01', 'value': {'type': 'number', 'value': 9}},
                 {'name': 'meta', 'get': {'type': 'function'}}]
        result = self.reader(props).read(dict(self.root, subtype='array'))
        self.assertEqual(result['properties'], [])
        self.assertEqual(result['non_index_properties_omitted'], 2)
        self.assertIn('index', result['property_coverage'])

    def test_exact_node_budget_does_not_invent_property_truncation(self):
        props = [{'name': str(i), 'value': {'type': 'number', 'value': i}} for i in range(2)]
        reader = self.reader(props)
        reader.budget = 3
        result = reader.read(self.root)
        self.assertFalse(result['properties_truncated'])
        self.assertEqual(len(result['properties']), 2)

    def test_collection_pointer_traversal_is_also_refused(self):
        for subtype in ('map', 'set', 'weakmap', 'weakset'):
            with self.subTest(subtype=subtype), self.assertRaises(inspector.InspectorError):
                self.reader([]).follow(dict(self.root, subtype=subtype), '/meta')
        self.session.request.assert_not_called()

    def test_bigint_and_nonfinite_values_keep_cdp_type(self):
        reader = self.reader([])
        for value in ('9007199254740993n', 'NaN', 'Infinity', '-0'):
            result = reader.read({'type': 'bigint' if value.endswith('n') else 'number', 'unserializableValue': value})
            self.assertEqual(result['unserializableValue'], value)
            json.dumps(result, allow_nan=False)

    def test_cycles_and_depth_are_bounded(self):
        reader = self.reader([{'name': 'self', 'value': self.root}], depth=3)
        self.assertEqual(reader.read(self.root)['properties'][0]['data']['reference'], '')
        self.assertEqual(self.session.request.call_count, 1)
        self.session.request.reset_mock()
        result = self.reader([], depth=0).read(self.root)
        self.assertEqual(result['expansion'], 'depth_or_node_limit')
        self.session.request.assert_not_called()

    def test_proxy_and_collections_are_explicitly_unsupported(self):
        for subtype in ('proxy', 'map', 'set', 'weakmap'):
            result = self.reader([]).read(dict(self.root, subtype=subtype))
            self.assertEqual(result['expansion'], 'unsupported_collection_or_proxy')
        self.session.request.assert_not_called()
        with self.assertRaises(inspector.InspectorError):
            self.reader([]).follow(dict(self.root, subtype='proxy'), '/x')

    def test_scopes_require_function_and_internal_scope_list(self):
        reader = self.reader([])
        with self.assertRaises(inspector.InspectorError):
            reader.scopes(self.root)
        function = {'type': 'function', 'objectId': 'fn'}
        for value in ({'type': 'object', 'subtype': 'array', 'objectId': 'scopes'},
                      {'type': 'function', 'subtype': 'internal#scopeList', 'objectId': 'scopes'},
                      {'type': 'object', 'subtype': 'internal#scopeList'}):
            self.session.request.return_value = {'internalProperties': [{'name': '[[Scopes]]', 'value': value}]}
            with self.subTest(value=value), self.assertRaises(inspector.InspectorError):
                reader.scopes(function)
        self.assertTrue(all(c.args[0] == 'Runtime.getProperties' for c in self.session.request.call_args_list))

    def test_scope_index_must_reference_internal_scope(self):
        reader = self.reader([])
        function = {'type': 'function', 'objectId': 'fn'}
        self.session.request.side_effect = [
            {'internalProperties': [{'name': '[[Scopes]]', 'value': {'type': 'object', 'subtype': 'internal#scopeList', 'objectId': 'scopes'}}]},
            {'result': [{'name': '0', 'value': {'type': 'object', 'objectId': 'ordinary'}}]}
        ]
        with self.assertRaises(inspector.InspectorError) as error:
            reader.follow_scope(function, '/0/secret')
        self.assertEqual(error.exception.kind, 'InspectorScopeRefused')
        self.assertEqual(self.session.request.call_count, 2)

    def test_large_text_is_bounded(self):
        result = self.reader([]).read({'type': 'string', 'value': '中文' * 1000})
        self.assertEqual(result['length'], 2000)
        self.assertEqual(len(result['value']), 512)
        self.assertTrue(result['value_truncated'])


@unittest.skipUnless(shutil.which('node') and importlib.util.find_spec('websocket'), 'Node and optional websocket-client required')
class LiveV8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.process = subprocess.Popen([shutil.which('node'), '--inspect=127.0.0.1:0', str(ROOT / 'tests' / 'inspector_fixture.js')],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        cls.stderr_lines = queue.Queue()
        cls.stdout_lines = queue.Queue()
        def collect(stream, target):
            for line in stream:
                target.put(line)
        for stream, target in ((cls.process.stderr, cls.stderr_lines), (cls.process.stdout, cls.stdout_lines)):
            threading.Thread(target=collect, args=(stream, target), daemon=True).start()
        try:
            cls.url = re.search(r'ws://\S+', cls.stderr_lines.get(timeout=10)).group(0)
            if cls.stdout_lines.get(timeout=10).strip() != 'fixture-ready':
                raise AssertionError('Fixture not ready')
            contexts = inspector.inspect(cls.url)
            default = [c for c in contexts.get('contexts', []) if c.get('auxData', {}).get('isDefault')]
            if len(default) != 1:
                raise AssertionError('Fixture default context not uniquely identified')
            cls.context = default[0]['id']
        except Exception:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        try:
            cls.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.process.kill()
            cls.process.wait(timeout=5)
        cls.process.stdout.close()
        cls.process.stderr.close()

    def snapshot(self, **opts):
        result = inspector.inspect(self.url, 'fixture', context_id=self.context, **opts)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual(result['cleanup']['object_group'], 'released', result)
        return result['data']

    def test_real_contexts_plain_data_and_bigint(self):
        contexts = inspector.inspect(self.url)
        self.assertEqual(contexts['status'], 'ok', contexts)
        self.assertIn(self.context, [c['id'] for c in contexts['contexts']])
        if len(contexts['contexts']) > 1:
            self.assertEqual(inspector.inspect(self.url, 'fixture')['error_type'], 'InspectorContextRequired')
        root = self.snapshot()
        props = {p['name']: p for p in root['properties']}
        self.assertEqual(props['count']['data']['value'], 7)
        self.assertEqual(props['big']['data']['unserializableValue'], '9007199254740993n')
        self.assertEqual(props['missing']['data']['type'], 'undefined')
        self.assertEqual(props['nil']['data']['subtype'], 'null')
        self.assertTrue(props['danger']['getter'])

    def test_real_paging_and_field_path(self):
        array = self.snapshot(path='/arr', offset=1, limit=2)
        self.assertEqual(array['length'], 4)
        self.assertEqual([(p['name'], p['data']['value']) for p in array['properties']], [('1', 22), ('2', 33)])
        self.assertEqual(self.snapshot(path='/nested/name')['value'], 'expected')
        sparse = self.snapshot(path='/sparse')
        self.assertEqual([p['name'] for p in sparse['properties']], ['0', '2'])

    def test_real_getter_refused_and_counter_unchanged(self):
        before = self.snapshot(path='/calls')['value']
        rejected = inspector.inspect(self.url, 'fixture.danger', context_id=self.context)
        self.assertEqual(rejected['status'], 'error', rejected)
        self.assertEqual(rejected['error_type'], 'InspectorReadRefused')
        self.assertEqual(rejected['cleanup']['object_group'], 'released')
        root = self.snapshot(depth=3)
        self.assertIn('properties', root)
        via_path = inspector.inspect(self.url, 'fixture', path='/danger', context_id=self.context)
        self.assertEqual(via_path['error_type'], 'InspectorReadRefused')
        self.assertEqual(self.snapshot(path='/calls')['value'], before)

    def test_real_closure_scopes_read_without_invoking_function(self):
        summary = inspector.inspect(self.url, 'fixture.closure', context_id=self.context, list_scopes=True)
        self.assertEqual(summary['status'], 'ok', summary)
        selected = [s for s in summary['scopes'] if s['description'] == 'Closure']
        self.assertEqual(len(selected), 1, summary)
        pointer = '/' + str(selected[0]['index']) + '/hiddenState'
        state = inspector.inspect(self.url, 'fixture.closure', context_id=self.context, scope_paths=[pointer], depth=2)
        self.assertEqual(state['status'], 'ok', state)
        props = {p['name']: p['data'] for p in state['data']['properties']}
        self.assertEqual(props['selected']['value'], 202)
        self.assertEqual([p['data']['value'] for p in props['items']['properties']], [101, 202, 303])
        self.assertEqual(state['cleanup']['object_group'], 'released')
        self.assertEqual(self.snapshot(path='/calls')['value'], 0)

    def test_real_projection_150_rows_nested_scalars_and_bigint(self):
        result = inspector.inspect(self.url, 'fixture.rows', context_id=self.context, limit=150,
                                   project_fields=['/id', '/qty', '/meta/active'])
        self.assertEqual(result['status'], 'ok', result)
        data = result['data']
        self.assertTrue(data['complete'])
        self.assertEqual(data['length'], 150)
        self.assertEqual([r['fields']['/id']['unserializableValue'] for r in data['records']],
                         [str(9007199254740993 + i) + 'n' for i in range(150)])
        self.assertEqual([r['fields']['/qty']['value'] for r in data['records']], [i % 7 for i in range(150)])
        self.assertEqual([r['fields']['/meta/active']['value'] for r in data['records']], [i % 2 == 0 for i in range(150)])
        self.assertLess(result['exchanges'], 25)
        self.assertGreater(result['requests'], 300)
        self.assertEqual(result['cleanup']['object_group'], 'released')
        self.assertEqual(self.snapshot(path='/calls')['value'], 0)

    def test_real_projection_refuses_accessor_proxy_and_keeps_holes(self):
        result = inspector.inspect(self.url, 'fixture.mixedRows', context_id=self.context, project_fields=['/danger', '/count'])
        self.assertEqual(result['status'], 'ok', result)
        rows = result['data']['records']
        self.assertFalse(result['data']['complete'])
        self.assertEqual(rows[1]['state'], 'hole')
        self.assertEqual(rows[0]['fields']['/count']['value'], 7)
        self.assertEqual(rows[0]['field_errors']['/danger']['error_type'], 'InspectorReadRefused')
        self.assertEqual(rows[3]['field_errors']['/count']['error_type'], 'InspectorReadRefused')
        self.assertEqual(self.snapshot(path='/calls')['value'], 0)

    def test_real_proxy_refused_and_session_remains_usable(self):
        self.assertEqual(self.snapshot(path='/proxy')['expansion'], 'unsupported_collection_or_proxy')
        rejected = inspector.inspect(self.url, 'fixture', path='/proxy/hidden', context_id=self.context)
        self.assertEqual(rejected['error_type'], 'InspectorReadRefused')
        self.assertEqual(self.snapshot(path='/calls')['value'], 0)
        self.assertEqual(self.snapshot(path='/count')['value'], 7)


if __name__ == '__main__':
    unittest.main()
