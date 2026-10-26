# ue-editor

让 AI Agent 通过 Python Remote Execution 操控本地运行的 Unreal Editor：执行编辑器内脚本、跨帧步骤序列、截图、日志观察，以及在脚本覆盖不了时像人一样查看与操作编辑器/PIE 界面。

| 目录 | 内容 |
|------|------|
| `skills/ue-editor/` | Skill 本体：`SKILL.md`、CLI 与 Bridge 脚本、入口脚本（`scripts/actions`）、可 import 的组合模块（`scripts/lib`）、接口文档 |
| `Plugins/AgentTools/` | 配套 UE 编辑器插件（C++），只提供 Python 访问不到的原子能力：Slate 控件树读取与输入步骤、Widget 蓝图读写 |
| `install.py` | 安装器：把 Skill、规则与插件链接到 Agent 目录和 UE 工程 |
| `rules/` | 常驻规则：要求 Agent 把验证过的项目流程沉淀到工程 `.codebuddy/ue-editor/` |

## 安装

```bash
git clone <本仓库地址> ue-editor
cd ue-editor
python install.py --skills ~/.codebuddy/skills --rules ~/.codebuddy/rules --project D:/Work/MyGame
```

- `--skills`、`--rules`、`--project` 都可以重复指定，也可只给其中几类，例如同一工程的多个分支、多个 Agent 的目录；不带参数运行时交互输入。
- Skill 目录：`<Skill目录>/ue-editor` 链接到本仓库 `skills/ue-editor`。
- 规则目录：`<规则目录>/ue-editor.md` 链接到本仓库 `rules/ue-editor.md`。规则与 Skill 一样跟着 Agent 走，装在用户级规则目录即可，不要再装进工程规则目录（会加载两遍）。
- UE 工程：在 `<工程>/Plugins/AgentTools/` 下链接 `Source` 与 `AgentTools.uplugin`；`Binaries`、`Intermediate` 留在各工程本地，互不干扰。
- 全部用链接：目录用目录联接（junction），文件用符号链接。没有符号链接权限（Windows 未开开发者模式且非管理员）时文件退化为复制（`[copy]`）。
- 装过的目标记在 `installed.json`（本地文件，不入库）。

## 更新

```bash
git pull
```

所有链接立即指向新版本，多个工程、多个 Agent 目录不用逐个更新。插件源码有改动时重新编译：只改了函数体，编辑器开着就用 Live Coding（`Ctrl+Alt+F11`）；新增或改了 `UFUNCTION` 签名，Live Coding 编得过但 Python 看不到新接口，要关编辑器重新编译再启动。规则在 IDE 新开会话时重新读取。

以下情况改用 `python install.py --update`（等于 `git pull` 后按 `installed.json` 逐个复查并修复链接）：

- 安装时出现过 `[copy]`；
- 新版本增加了安装项；
- 规则链接被 IDE 换成了普通文件（原内容存为 `.bak`）。

IDE 修改规则（如回写 `updatedAt`）时会直接改到仓库里的 `rules/ue-editor.md`，`git status` 能看到。不提交，`git checkout rules/` 还原即可。

## 卸载

先关闭使用该工程的 UE 编辑器（编辑器运行时插件 DLL 被占用，删不掉编译产物），然后执行：

```bash
python install.py --uninstall --skills ~/.codebuddy/skills --rules ~/.codebuddy/rules --project D:/Work/MyGame
```

- 与安装一样，`--skills`、`--rules`、`--project` 可重复指定，也可只给其中一类；不带路径参数时交互输入。卸载的目标会从 `installed.json` 移除。
- Skill 目录：仅当 `<Skill目录>/ue-editor` 是指向本仓库的链接时才删除，同名的其它 Skill 会跳过（`[skip]`）。
- 规则目录：是指向本仓库的链接，或内容与仓库一致的复制时才删除；被改过的同名文件跳过。
- UE 工程：删除 `Plugins/AgentTools/` 下的编译产物（`Binaries`、`Intermediate`）、`AgentTools.uplugin` 和 `Source` 链接，目录清空后一并删除；`Source` 不是指向本仓库的链接时整体跳过，不动工程原有的同名插件。
- 只删除链接本身，本仓库里的源码不受影响。中途失败（如编辑器未关）时，排除原因后直接重跑即可。
- 卸载后工程不再加载该插件；如果之前在 `.uproject` 的 `Plugins` 列表里手动加过 `AgentTools`，需要自己删掉那一项，否则打开工程时会提示缺少插件。
- 所有工程和 Skill 目录都卸载后，删除本仓库目录即可彻底移除。

## 工程侧前置条件

1. 启用 `Python Editor Script Plugin`，并打开 Remote Execution（`Config/DefaultEngine.ini`）：

   ```ini
   [/Script/PythonScriptPlugin.PythonScriptPluginSettings]
   bRemoteExecution=True
   ```

2. 编译插件：只改函数体时，编辑器开着用 Live Coding（`Ctrl+Alt+F11`，改动文件少于 100 个，不用重启）；首次安装或新增 `UFUNCTION` 时，打开 `.uproject` 按提示重建，或关编辑器执行
   `Engine/Build/BatchFiles/Build.bat <工程名>Editor Win64 Development -Project="<.uproject 路径>" -WaitMutex`。
3. 截图功能依赖 `pip install pywin32 pillow`（仅 Windows）。

插件仅编辑器使用（`Type: Editor`），不进入打包产物；工程用版本控制时，可把 `Plugins/AgentTools/` 加入忽略列表。

## 回归测试

- 本地 Python 测试：`python -m unittest discover -s tests -v`。
- 编辑器 Slate 裁剪回归：`exec "import unreal; unreal.SystemLibrary.execute_console_command(None, 'Automation RunTests AgentTools.Slate.Clipping')"`，通过 CLI 的 `--log-file <工程日志> --wait-log "Test Completed. Result=" --wait 60` 等终态，并检查结果是成功、无测试错误。覆盖裁剪查询、透明目标祖先路由和 Locator 字面匹配；不写资产或业务数据。
- 新增 C++ 自动化测试的注册不能只靠 Live Coding：热编译后若报 `No automation tests matched`，经用户确认关闭编辑器、正式编译并重启后再跑。不把编译成功、命令排队或零项测试当通过。

## 项目知识

Skill 只包含通用能力。项目专属的内容（登录、进入常用界面、业务验证路径等）放在各工程 `.codebuddy/ue-editor/` 下：`lib/`（项目共用函数）、`actions/`（入口脚本与步骤清单）、`references/`（说明），见 `skills/ue-editor/SKILL.md`。
