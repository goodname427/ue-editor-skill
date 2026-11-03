import contextlib
import io
import json
from pathlib import Path
import socket
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'ue-editor' / 'scripts'))
import ue_bridge
import ue_cli


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.bridge = ue_bridge.UEBridge(auto_detect_config=False)
        self.clock = 0.0

    def discover_with_schedule(self, schedule, timeout=1, target=None):
        def sleep(seconds):
            self.clock += seconds
            with self.bridge._nodes_lock:
                for at, node in schedule:
                    if at <= self.clock:
                        self.bridge._remote_nodes[node] = {'project_name': 'Sample'}
        with mock.patch.object(self.bridge, '_start_broadcast'), mock.patch.object(self.bridge, '_stop_broadcast') as stop, \
                mock.patch.object(ue_bridge.time, 'monotonic', side_effect=lambda: self.clock), \
                mock.patch.object(ue_bridge.time, 'sleep', side_effect=sleep), \
                mock.patch.object(ue_bridge.time, 'time', side_effect=AssertionError('wall clock used')):
            result = self.bridge.discover(timeout, remote_node_id=target)
        stop.assert_called_once()
        return result

    def test_delayed_second_node_is_not_missed(self):
        result = self.discover_with_schedule([(0.05, 'first'), (0.9, 'second')])
        self.assertEqual([n['node_id'] for n in result['nodes']], ['first', 'second'])
        self.assertTrue(result['discovery_complete'])
        self.assertAlmostEqual(result['discovery_waited'], 1)

    def test_single_response_does_not_end_inventory_early(self):
        result = self.discover_with_schedule([(0.05, 'only')])
        self.assertTrue(result['discovery_complete'])
        self.assertAlmostEqual(self.clock, 1)

    def test_explicit_node_returns_early_only_after_target_reply(self):
        result = self.discover_with_schedule([(0.05, 'other'), (0.3, 'wanted')], target='wanted')
        self.assertEqual({n['node_id'] for n in result['nodes']}, {'other', 'wanted'})
        self.assertFalse(result['discovery_complete'])
        self.assertAlmostEqual(self.clock, 0.3)

    def test_missing_explicit_node_still_collects_until_deadline(self):
        result = self.discover_with_schedule([(0.05, 'other')], target='wanted')
        self.assertTrue(result['discovery_complete'])
        self.assertAlmostEqual(self.clock, 1)

    def test_late_reply_outside_budget_is_not_claimed(self):
        result = self.discover_with_schedule([(0.05, 'first'), (1.1, 'late')])
        self.assertEqual([n['node_id'] for n in result['nodes']], ['first'])
        self.assertIn('not a process inventory', result['coverage'])

    def test_duplicates_are_deduplicated_and_order_is_stable(self):
        result = self.discover_with_schedule([(0.05, 'z'), (0.2, 'a'), (0.4, 'a')])
        self.assertEqual([n['node_id'] for n in result['nodes']], ['a', 'z'])

    def test_no_response_does_not_mean_no_process(self):
        result = self.discover_with_schedule([])
        self.assertEqual(result['error_type'], 'NoEditorFound')
        self.assertFalse(result['command_sent'])
        self.assertIn('不证明', result['suggestion'])

    def test_start_failure_still_cleans_broadcast(self):
        with mock.patch.object(self.bridge, '_start_broadcast', side_effect=OSError('bind failed')), \
                mock.patch.object(self.bridge, '_stop_broadcast') as stop:
            result = self.bridge.discover(1)
        stop.assert_called_once()
        self.assertEqual(result['error_type'], 'DiscoverError')
        self.assertFalse(result['command_sent'])

    def test_empty_explicit_id_never_falls_back(self):
        for node in ('', ' ', 3):
            with self.subTest(node=node), mock.patch.object(self.bridge, '_start_broadcast') as start, \
                    mock.patch.object(self.bridge, '_open_command_connection') as tcp:
                result = self.bridge.connect(remote_node_id=node)
                self.assertEqual(result['error_type'], 'DiscoverArguments')
                start.assert_not_called()
                tcp.assert_not_called()

    def test_receiver_rejects_reply_arriving_at_or_after_deadline(self):
        for received_at in (1.0, 1.1):
            self.bridge._running = True
            self.bridge._discovery_deadline = 1.0
            self.bridge._broadcast_sock = mock.Mock()
            message = ue_bridge._Message(ue_bridge._TYPE_PONG, 'late', self.bridge._node_id).to_bytes()
            self.bridge._broadcast_sock.recv.return_value = message
            def stop(_seconds):
                self.bridge._running = False
            with self.subTest(received_at=received_at), mock.patch.object(ue_bridge.time, 'monotonic', return_value=received_at), \
                    mock.patch.object(ue_bridge.time, 'sleep', side_effect=stop):
                self.bridge._broadcast_loop()
                self.assertNotIn('late', self.bridge._remote_nodes)

    def test_invalid_discovery_budget_does_not_start(self):
        for timeout in (0, -1, True, float('nan'), float('inf'), '1'):
            with self.subTest(timeout=timeout), mock.patch.object(self.bridge, '_start_broadcast') as start:
                result = self.bridge.discover(timeout)
                self.assertEqual(result['error_type'], 'DiscoverArguments')
                start.assert_not_called()


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.bridge = ue_bridge.UEBridge(auto_detect_config=False)
        self.nodes = [{'node_id': 'a', 'project_name': 'Sample'}, {'node_id': 'b', 'project_name': 'Sample'}]

    def test_multiple_same_project_nodes_refuse_tcp_without_selection(self):
        for nodes in (self.nodes, list(reversed(self.nodes))):
            with self.subTest(nodes=nodes), mock.patch.object(self.bridge, 'discover', return_value={'status': 'ok', 'nodes': nodes}), \
                    mock.patch.object(self.bridge, '_open_command_connection') as tcp:
                result = self.bridge.connect()
                self.assertEqual(result['error_type'], 'AmbiguousEditor')
                self.assertEqual(result['nodes'], nodes)
                self.assertFalse(result['command_sent'])
                tcp.assert_not_called()

    def test_explicit_node_does_not_choose_first(self):
        with mock.patch.object(self.bridge, 'discover', return_value={'status': 'ok', 'nodes': self.nodes}) as discover, \
                mock.patch.object(self.bridge, '_open_command_connection', return_value={'status': 'ok'}) as tcp:
            self.assertEqual(self.bridge.connect(remote_node_id='b')['status'], 'ok')
        discover.assert_called_once_with(5, remote_node_id='b')
        tcp.assert_called_once_with('b')

    def test_missing_requested_node_never_falls_back(self):
        with mock.patch.object(self.bridge, 'discover', return_value={'status': 'ok', 'nodes': self.nodes}), \
                mock.patch.object(self.bridge, '_open_command_connection') as tcp:
            result = self.bridge.connect(remote_node_id='missing')
        self.assertEqual(result['error_type'], 'NodeNotFound')
        self.assertFalse(result['command_sent'])
        self.assertEqual(result['nodes'], self.nodes)
        tcp.assert_not_called()

    def test_single_node_keeps_auto_connect(self):
        with mock.patch.object(self.bridge, 'discover', return_value={'status': 'ok', 'nodes': self.nodes[:1]}), \
                mock.patch.object(self.bridge, '_open_command_connection', return_value={'status': 'ok'}) as tcp:
            self.assertEqual(self.bridge.connect()['status'], 'ok')
        tcp.assert_called_once_with('a')

    def test_ambiguous_cli_does_not_retry_or_run_action(self):
        bridge, action = mock.Mock(), mock.Mock()
        bridge.connect.return_value = {'status': 'error', 'error_type': 'AmbiguousEditor', 'nodes': self.nodes}
        with mock.patch.object(ue_cli, '_make_bridge', return_value=bridge):
            result = ue_cli._run(SimpleNamespace(timeout=None, node=None), action)
        self.assertFalse(result['command_sent'])
        bridge.connect.assert_called_once()
        action.assert_not_called()
        bridge.disconnect.assert_called_once()

    def test_discover_cli_error_exits_nonzero_with_json(self):
        bridge = mock.Mock()
        bridge.discover.return_value = {'status': 'error', 'error_type': 'NoEditorFound'}
        output = io.StringIO()
        with mock.patch.object(ue_cli, '_make_bridge', return_value=bridge), contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as error:
                ue_cli.cmd_discover(SimpleNamespace(timeout=1))
        self.assertEqual(error.exception.code, 1)
        self.assertEqual(json.loads(output.getvalue())['error_type'], 'NoEditorFound')

    def test_connection_broadcast_start_failure_cleans_udp_and_tcp(self):
        listener = mock.Mock()
        udp = mock.Mock()
        def fail_start():
            self.bridge._running = True
            self.bridge._broadcast_sock = udp
            raise OSError('UDP bind failed')
        with mock.patch.object(self.bridge, 'discover', return_value={'status': 'ok', 'nodes': self.nodes[:1]}), \
                mock.patch.object(self.bridge, '_start_broadcast', side_effect=fail_start), \
                mock.patch.object(ue_bridge.socket, 'socket', return_value=listener), \
                mock.patch.object(ue_bridge.time, 'sleep'), contextlib.redirect_stderr(io.StringIO()):
            result = self.bridge.connect()
        self.assertEqual(result['error_type'], 'ConnectionFailed')
        self.assertFalse(result['command_sent'])
        self.assertIsNone(self.bridge._cmd_listen_sock)
        self.assertIsNone(self.bridge._broadcast_sock)
        self.assertFalse(self.bridge._running)
        self.assertEqual(udp.close.call_count, 3)
        self.assertEqual(listener.close.call_count, 3)

    def test_cli_empty_node_and_zero_budget_are_rejected_before_connection(self):
        for argv in (['discover', '--timeout=0'], ['exec', 'print(1)', '--timeout=0'], ['exec', 'print(1)', '--node=']):
            with self.subTest(argv=argv), mock.patch.object(sys, 'argv', ['ue_cli.py'] + argv), \
                    mock.patch.object(ue_cli, '_make_bridge') as make, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    ue_cli.main()
                self.assertEqual(error.exception.code, 2)
                make.assert_not_called()

    def test_exec_connection_error_exits_nonzero_without_execution(self):
        args = SimpleNamespace(action='ui', ready_timeout=0, verbose=False)
        with mock.patch.object(ue_cli, '_read_source', return_value=('print(1)', '<test>')), \
                mock.patch.object(ue_cli, '_run', return_value={'status': 'error', 'error_type': 'AmbiguousEditor'}), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                ue_cli.cmd_exec(args, [])
        self.assertEqual(error.exception.code, 1)


