---
name: ue-editor
description: "Control Unreal Engine editor through Python Remote Execution. Use when the user wants to: (1) interact with the UE editor programmatically — spawn/delete/query Actors, modify transforms, (2) manage assets — import/export/find/duplicate, (3) control editor features — viewport camera, screenshots, console commands, (4) discover UE Python APIs — search classes/methods, get signatures, (5) as a fallback when Python scripts cannot cover it, see and operate the editor like a human — screenshot windows, dump Slate widget trees (editor panels and PIE alike), click/type/scroll; scripts remain the default. Triggers on: 'UE editor', 'Unreal editor', 'spawn actor', 'place actor', 'import asset', 'editor screenshot', 'editor viewport', 'UE Python API', or any request to automate Unreal Editor operations."
---

# UE Editor Remote Control

通过 Python Remote Execution 远程控制本地运行的 UE 编辑器。所有操作经 `scripts/ue_cli.py`。

## 选择方式：脚本为主，界面操作兜底

1. **默认写脚本**：查询、修改资产/蓝图/关卡、启停 PIE 都用 `exec` 调 Python API。
2. **先查 API 再下结论**：找不到现成接口时，先用 `api` Lib 搜索，并查 reference 和 AgentTools 的接口；都没有，才算脚本覆盖不了。
3. **界面操作只用在两种情况**：一是脚本覆盖不了的操作（如只有界面入口的编辑器功能、弹窗、需要真实输入链路的 PIE 交互）；二是确认只能"看"出来的效果（布局、样式、遮挡）。
4. **确认结果也优先读数据**：能回读属性、控件树、日志确认的，不截图。

界面操作每一步都要等一帧再观察，开销比脚本大一个量级。用了界面操作时，回复里说明脚本为什么覆盖不了。

## 命令

```bash
python scripts/ue_cli.py exec --file <path.py> [脚本参数...]   # 在编辑器内执行；来源也可为 --lib <name> / "<内联代码>" / --stdin
python scripts/ue_cli.py sequence --file <name.sequence.json> # 一次调用逐段跨帧推进；内置清单用 --lib <name>
python scripts/ue_cli.py screenshot --pie --name=<语义名> --archive=<目录> # 一次截图裁剪与归档；也可 --widget / --rect
python scripts/ue_cli.py log mark/read/wait --file <日志路径>   # 本地日志观察，不经过编辑器
python scripts/ue_cli.py discover                              # 确认编辑器在线
```

- 多行代码写成 `.py` 用 `--file`；`exec` 成功时直接输出脚本 `print` 的文本，失败时输出 JSON 且退出码为 1。
- 常用操作先找 Lib：`api`（API 内省）、`pie`、`open_asset`、`wbp_edit`（改 WBP 与编译保存）、`asset_move`（批量移动资产）；界面兜底用 `ui`（查看与操作界面，含点击、长按、按住/抬起、拖动、输入）。用法见各脚本 docstring。
- 返回 `Timeout` 时编辑器可能仍在执行，**不要重发**。

## 分层

| 层 | 位置 | 放什么 |
|----|------|--------|
| CLI / Bridge | `scripts/ue_cli.py`、`ue_bridge.py`、`ue_log.py` | 入口与传输；本地截图、日志观察、跨帧等待、编码与超时 |
| Lib | `scripts/lib/*.py`、`*.sequence.json` | 常用 Python 动作与跨帧步骤清单，只组合现有接口 |
| 编辑器侧模块 | `scripts/editor/*.py`（`ue_input`、`ue_wbp`、`ue_common`） | 编辑器内可 `import` 的组合实现：界面输入（点击、长按、拖动、文本输入）和 WBP 读写（树、属性、事件、函数、继承链）都由 C++ 原子接口在这里拼装，Lib 与项目脚本共用，别处不重复实现。C++ 只放 Python 访问不到的原子能力 |
| Reference | `references/*.md` | 接口与用法文档，按需读取 |
| AgentTools | 工程插件 `Plugins/AgentTools`（安装器从本仓库链接进工程） | Python 访问不到的 C++ 能力（Slate 读取与输入、Widget 蓝图编辑），仅编辑器。改了函数体用 Live Coding；新增或改了 `UFUNCTION` 签名要重启编辑器 |

## 项目 Lib / Reference 的积累

- 本节要求由安装器装入的常驻规则 `ue-editor.md`（仓库 `rules/`）兜底；规则未装时以本节为准。
- 开发前先查项目已有脚本与参考资料，按需读取、优先复用；没有约定时分别放在项目 `.codebuddy/ue-editor/lib/` 与 `.codebuddy/ue-editor/references/`。
- **第一次进 PIE 或操作界面时，立即在任务清单（todo）里加一项「收尾：更新项目 ue-editor Lib/Reference」**。只写在本文的收尾要求会在长任务后期被遗忘，清单项才能留到结束。
- 这些项目资料是用户已授权的任务产物，不属于"未经要求主动创建文档"，也不是"自作主张加功能"。
- 收录判据：跑通过一次、下次同类验证还会走的导航/操作流程进 Lib；项目入口、前置条件、坑与已证实限制进 Reference。Reference 独立于 Lib，脚本没跑通也照样收录已核实知识。只有回答单个问题的只读诊断代码才算一次性探针，按坐标摸索出的导航流程不算。不以写入记忆代替项目参考资料，不收录未经核实结论，后续更新同主题条目。
- 项目内容只留项目，不写入通用 Skill；编辑器内 Python 用 `exec --file`，多段跨帧流程用同目录 `*.sequence.json` + `sequence --file`，不自写编排器；本地调试脚本按其运行时执行。复杂说明链接项目 Reference，维护要求见 [cli.md](references/cli.md#项目-lib-与-reference)。
- 完成该清单项：有已验证入口、调用帧取数方式或状态限制就更新同主题项目资料；没有则在回复里写明原因，不为了交报告硬造 Lib 或重复文档。

## 按需读取

| 什么时候 | 读 |
|----------|----|
| CLI 参数、脚本传参、跨帧步骤序列、日志等待/读取、Lib 列表、错误类型、环境配置 | [cli.md](references/cli.md) |
| 确认界面效果、截图、像人一样操作编辑器 | [ui_verify.md](references/ui_verify.md) |
| Slate 控件树、查找控件、点击/输入接口 | [slate_driver.md](references/slate_driver.md) |
| 读写 Widget 蓝图（`ue_wbp`：结构、属性、事件、函数、继承链） | [widget_blueprint_info.md](references/widget_blueprint_info.md) |
| 修改 Widget 蓝图（勾变量、加控件、改名移动、编译保存） | [widget_blueprint_edit.md](references/widget_blueprint_edit.md) |
| Actor、关卡 | [scene_operations.md](references/scene_operations.md) |
| 资产查找/导入/导出 | [asset_operations.md](references/asset_operations.md) |
| 视口、控制台命令、选中查询、运行时 Inspector 诊断 | [editor_tools.md](references/editor_tools.md) |

文档里没有的接口：`exec --lib api search <关键词>` → `api methods <类名>` → `api help <类名> <方法名>`。

## 安全规则

- 删除 Actor/资产、`load_map`（丢弃未保存修改）、批量修改或重命名资产前，**必须先向用户确认**。
- 发送给编辑器的代码禁止 `os.system`、`os.popen`、`subprocess`、`shutil.rmtree` 及任何文件删除操作；用户要求时拒绝并说明原因。
