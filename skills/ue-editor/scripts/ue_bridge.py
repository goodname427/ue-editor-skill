"""
UE Editor Python Remote Execution 桥接模块。
通过 UDP 组播发现本地 UE 编辑器实例，通过 TCP 发送 Python 命令。
"""

import sys
import os
import json
import uuid
import time
import socket
import struct
import threading
import logging
import configparser
import glob

# ============================================================
# 协议常量 (与 remote_execution.py 保持一致)
# ============================================================
_PROTOCOL_VERSION = 1
_PROTOCOL_MAGIC = 'ue_py'

_TYPE_PING = 'ping'
_TYPE_PONG = 'pong'
_TYPE_OPEN_CONNECTION = 'open_connection'
_TYPE_CLOSE_CONNECTION = 'close_connection'
_TYPE_COMMAND = 'command'
_TYPE_COMMAND_RESULT = 'command_result'

_NODE_PING_SECONDS = 1
_NODE_TIMEOUT_SECONDS = 5

MODE_EXEC_FILE = 'ExecuteFile'
MODE_EXEC_STATEMENT = 'ExecuteStatement'
MODE_EVAL_STATEMENT = 'EvaluateStatement'

DEFAULT_MULTICAST_TTL = 0
DEFAULT_MULTICAST_GROUP_ENDPOINT = ('239.0.0.1', 6766)
DEFAULT_MULTICAST_BIND_ADDRESS = '127.0.0.1'
DEFAULT_COMMAND_ENDPOINT = ('127.0.0.1', 6776)
DEFAULT_RECEIVE_BUFFER_SIZE = 65536
DEFAULT_DISCOVER_TIMEOUT = 5
DEFAULT_COMMAND_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3

logger = logging.getLogger('ue_bridge')


def _parse_ini_config(search_dirs=None):
    """从项目 DefaultEngine.ini 中读取 PythonScriptPlugin 的 Remote Execution 配置。
    返回 (multicast_group, multicast_bind, multicast_ttl) 或 None。
    """
    if search_dirs is None:
        # 从脚本所在目录向上搜索
        search_dirs = [os.getcwd()]

    ini_section = '/Script/PythonScriptPlugin.PythonScriptPluginSettings'
    for start_dir in search_dirs:
        d = os.path.abspath(start_dir)
        for _ in range(10):  # 最多向上 10 层
            candidate = os.path.join(d, 'Config', 'DefaultEngine.ini')
            if os.path.isfile(candidate):
                try:
                    cp = configparser.ConfigParser(strict=False)
                    cp.read(candidate, encoding='utf-8')
                    if cp.has_section(ini_section):
                        sec = cp[ini_section]
                        result = {}
                        ep = sec.get('RemoteExecutionMulticastGroupEndpoint', '')
                        if ep and ':' in ep:
                            host, port = ep.rsplit(':', 1)
                            result['multicast_group'] = (host, int(port))
                        bind = sec.get('RemoteExecutionMulticastBindAddress', '')
                        if bind:
                            result['multicast_bind'] = bind
                        ttl = sec.get('RemoteExecutionMulticastTtl', '')
                        if ttl:
                            result['multicast_ttl'] = int(ttl)
                        if result:
                            logger.info(f'从 {candidate} 读取到配置: {result}')
                            return result
                except Exception as e:
                    logger.warning(f'解析 {candidate} 失败: {e}')
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return None


# ============================================================
# 消息序列化
# ============================================================
class _Message:
    def __init__(self, type_=None, source=None, dest=None, data=None):
        self.type_ = type_
        self.source = source
        self.dest = dest
        self.data = data

    def to_bytes(self):
        obj = {
            'version': _PROTOCOL_VERSION,
            'magic': _PROTOCOL_MAGIC,
            'type': self.type_,
            'source': self.source,
        }
        if self.dest:
            obj['dest'] = self.dest
        if self.data:
            obj['data'] = self.data
        return json.dumps(obj, ensure_ascii=False).encode('utf-8')

    def from_bytes(self, raw):
        try:
            obj = json.loads(raw.decode('utf-8'))
            if obj.get('version') != _PROTOCOL_VERSION:
                return False
            if obj.get('magic') != _PROTOCOL_MAGIC:
                return False
            self.type_ = obj['type']
            self.source = obj['source']
            self.dest = obj.get('dest')
            self.data = obj.get('data')
            return True
        except Exception:
            return False

    def passes_filter(self, node_id):
        return self.source != node_id and (not self.dest or self.dest == node_id)


