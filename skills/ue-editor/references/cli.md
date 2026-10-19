# ue_cli.py 用法参考

## 前提条件

UE 编辑器必须启用 Python Remote Execution（`Config/DefaultEngine.ini`）：

```ini
[/Script/PythonScriptPlugin.PythonScriptPluginSettings]
bRemoteExecution=True
RemoteExecutionMulticastGroupEndpoint=239.0.0.1:6766
RemoteExecutionMulticastBindAddress=127.0.0.1
```

未启用时：Editor Preferences → Plugins → Python → 勾选 "Enable Remote Execution"。组播地址与绑定地址由 CLI 自动从项目 ini 读取，也可用参数覆盖。

## exec

代码来源四选一，其余行为完全一致：

```bash
python scripts/ue_cli.py exec --file .codebuddy/temp/xxx/do_something.py   # 本地文件，多行代码首选（UTF-8，可含中文）
python scripts/ue_cli.py exec --lib api search viewport                     # Lib 常用脚本
python scripts/ue_cli.py exec "import unreal; print(unreal.SystemLibrary.get_engine_version())"
echo "import unreal; print('hello')" | python scripts/ue_cli.py exec --stdin
python scripts/ue_cli.py exec --file do_rename.py --timeout 300             # 耗时操作加大等待
```

- **脚本参数**：CLI 不认识的参数都传给脚本：`--k=v` 和 `--k`（布尔）进 `OPTS`，其余按顺序进 `ARGS`，四种来源都可用。带值的选项必须写成 `--k=v`（写成 `--k v` 时 `v` 会进 `ARGS`）。
- **输出**：成功时直接输出脚本 `print` 的文本（无输出时为 `[ok]`，用了 `--wait-until` 时末尾附 `[waited Ns]`），退出码 0；失败时输出 JSON（`error_type`、`message` 为 traceback 且行号与脚本文件一致、`output` 为报错前已 print 的内容），退出码 1。要拿某个值就 `print` 出来。
- **编码**：输入按 UTF-8 解码并忽略 BOM，输出统一 UTF-8；超过一行的代码写成 `.py` 用 `--file`，避开 Shell 转义。
- **源码载荷**：`--file` 读取内容后按源码发送，Bridge 用 `ExecuteStatement` 包装多语句执行；可保留模块 docstring、`.py` 字符串和原始行号，不需要改成注释。旧版 Bridge 使用 `ExecuteFile` 会把源码中某些 `.py` 文本误当文件名。
- **编辑器内路径**：`unreal.Paths.project_dir()` 可能是相对路径，需要磁盘绝对路径时用 `unreal.Paths.convert_relative_path_to_full(...)`；不要假定它与本地 CLI 工作目录相同。
- **跨帧等待**：编辑器内的脚本会阻塞当前帧，无法等待"下一帧才生效"的结果。需要等待时加 `--wait-until "<表达式>" [--wait 秒数]`，CLI 在执行成功后每秒求值一次，直到为真；超时返回 `WaitTimeout`。执行前会先预检一次，条件已成立时输出 `[warning]`（等待不能证明操作生效，要换条件）。
- **等待中远控超时**：PIE 启动、地图加载会阻塞游戏线程，单次求值可能超过 `--timeout`。此时 CLI 不重发命令，而是继续收那条尚未返回的结果直到 `--wait` 用完；仍不成立才报 `WaitTimeout` / `SequenceWaitTimeout`。`--timeout` 只管单次命令结果，不覆盖整段等待。
- **连接恢复**：换地图等重操作可能让远控短暂不可发现。命令发送前遇到 `NoEditorFound` 时自动额外发现一次并输出告警，默认两次发现合计至多约 10 秒；显式 `discover` 不额外重试。`Timeout` / `InvalidResponse` 等命令发送后的错误不自动重发，以免重复执行改动。

## sequence：通用跨帧步骤

`sequence --file <名称.sequence.json> [--param name=value ...]` 或 `sequence --lib <名称> [--param name=value ...]`，一次连接按顺序推进“等待 → 执行 → 等待”；项目只提供动作脚本与纯查询条件，不在编辑器内 sleep，不复制编排器。

清单与脚本统一放在各自 `lib/`：Python 动作用 `<名称>.py`，步骤清单用 `<名称>.sequence.json`。`--file` / `--lib` 必填且互斥；`sequence --lib foo` 只查 Skill 的 `scripts/lib/foo.sequence.json`，不扫描项目、不回退到同名 Python 脚本。项目清单用 `--file` 明确指定。清单内的 `lib` 字段仍指 Skill 的 Python Lib，不表示嵌套序列。

