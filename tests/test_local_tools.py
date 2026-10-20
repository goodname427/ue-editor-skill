import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills' / 'ue-editor' / 'scripts'))
import ue_bridge
import ue_cli
import ue_log


class LogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'editor.log'

    def test_full_history_unicode_and_bounded_matches(self):
        self.path.write_bytes('目标 first\n'.encode() + b'noise\n' * 200000 + '目标 last\r\n'.encode())
        result = ue_log.read(self.path, filter_text='目标', max_lines=1)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['line_count'], 2)
        self.assertEqual(result['lines'], ['目标 last'])
        self.assertEqual(result['scanned_lines'], 200002)
        self.assertEqual(result['scan_from_line'], 1)
        self.assertFalse(result['history_truncated'])
        self.assertFalse(result['scan_truncated'])
        self.assertTrue(result['truncated'])

    def test_tail_and_since_zero_match_explain_window(self):
        self.path.write_bytes(b'noise\n' * 200000)
        tail = ue_log.read(self.path)
        self.assertTrue(tail['history_truncated'])
        self.assertIsNone(tail['scan_from_line'])
        base = ue_log.mark(self.path)
        with self.path.open('ab') as fp:
            fp.write(b'noise\n' * 200000)
        result = ue_log.read(self.path, base['cursor'], filter_text='missing')
        self.assertEqual(result['line_count'], 0)
        self.assertTrue(result['scan_truncated'])
        self.assertIn(str(result['start_offset']), result['note'])
        self.assertIn(str(result['scanned_lines']), result['note'])
        following = ue_log.read(self.path, result['cursor'])
        self.assertFalse(following['scan_truncated'])

    def test_chunk_boundary_and_partial_tail(self):
        prefix = b'n\n' * ((ue_log.MAX_SCAN_BYTES - 2) // 2)
        self.path.write_bytes(prefix + '目标\r\nunfinished'.encode())
        result = ue_log.read(self.path, filter_text='目标')
        self.assertEqual(result['lines'], ['目标'])
        self.assertEqual(result['pending_bytes'], len(b'unfinished'))
        with self.path.open('ab') as fp:
            fp.write(b' complete\nnew\n')
        next_result = ue_log.read(self.path, result['cursor'])
        self.assertEqual(next_result['lines'], ['unfinished complete', 'new'])

    def test_mark_in_partial_line_and_rewrite(self):
        self.path.write_bytes(b'old partial')
        base = ue_log.mark(self.path)
        with self.path.open('ab') as fp:
            fp.write(b' complete\nnew\n')
        result = ue_log.read(self.path, base['cursor'])
        self.assertEqual(result['lines'], ['new'])
        self.path.write_bytes(b'rewritten\n')
        self.assertEqual(ue_log.read(self.path, result['cursor'])['error_type'], 'LogChanged')

    def test_truncation_during_full_scan_terminates(self):
        self.path.write_bytes(b'old\n' * 300000)
        with mock.patch.object(ue_log, '_verify', side_effect=lambda *args: self.path.write_bytes(b'')):
            result = ue_log.read(self.path, filter_text='old')
        self.assertEqual(result['error_type'], 'LogChanged')

    def test_complete_long_line_filters_across_chunk_boundary(self):
        self.path.write_bytes(b'a' * (ue_log.MAX_SCAN_BYTES - 2) + '目标'.encode()
                              + b'b' * ue_log.MAX_SCAN_BYTES + b'\nlast\n')
        result = ue_log.read(self.path, filter_text='目标')
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['line_count'], 1)
        self.assertEqual(result['scanned_lines'], 2)
        self.assertTrue(result['truncated'])
        self.assertFalse(result['scan_truncated'])
        self.assertEqual(result['end_offset'], result['file_size'])

    def test_long_line_and_missing_whole_history(self):
        self.path.write_bytes(b'a' * ue_log.MAX_SCAN_BYTES)
        self.assertEqual(ue_log.read(self.path, filter_text='missing')['error_type'], 'LogLineTooLong')
        self.path.write_bytes(b'only\n')
        result = ue_log.read(self.path, filter_text='missing')
        self.assertEqual(result['line_count'], 0)
        self.assertNotIn('note', result)
        self.assertEqual(result['end_offset'], result['file_size'])


class ScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.args = SimpleNamespace(out=str(Path(self.directory.name) / 'capture.png'), archive=None,
                                    name=None, margin=8, rect='-90,30,50,40', widget=None, crop=None,
                                    pie=False, popup=False, instance=None, list=False, title=None, max_width=0)
        self.window = {'hwnd': 1, 'title': 'Editor', 'rect': [-100, 20, 100, 80]}
        self.screenshot = mock.Mock()
        self.screenshot.window_at.return_value = self.window
        self.screenshot.capture.return_value = {'path': self.args.out}

    def run_capture(self):
        output = io.StringIO()
        with mock.patch.dict(sys.modules, ue_screenshot=self.screenshot), contextlib.redirect_stdout(output):
            try:
                ue_cli.cmd_screenshot(self.args)
            except SystemExit as e:
                self.assertEqual(e.code, 1)
        return json.loads(output.getvalue())

    def test_margin_in_desktop_pixels(self):
        result = self.run_capture()
        self.screenshot.capture.assert_called_once_with(1, self.args.out, crop=[2, 2, 66, 56], max_width=0)
        self.assertEqual(result['rect'], [-98, 22, 66, 56])

    def test_margin_clips_to_original_window(self):
        self.args.margin = 500
        result = self.run_capture()
        self.assertEqual(result['rect'], self.window['rect'])
        self.screenshot.window_at.assert_called_once_with(-65.0, 50.0)

    def test_widget_uses_same_margin_path(self):
        self.args.rect = None
        self.args.widget = 'name=Panel'
        with mock.patch.object(ue_cli, '_widget_rect', return_value=[-90, 30, 50, 40]):
            result = self.run_capture()
        self.assertEqual(result['rect'], [-98, 22, 66, 56])

    def test_invalid_margin_and_ignored_crop_rejected(self):
        for updates in ({'margin': -1}, {'rect': None}, {'crop': '0,0,5,5'},
                        {'rect': None, 'pie': True, 'margin': 0, 'crop': '0,0,5,5'}):
            with self.subTest(updates=updates):
                original = vars(self.args).copy()
                for key, value in updates.items():
                    setattr(self.args, key, value)
                self.assertEqual(self.run_capture()['error_type'], 'ScreenshotArguments')
                self.args = SimpleNamespace(**original)
        self.screenshot.capture.assert_not_called()


class WaitTests(unittest.TestCase):
    def test_false_condition_expires_on_monotonic_clock(self):
        bridge = mock.Mock()
        bridge.evaluate.return_value = {'status': 'ok', 'result': 'False'}
        args = SimpleNamespace(wait_until='False', wait=1)
        with mock.patch.object(ue_cli.time, 'monotonic', side_effect=[10.0, 10.2, 10.4, 11.1]), \
                mock.patch.object(ue_cli.time, 'sleep'), \
                mock.patch.object(ue_cli.time, 'time', side_effect=AssertionError('wall clock used')):
            result = ue_cli._wait_until(bridge, {'status': 'ok', 'output': 'sent'}, args)
        self.assertEqual(result['error_type'], 'WaitTimeout')
        self.assertEqual(bridge.evaluate.call_count, 2)

    def test_success_elapsed_uses_same_clock(self):
        args = SimpleNamespace(wait_until='True', wait=1)
        with mock.patch.object(ue_cli.time, 'monotonic', side_effect=[10.0, 10.3]), \
                mock.patch.object(ue_cli, '_poll', return_value={'status': 'ok'}) as poll, \
                mock.patch.object(ue_cli.time, 'time', side_effect=AssertionError('wall clock used')):
            result = ue_cli._wait_until(mock.Mock(), {'status': 'ok'}, args)
        self.assertEqual(result['waited'], 0.3)
        self.assertEqual(poll.call_args.args[2], 11.0)


class ConnectionTests(unittest.TestCase):
    def test_tcp_failure_does_not_send_command(self):
        bridge = ue_bridge.UEBridge()
        with mock.patch.object(bridge, 'discover', return_value={'status': 'ok', 'nodes': [{'node_id': 'test'}]}), \
                mock.patch.object(bridge, '_open_command_connection', side_effect=RuntimeError('unavailable')), \
                mock.patch.object(ue_bridge.time, 'sleep'), mock.patch.object(bridge, 'execute') as execute:
            result = bridge.connect()
        self.assertEqual(result['error_type'], 'ConnectionFailed')
        self.assertFalse(result['command_sent'])
        execute.assert_not_called()

    def test_node_failure_does_not_run_action(self):
        bridge = mock.Mock()
        bridge.connect.return_value = {'status': 'error', 'error_type': 'NodeNotFound'}
        args = SimpleNamespace(timeout=1, node='absent')
        action = mock.Mock()
        with mock.patch.object(ue_cli, '_make_bridge', return_value=bridge):
            result = ue_cli._run(args, action)
        self.assertFalse(result['command_sent'])
        action.assert_not_called()
        bridge.disconnect.assert_called_once()


if __name__ == '__main__':
    unittest.main()