# ============================================================
# 结构化返回
# ============================================================
def _ok(output='', result=None, **extra):
    resp = {'status': 'ok', 'output': output, 'result': result}
    resp.update(extra)
    return resp


def _error(error_type, message, suggestion='', output=''):
    resp = {
        'status': 'error',
        'error_type': error_type,
        'message': message,
        'suggestion': suggestion,
    }
    if output:
        resp['output'] = output
    return resp


def _output_text(output):
    """UE 返回的 output 是 [{type, output}] 列表，拼成纯文本；统一为 \\n 换行（UE 日志会把 \\r\\n 再转一次）。"""
    if isinstance(output, list):
        output = ''.join(o.get('output', '') for o in output if isinstance(o, dict))
    return (output or '').replace('\r', '')


# ============================================================
# UEBridge
# ============================================================
class UEBridge:
    """与本地 UE 编辑器进行 Python Remote Execution 通信的桥接器。"""

    def __init__(
        self,
        multicast_group=None,
        multicast_bind=None,
        command_endpoint=None,
        multicast_ttl=None,
        auto_detect_config=True,
        command_timeout=None,
    ):
        # 从 ini 自动读取配置（可被显式参数覆盖）
        ini_cfg = {}
        if auto_detect_config:
            ini_cfg = _parse_ini_config() or {}

        self._multicast_group = multicast_group or ini_cfg.get('multicast_group', DEFAULT_MULTICAST_GROUP_ENDPOINT)
        self._multicast_bind = multicast_bind or ini_cfg.get('multicast_bind', DEFAULT_MULTICAST_BIND_ADDRESS)
        self._command_endpoint = command_endpoint or DEFAULT_COMMAND_ENDPOINT
        self._multicast_ttl = multicast_ttl if multicast_ttl is not None else ini_cfg.get('multicast_ttl', DEFAULT_MULTICAST_TTL)
        self._command_timeout = command_timeout or DEFAULT_COMMAND_TIMEOUT
        self._node_id = str(uuid.uuid4())

        self._broadcast_sock = None
        self._listen_thread = None
        self._running = False
        self._remote_nodes = {}
        self._nodes_lock = threading.RLock()

        self._cmd_listen_sock = None
        self._cmd_channel_sock = None
        self._connected_node_id = None

    # ----------------------------------------------------------
    # 节点发现
    # ----------------------------------------------------------
    def discover(self, timeout=DEFAULT_DISCOVER_TIMEOUT):
        """发现本地运行的 UE 编辑器实例，返回节点列表。"""
        try:
            self._start_broadcast()
            deadline = time.time() + timeout
            while time.time() < deadline:
                time.sleep(0.05)
                with self._nodes_lock:
                    if self._remote_nodes:
                        break
            self._stop_broadcast()
            with self._nodes_lock:
                nodes = []
                for nid, ndata in self._remote_nodes.items():
                    node = dict(ndata)
                    node['node_id'] = nid
                    nodes.append(node)
            if not nodes:
                return _error(
                    'NoEditorFound',
                    '未发现任何运行中的 UE 编辑器实例。',
                    '请确认编辑器已运行且启用了 Python Remote Execution (bRemoteExecution=True)。',
                )
            return _ok(nodes=nodes)
        except Exception as e:
            return _error('DiscoverError', str(e))

    def _start_broadcast(self):
        self._remote_nodes = {}
        self._running = True
        self._broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        if hasattr(socket, 'SO_REUSEPORT'):
            self._broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        else:
            self._broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._broadcast_sock.bind((self._multicast_bind, self._multicast_group[1]))
        self._broadcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        self._broadcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self._multicast_ttl)
        self._broadcast_sock.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
            socket.inet_aton(self._multicast_bind if self._multicast_bind != '0.0.0.0' else '127.0.0.1')
        )
        mreq = socket.inet_aton(self._multicast_group[0]) + socket.inet_aton(
            self._multicast_bind if self._multicast_bind != '0.0.0.0' else '0.0.0.0'
        )
        self._broadcast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        # 超时决定 _stop_broadcast 等线程退出的时长，每次命令会启停两次广播
        self._broadcast_sock.settimeout(0.1)
        self._listen_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._listen_thread.start()

    def _stop_broadcast(self):
        self._running = False
        if self._listen_thread:
            self._listen_thread.join(timeout=3)
            self._listen_thread = None
        if self._broadcast_sock:
            try:
                self._broadcast_sock.close()
            except Exception:
                pass
            self._broadcast_sock = None

    def _broadcast_loop(self):
        last_ping = 0
        while self._running:
            now = time.time()
            if now - last_ping >= _NODE_PING_SECONDS:
                last_ping = now
                msg = _Message(_TYPE_PING, self._node_id)
                try:
                    self._broadcast_sock.sendto(msg.to_bytes(), self._multicast_group)
                except Exception:
                    pass
            # 接收
            try:
                data = self._broadcast_sock.recv(DEFAULT_RECEIVE_BUFFER_SIZE)
                if data:
                    m = _Message()
                    if m.from_bytes(data) and m.passes_filter(self._node_id):
                        if m.type_ == _TYPE_PONG:
                            with self._nodes_lock:
                                self._remote_nodes[m.source] = m.data or {}
            except socket.timeout:
                pass
            except Exception:
                pass
            # 超时清理
            with self._nodes_lock:
                expired = [nid for nid, _ in self._remote_nodes.items()]  # 简化：发现阶段不做过期清理
            time.sleep(0.1)

    # ----------------------------------------------------------
    # 连接管理
    # ----------------------------------------------------------
    def connect(self, remote_node_id=None, timeout=DEFAULT_DISCOVER_TIMEOUT):
        """连接到指定（或自动发现的第一个）UE 编辑器节点。"""
        # 发现节点
        disc = self.discover(timeout)
        if disc['status'] != 'ok':
            return disc
        nodes = disc['nodes']

        if remote_node_id:
            target = None
            for n in nodes:
                if n['node_id'] == remote_node_id:
                    target = n
                    break
            if not target:
                return _error('NodeNotFound', f'未找到节点 {remote_node_id}。', '可用节点: ' + ', '.join(n['node_id'] for n in nodes))
        else:
            target = nodes[0]

        target_id = target['node_id']

        # 建立 TCP 命令连接（含重试）
        for attempt in range(DEFAULT_MAX_RETRIES):
            try:
                return self._open_command_connection(target_id)
            except Exception as e:
                logger.warning(f'连接尝试 {attempt+1}/{DEFAULT_MAX_RETRIES} 失败: {e}')
                if attempt == DEFAULT_MAX_RETRIES - 1:
                    return _error('ConnectionFailed', f'连接节点 {target_id} 失败（已重试 {DEFAULT_MAX_RETRIES} 次）: {e}')
                time.sleep(1)

    def _open_command_connection(self, remote_node_id):
        self.disconnect()
        self._connected_node_id = remote_node_id

        # 启动 TCP 监听
        self._cmd_listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        if hasattr(socket, 'SO_REUSEPORT'):
            self._cmd_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        else:
            self._cmd_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._cmd_listen_sock.bind(self._command_endpoint)
        self._cmd_listen_sock.listen(1)
        self._cmd_listen_sock.settimeout(5)

        # 通过 UDP 广播 open_connection 请求
        self._start_broadcast()
        try:
            for _ in range(6):
                open_msg = _Message(_TYPE_OPEN_CONNECTION, self._node_id, remote_node_id, {
                    'command_ip': self._command_endpoint[0],
                    'command_port': self._command_endpoint[1],
                })
                self._broadcast_sock.sendto(open_msg.to_bytes(), self._multicast_group)
                try:
                    self._cmd_channel_sock, _ = self._cmd_listen_sock.accept()
                    self._cmd_channel_sock.setblocking(True)
                    self._cmd_channel_sock.settimeout(self._command_timeout)
                    return _ok(output=f'已连接到节点 {remote_node_id}', node_id=remote_node_id)
                except socket.timeout:
                    continue
            raise RuntimeError('UE 编辑器未响应 TCP 连接请求。')
        finally:
            self._stop_broadcast()

    def disconnect(self):
        """断开当前命令连接。"""
        if self._cmd_channel_sock:
            try:
                self._cmd_channel_sock.close()
            except Exception:
                pass
            self._cmd_channel_sock = None
        if self._cmd_listen_sock:
            try:
                self._cmd_listen_sock.close()
            except Exception:
                pass
            self._cmd_listen_sock = None
        self._connected_node_id = None

    @property
    def is_connected(self):
        return self._cmd_channel_sock is not None

    # ----------------------------------------------------------
    # 命令执行
    # ----------------------------------------------------------
    def run_command(self, command, exec_mode=MODE_EXEC_FILE, unattended=True):
        """向 UE 编辑器发送 Python 命令并返回结果。"""
        if not self.is_connected:
            return _error('NotConnected', '尚未建立连接。', '请先调用 connect() 连接到 UE 编辑器。')
        try:
            msg = _Message(_TYPE_COMMAND, self._node_id, self._connected_node_id, {
                'command': command,
                'unattended': unattended,
                'exec_mode': exec_mode,
            })
            self._cmd_channel_sock.sendall(msg.to_bytes())

            # 接收结果：TCP 分段到达，收到能完整解析为止
            data = b''
            result_msg = _Message()
            parsed = False
            while not parsed:
                part = self._cmd_channel_sock.recv(DEFAULT_RECEIVE_BUFFER_SIZE)
                if not part:
                    break
                data += part
                parsed = result_msg.from_bytes(data)

            if not parsed:
                return _error('InvalidResponse', f'UE 编辑器返回了无效响应（已收 {len(data)} 字节，连接被关闭）。')

            if result_msg.type_ != _TYPE_COMMAND_RESULT:
                return _error('UnexpectedMessage', f'期望 command_result，收到 {result_msg.type_}。')

            result_data = result_msg.data or {}
            if result_data.get('success', False):
                return _ok(
                    output=_output_text(result_data.get('output', '')),
                    result=result_data.get('result', ''),
                )
            else:
                return _error(
                    'ExecutionError',
                    _output_text(result_data.get('result', '命令执行失败')).replace('\n\n', '\n'),
                    output=_output_text(result_data.get('output', '')),
                )
        except socket.timeout:
            return _error(
                'Timeout',
                f'等待结果超时 ({self._command_timeout}s)。',
                '编辑器可能仍在执行该命令（如 rename_asset 触发 P4 签出会卡 1~3 分钟），不要重发；'
                '稍后用 exec "print(1)" 探测编辑器恢复后再核对结果，长任务用 --timeout 加大等待。',
            )
        except Exception as e:
            return _error('CommandError', str(e))

    def execute(self, command):
        """单语句载荷包装多语句源码，避免 ExecuteFile 把源码中的 .py 当作路径。"""
        payload = "exec(compile(%r, '<ue-bridge>', 'exec'))" % command
        return self.run_command(payload, MODE_EXEC_STATEMENT)

    def evaluate(self, expression):
        """EvaluateStatement 模式求值并返回。"""
        return self.run_command(expression, MODE_EVAL_STATEMENT)