class ProtocolDiscoveryTests(unittest.TestCase):
    def test_two_loopback_protocol_nodes_use_real_receiver_and_cleanup(self):
        bridge = ue_bridge.UEBridge(auto_detect_config=False)
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(('127.0.0.1', 0))
        receiver.settimeout(0.03)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.addCleanup(sender.close)
        self.addCleanup(receiver.close)
        address = receiver.getsockname()
        def start():
            bridge._remote_nodes = {}
            bridge._broadcast_sock = receiver
            bridge._running = True
            bridge._listen_thread = threading.Thread(target=bridge._broadcast_loop, daemon=True)
            bridge._listen_thread.start()
            sender.sendto(ue_bridge._Message(ue_bridge._TYPE_PONG, 'node-a', bridge._node_id,
                                            {'project_name': 'Sample'}).to_bytes(), address)
            sender.sendto(ue_bridge._Message(ue_bridge._TYPE_PONG, 'node-b', bridge._node_id,
                                            {'project_name': 'Sample'}).to_bytes(), address)
            sender.sendto(ue_bridge._Message(ue_bridge._TYPE_PONG, 'wrong-destination', 'someone-else').to_bytes(), address)
        with mock.patch.object(bridge, '_start_broadcast', side_effect=start):
            result = bridge.discover(0.6)
        self.assertEqual([n['node_id'] for n in result['nodes']], ['node-a', 'node-b'])
        self.assertIsNone(bridge._broadcast_sock)
        self.assertIsNone(bridge._listen_thread)
        self.assertFalse(bridge._running)
        with mock.patch.object(bridge, 'discover', return_value=result), mock.patch.object(bridge, '_open_command_connection') as tcp:
            self.assertEqual(bridge.connect()['error_type'], 'AmbiguousEditor')
            tcp.assert_not_called()


if __name__ == '__main__':
    unittest.main()