清单为 `{"steps": [...]}`，每步支持：

| 字段 | 含义 |
|------|------|
| `name` | 用于进度与失败诊断的步骤名 |
| `file` / `lib` / `code` | 三选一：项目脚本、Skill Python Lib 名或 Python 源码 |
| `args` / `options` | 注入脚本 `ARGS` 列表 / `OPTS` 对象，默认空 |
| `wait_before` | 执行动作前轮询的 Python 表达式；省略即直接执行 |
| `wait_until` | 动作执行后轮询表达式；省略即不等待 |
| `state` | 等待超时或执行异常时读取的诊断表达式，可返回世界、当前状态等 |
| `wait` | 每个等待阶段最长秒数，默认 60，范围 0~3600 |

脚本相对路径以清单所在目录为准。`--param` 值始终是字符串，以 `SEQUENCE_PARAMS` 注入脚本/条件所在的编辑器全局上下文，不做字符串插值或命令拼接；参数在每步执行前等待之前安装。首步等待所用函数需已定义，或用直接查询表达式；不能依赖尚未执行的同一步脚本定义——`wait_before` 出现 `NameError` 时 CLI 会在 `hint` 里提示这一点。

- 所有文件、字段和语法在连接/动作前校验；条件必须只读、不发请求、不修改业务状态。就绪判据由项目提供，不能仅用 `PIE running` 代替客户端或业务就绪。
- 动作每步只发一次；每 0.5 秒轮询条件。已完成状态的跳过由项目脚本自行判断，CLI 不自动重试、回滚、重连重放或替换账号；超时后先检查现场，不直接重跑整份清单。
- 失败立即停止后续步骤，JSON 标明 `step`、从 0 开始的 `step_index`、`phase`、`completed` 和当前动作输出。`SequenceWaitTimeout` 带最近条件及 `last_state`（若提供）；执行/条件异常保留原错误并尽力取只读状态；传输超时不追加查询。`command_sent` 只说明本步动作是否提交，不说明业务 GM/点击实际成功。
- 成功输出已完成步骤、动作输出和 `timings.wait_before/execute/wait_until` 各阶段耗时；失败也保留已执行阶段耗时。执行耗时包含远控与可选输入断言回读，后置 `waited` 兼容保留。退出码成功 0、失败 1；`--timeout` 是单次远控结果等待，不是整份序列总时长。若要区分 PIE 会话启动与业务入口加载，项目清单拆成两个命名步骤，不由通用工具猜业务就绪。
- 步骤清单与脚本具有相同权限：危险切图、删除或数据写入仍须确认，不能因放进 sequence 跳过授权。项目清单放在项目 `.codebuddy/ue-editor/lib/`，通用 Skill 不收录具体账号、页面或登录状态机。

## Lib 脚本

`exec --lib <name> [参数...]` 执行 `scripts/lib/<name>.py`。用法写在各脚本 docstring 里，缺参数时也会返回用法。

| 脚本 | 用途 |
|------|------|
| `api` | API 内省：`search <关键词>` / `methods <类名>` / `help <类名> [方法名]` |
| `pie` | PIE 启停、状态与世界上下文：`start` / `stop` / `status` / `worlds`（启停需配合 `--wait-until`，见 docstring） |
| `open_asset` | 打开资产编辑器（WBP 设计器、蓝图等） |
| `wbp_edit` | 改 WBP 并把改动落盘：`list` / `rename` / `set` / `add` / `replace` / `remove` / `save`；改控件默认编译保存，`--no-save` 攒下的改动用 `save` 统一收尾 |
| `asset_move` | 批量移动/改名资产与引用检查：`check` 先看存在性与引用方，`move` 移动（`--save-referencers`），`redirectors <目录>` 列旧路径残留 |
| `ui` | 查看与操作编辑器界面：`windows` / `tree` / `find` / `focus` / `click` / `type` / `key` / `scroll`（依赖 AgentTools） |

新增 Lib 脚本：只组合现有接口、在多个任务里反复手写过的操作才沉淀；模块 docstring 写用法；只用 `ARGS` / `OPTS` 取参数，不要用 `argparse`（解析失败会 `sys.exit`）。

### 项目 Lib 与 Reference

项目中的固定流程（如登录、进入常用界面、查询特定业务状态）及其相关知识，可以在实际开发中主动沉淀，不需要通用 Skill 收录具体业务。

