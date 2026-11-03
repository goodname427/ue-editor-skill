import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'ue-editor' / 'scripts'))
import ue_inspector as inspector
import ue_cli


def value(kind, data):
    return {'type': kind, 'value': data}


def prop(name, data):
    return {'name': name, 'value': data}


class DescriptorSession:
    def __init__(self, objects):
        self.objects = objects
        self.batches = []

    def request(self, method, params):
        assert method == 'Runtime.getProperties'
        return {'result': self.objects[params['objectId']]}

    def properties_batch(self, ids):
        self.batches.append(list(ids))
        return [self.request('Runtime.getProperties', {'objectId': i}) for i in ids]


class ProjectionTests(unittest.TestCase):
    def test_projects_150_rows_and_nested_scalars_in_bounded_batches(self):
        objects = {'array': [prop('length', value('number', 150))]}
        for i in range(150):
            objects['array'].append(prop(str(i), {'type': 'object', 'objectId': 'row%d' % i}))
            objects['row%d' % i] = [prop('id', {'type': 'bigint', 'unserializableValue': str(9007199254740993 + i) + 'n'}),
                                   prop('nested', {'type': 'object', 'objectId': 'nested%d' % i})]
            objects['nested%d' % i] = [prop('active', value('boolean', i % 2 == 0))]
        session = DescriptorSession(objects)
        result = inspector.ObjectReader(session, 0, 0, 150).project({'type': 'object', 'subtype': 'array', 'objectId': 'array'}, ['/id', '/nested/active'])
        self.assertTrue(result['complete'])
        self.assertEqual(len(result['records']), 150)
        self.assertEqual([r['fields']['/id']['unserializableValue'] for r in result['records']], [str(9007199254740993 + i) + 'n' for i in range(150)])
        self.assertEqual([r['fields']['/nested/active']['value'] for r in result['records']], [i % 2 == 0 for i in range(150)])
        self.assertEqual(len(session.batches), 10)
        self.assertTrue(all(len(b) <= 32 for b in session.batches))

    def test_holes_accessors_missing_and_proxy_remain_explicit(self):
        objects = {'array': [prop('length', value('number', 6)),
                             prop('0', {'type': 'object', 'objectId': 'row'}),
                             {'name': '2', 'get': {'type': 'function', 'objectId': 'getter'}},
                             prop('3', {'type': 'object', 'subtype': 'proxy', 'objectId': 'proxy'}),
                             prop('4', value('object', None)),
                             prop('5', {'type': 'object', 'objectId': 'row'})],
                   'row': [prop('ok', value('undefined', None)), {'name': 'danger', 'get': {'type': 'function'}}]}
        session = DescriptorSession(objects)
        r = inspector.ObjectReader(session, 0, 0, 6).project({'type': 'object', 'subtype': 'array', 'objectId': 'array'}, ['/ok', '/danger', '/absent'])
        self.assertFalse(r['complete'])
        self.assertEqual(r['records'][1]['state'], 'hole')
        self.assertEqual(r['records'][2]['state'], 'accessor')
        self.assertIn('/danger', r['records'][0]['field_errors'])
        self.assertEqual(r['records'][0]['field_errors']['/absent']['error_type'], 'InspectorPathMissing')
        self.assertIn('/ok', r['records'][3]['field_errors'])
        self.assertNotIn('proxy', sum(session.batches, []))
        self.assertEqual(sum(session.batches, []), ['row'])

    def test_paging_and_truncated_text_do_not_claim_completeness(self):
        session = DescriptorSession({'array': [prop('length', value('number', 3)), prop('2', {'type': 'object', 'objectId': 'row'})],
                                     'row': [prop('text', value('string', 'x' * 600)), prop('fn', {'type': 'function', 'objectId': 'fn'})]})
        result = inspector.ObjectReader(session, 0, 2, 1).project({'type': 'object', 'subtype': 'array', 'objectId': 'array'}, ['/text', '/fn'])
        self.assertEqual(result['records'][0]['index'], 2)
        self.assertTrue(result['records_truncated'])
        self.assertTrue(result['records'][0]['fields']['/text']['value_truncated'])
        self.assertIn('/fn', result['records'][0]['field_errors'])
        self.assertFalse(result['complete'])

    def test_invalid_projection_parameters_never_connect(self):
        for options in ({'project_fields': 'x'}, {'project_fields': ['/x'] * 17}, {'project_fields': ['/x', '/x']},
                        {'project_fields': ['/x~2']}, {'project_fields': ['/a/b/c/d/e']}, {'project_fields': ['x']},
                        {'project_fields': ['/x'], 'limit': 501}, {'project_fields': ['/x'], 'list_scopes': True}):
            with self.subTest(options=options), mock.patch.object(inspector, 'InspectorSession') as session:
                r = inspector.inspect('ws://127.0.0.1:9999', 'state', **options)
                self.assertEqual(r['error_type'], 'InspectorArguments')
                session.assert_not_called()

    def test_projection_refuses_nonarray_and_protocol_enumeration_failure(self):
        session = DescriptorSession({'array': [prop('length', value('number', 1)), prop('0', {'type': 'object', 'objectId': 'row'})]})
        reader = inspector.ObjectReader(session, 0, 0, 1)
        for subtype in ('proxy', 'map', None):
            with self.subTest(subtype=subtype), self.assertRaises(inspector.InspectorError):
                reader.project({'type': 'object', 'subtype': subtype, 'objectId': 'array'}, ['/x'])
        session.properties_batch = lambda ids: [{'exceptionDetails': {'text': 'refused'}}]
        with self.assertRaises(inspector.InspectorError):
            reader.project({'type': 'object', 'subtype': 'array', 'objectId': 'array'}, ['/x'])

    def test_cli_project_forwards_fields_without_ue_connection(self):
        argv = ['ue_cli.py', 'inspector', 'project', '--url=ws://127.0.0.1:9999', '--expression=rows', '--field=/id', '--limit=150']
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(inspector, 'inspect', return_value={'status': 'ok'}) as read, \
                mock.patch.object(ue_cli, '_make_bridge') as bridge, mock.patch.object(ue_cli, '_print_json'):
            ue_cli.main()
        self.assertEqual(read.call_args.kwargs['project_fields'], ['/id'])
        self.assertEqual(read.call_args.kwargs['limit'], 150)
        bridge.assert_not_called()