1. **先复用**：查项目既有脚本、参考资料和各脚本 docstring，只读与当前任务相关的内容；没有既有约定时分别用项目 `.codebuddy/ue-editor/lib/` 与 `.codebuddy/ue-editor/references/`，不要每个任务另建一套。
2. **先验证再收录**：只保存实际跑通且预期会复用的流程，不搬入试错探针；按流程职责命名，Python 用模块 docstring、本地其它语言用注释头，写用途、前置状态、参数、调用方式与成功判据。
3. **保持简单**：只组合现有接口，不硬编码个人账号或凭证。编辑器内 Python Lib 用 `ARGS` / `OPTS` 接收参数，通过 `exec --file <脚本绝对路径> [参数...]` 调用；本地 Inspector 等脚本用对应运行时直接执行，不发送进 UE Python。`--lib` 仍只查 Skill 自带 Python 脚本。
4. **分清执行位置**：编辑器内脚本不能用 sleep/轮询阻塞当前帧等界面就绪；单段等待用 CLI 的 `--wait-until` / `--wait-log`，多段“等待再执行”沉淀为同目录 `<名称>.sequence.json`，用通用 `sequence` 推进，不自写编排器。本地 Inspector 等调试脚本仍由对应运行时有界等待和清理；sequence 不启动或管理本地进程。
5. **Reference 按需沉淀**：脚本简单用法留 docstring；复杂的项目入口、前置条件、业务约定、验证路径和已证实限制按主题写入 Reference，有关联脚本再链接。Reference 不依赖可用 Lib：通道失败不妨碍收录其它已验证路径，不能仅以“没有脚本可保留”跳过资料沉淀，也不以记忆替代项目资料。不是每个 Lib 都要配一篇文档；已有项目文档优先链接，不重复复制。记录来源与核验日期，待确认事项单独标出，不作为已验证结论。
6. **收尾检查与维护**：完成任务、删除探针前，检查是否新确认了可复用入口、世界/调试目标关联、真实调用帧取数方式或页面状态限制；值得保留就更新同主题项目 Reference，只有脚本本身满足复用条件才进 Lib。没有合适收获时不造文件，回复里简述原因。后续变化先核实再更新原条目并重验，不复制版本；资料增多时用简短“什么时候读哪篇”索引，不全量加载。项目 Lib / Reference 不按临时文件清理；权限、危险操作确认和超时不重发规则不变。

## screenshot

见 [ui_verify.md](ui_verify.md)。

## log：本地日志观察

只读本地 UTF-8 日志，不连接编辑器、不依赖 AgentTools。路径显式指定，通常在项目 `Saved/Logs/`；不猜项目名，多实例需选对应文件。

```powershell
$log = 'G:\MyProject\Saved\Logs\MyProject.log'
$base = python scripts/ue_cli.py log mark --file $log | ConvertFrom-Json
# 在这里执行要验证的操作
python scripts/ue_cli.py log read --file $log --since $base.cursor --filter '[MyFeature]' --lines 40
python scripts/ue_cli.py log wait --file $log --since $base.cursor --text '[MyFeature] Done' --wait 10
```

- `mark`：返回当前文件末尾 `cursor`，操作前取一次。不保存额外基线文件。
- `read`：返回新增完整行、统计与新 `cursor`。不带 `--since` 时读近期日志；`--filter` 为区分大小写的字面包含匹配。续读使用返回的游标，不能跨文件。
- **扫描范围**：`start_offset` / `end_offset` 是实际消费的字节区间，`file_size` 是读取时文件大小；`scanned_lines` 是过滤前行数，`line_count` 是匹配数。`history_truncated=true` 表示省略了更早历史，零匹配只能说明此次范围无匹配，不代表全日志没有；`scan_truncated=true` 时用返回游标续读。
- `wait`：从明确基线等待新完整行包含 `--text`；旧日志不满足条件。成功输出匹配行，超时输出有限的新增近期上下文及新游标；不重发任何操作。
- `--lines` 限 1~200，`read` 默认 80、`wait` 默认 40；单行最多 2000 字符，总正文最多 12000 字符。JSON 中 `truncated` 表示输出限量，`scan_truncated` 表示单次最多扫描 1 MiB 后还有未读数据，可用新游标继续读。等待会自动继续扫描。
- 输出 JSON，成功退出码 0，失败退出码 1。半行尚未换行则不消费（`pending_bytes`）；基线落在旧半行时，其后补完的那一行不作新增证据。
- 文件轮转、变小或基线附近改写时报 `LogChanged`，不静默从头重读。校验使用文件身份和基线头尾各最多 64 字节；同文件截断后若恰好恢复这些校验字节且已增长过游标，不能识别，已知重启/重写后应重新取基线。

### 操作与等待放在同一次调用

```powershell
python scripts/ue_cli.py exec --lib ui click 'name=Btn_Apply' --log-file $log --wait-log '[MyFeature] Applied' --wait 10
```

CLI 在命令执行前取基线，执行成功后在本地等待新增日志；`--log-lines` 控制输出行数，默认 40。与 `--wait-until` 二选一。基线失败不发送命令；执行后 `LogWaitTimeout` 带 `command_sent=true`，不能直接重试改动。日志存在只证明文本出现，不自动判断业务通过。

## 公共参数

参数跟在子命令之后（如 `discover --timeout 5`）：

- `--node <id>`：指定编辑器节点 ID（多实例时使用，节点 ID 用 `discover` 查）
- `--timeout <seconds>`：等待命令结果的秒数（默认 30）；`discover` 下为发现超时（默认 5）
- `--multicast-group <ip:port>` / `--multicast-bind <ip>`：组播地址与绑定地址

## 错误类型

| error_type | 原因 | 建议 |
|------------|------|------|
| `NoEditorFound` | 未发现 UE 编辑器 | 确认编辑器运行且 bRemoteExecution=True |
| `ConnectionFailed` | TCP 连接失败 | 检查端口 6776 是否被占用 |
| `Timeout` | 等待结果超时 | 编辑器可能仍在执行，**不要重发**；用 `exec "print(1)"` 探测恢复后核对结果，耗时操作加大 `--timeout` |
| `WaitTimeout` | `--wait-until` 条件在 `--wait` 秒内未成立 | 命令本身已执行；确认条件表达式，或加大 `--wait` |
| `SequenceFileError` | 清单来源、字段、文件或语法不可用 | 校验 `--lib` 名称/`--file` 路径与所有步骤；尚未运行步骤 |
| `SequenceWaitTimeout` | 步骤前置/后置条件未成立 | 查看 `step/phase/last_state/completed`，不要重放已发送动作 |
| `LogWaitTimeout` | 等待期内未出现新增匹配日志 | 查看新增上下文；操作已发送时不要重发 |
| `LogChanged` | 日志轮转、截断或校验位置改写 | 先确认日志文件与操作结果，再重新取基线 |
| `LogFileError` / `LogCursorInvalid` / `LogArguments` | 日志文件、游标或参数不可用 | 确认文件可读、游标对应、参数范围 |
| `LogLineTooLong` | 单行超过扫描上限 | 人工检查异常长行，不静默跳过 |
| `InvalidResponse` | 连接在回包完整前被关闭 | 多为编辑器崩溃或重启，先 `discover` 确认 |
| `FileReadError` | `--file` 文件读取失败 | 检查路径 |
| `ScriptNotFound` | `--lib` 脚本名不存在 | 看 `suggestion` 里的可用脚本 |
| `WindowNotFound` / `CaptureFailed` | 截图找不到窗口或窗口最小化；`--popup` 时没有打开的弹出层 | `screenshot --list` 查看可用窗口，让用户还原窗口 |
| `WidgetNotFound` | `screenshot --widget` 没有命中第 `--index` 个控件 | 先 `ui find` 确认 Locator |
| `PIEViewportNotFound` / `PIEViewportAmbiguous` | PIE 视口未排布或目标不唯一 | `screenshot --pie --list` 后按实际实例选择 |
| `ScreenshotArguments` | 截图命名、归档或实例参数不合法 | 检查 name/out/archive 及 --instance 的使用 |
| `InputAssertionFailed` | 发送前命中路径不符合预期或目标失效 | 查 input.hit / clicks_sent，不重放部分双击 |
| `InputWaitTimeout` | 断言点击结果仍在排队 | 保存 request_id，恢复后查询，不能重发 |
| `DependencyMissing` | 截图缺少 pywin32/Pillow | `pip install pywin32 pillow` |
| `ExecutionError` | Python 代码执行错误 | 看 `message` 里的 traceback；Lib 脚本缺参数时 `message` 即用法 |

`ExecutionError` 提示 `AgentSlateDriverFunctionLib` 或 `AgentWidgetBlueprintInfoFunctionLib` 找不到时，说明工程插件 `AgentTools` 未安装、未编译或未启用（安装见仓库 README）。