class BatchTransportTests(unittest.TestCase):
    def session(self, count=3):
        s = inspector.InspectorSession('ws://127.0.0.1:9999', 8)
        socket = mock.Mock()
        sent, queued, receive_sizes = [], [], []
        def send(raw):
            q = json.loads(raw)
            sent.append(q)
            queued.insert(0, json.dumps({'id': q['id'], 'result': {'result': [prop('v', value('number', q['id']))]}}))
        def recv():
            receive_sizes.append(len(sent))
            return queued.pop(0)
        socket.send.side_effect = send
        socket.recv.side_effect = recv
        s.socket = socket
        return s, sent, queued, receive_sizes

    def test_batch_sends_before_receiving_and_maps_out_of_order_ids(self):
        s, sent, _, receives = self.session()
        responses = s.properties_batch(['a', 'b', 'c'])
        self.assertEqual(receives, [3, 3, 3])
        self.assertEqual([r['result'][0]['value']['value'] for r in responses], [1, 2, 3])
        self.assertEqual(s.requests, 3)
        self.assertEqual(s.exchanges, 1)
        self.assertFalse(s.outstanding)
        self.assertTrue(all(q['method'] == 'Runtime.getProperties' and q['params']['ownProperties'] for q in sent))

    def test_invalid_batch_has_no_send(self):
        for ids in ([], ['x'] * 33, [None], [''], 'x'):
            s, sent, _, _ = self.session()
            with self.subTest(ids=ids), self.assertRaises(inspector.InspectorError):
                s.properties_batch(ids)
            self.assertEqual(sent, [])

    def test_duplicate_or_unknown_response_is_refused(self):
        for ids in ([1, 1], [123]):
            s, _, _, _ = self.session()
            s.socket.recv.side_effect = [json.dumps({'id': i, 'result': {}}) for i in ids]
            with self.subTest(ids=ids), self.assertRaises(inspector.InspectorError) as error:
                s.properties_batch(['a', 'b'])
            self.assertEqual(error.exception.kind, 'InspectorResponse')

    def test_failed_batch_late_responses_do_not_prevent_group_release(self):
        s, _, queued, _ = self.session()
        s.group_used = True
        original = s.socket.recv.side_effect
        s.socket.recv.side_effect = TimeoutError('batch timed out')
        with self.assertRaises(inspector.InspectorError):
            s.properties_batch(['a', 'b'])
        self.assertEqual(s.outstanding, {1, 2})
        s.socket.recv.side_effect = original
        send = s.socket.send.side_effect
        def append_release(raw):
            send(raw)
            queued.append(queued.pop(0))
        s.socket.send.side_effect = append_release
        cleanup = s.close()
        self.assertEqual(cleanup['object_group'], 'released')
        self.assertTrue(cleanup['connection_closed'])
        self.assertFalse(s.outstanding)


if __name__ == '__main__':
    unittest.main()
