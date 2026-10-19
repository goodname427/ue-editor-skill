# ue-editor

让 AI Agent 通过 Python Remote Execution 操控本地运行的 Unreal Editor：执行编辑器内脚本、跨帧步骤序列、截图、日志观察，以及在脚本覆盖不了时像人一样查看与操作编辑器/PIE 界面。

| 目录 | 内容 |
|------|------|
| `skills/ue-editor/` | Skill 本体：`SKILL.md`、CLI 与 Bridge 脚本、常用 Lib、接口文档 |
| `Plugins/AgentTools/` | 配套 UE 编辑器插件（C++）：Slate 控件树读取与合成输入、Widget 蓝图读取与编辑 |
| `install.py` | 安装器：把 Skill 与插件链接到 Agent 的 Skill 目录和 UE 工程 |

## 安装

```bash
git clone <本仓库地址> ue-editor
cd ue-editor
python install.py --skills ~/.codebuddy/skills --project D:/Work/MyGame
```

- `--skills`、`--project` 都可以重复指定，例如同一工程的多个分支、多个 Agent 的 Skill 目录；不带参数运行时交互输入。
- Skill 目录：`<Skill目录>/ue-editor` 链接到本仓库 `skills/ue-editor`。
- UE 工程：在 `<工程>/Plugins/AgentTools/` 下链接 `Source` 与 `AgentTools.uplugin`；`Binaries`、`Intermediate` 留在各工程本地，互不干扰。
- Windows 使用目录联接（junction），无需管理员权限；`.uplugin` 优先符号链接，无权限时退化为硬链接或复制。

## 更新

```bash
git pull
```

所有已安装的 Skill 目录和工程立即使用新版本；插件源码有改动时重新编译工程编辑器目标。安装时若 `.uplugin` 退化为复制，增减插件模块后重跑一次 `install.py`。

## 卸载

先关闭使用该工程的 UE 编辑器（编辑器运行时插件 DLL 被占用，删不掉编译产物），然后执行：

```bash
python install.py --uninstall --skills ~/.codebuddy/skills --project D:/Work/MyGame
```

- 与安装一样，`--skills`、`--project` 可重复指定，也可只给其中一类；不带路径参数时交互输入。
- Skill 目录：仅当 `<Skill目录>/ue-editor` 是指向本仓库的链接时才删除，同名的其它 Skill 会跳过（`[skip]`）。
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

2. 编译插件：打开 `.uproject` 时按提示重建，或执行
   `Engine/Build/BatchFiles/Build.bat <工程名>Editor Win64 Development -Project="<.uproject 路径>" -WaitMutex`。
3. 截图功能依赖 `pip install pywin32 pillow`（仅 Windows）。

插件仅编辑器使用（`Type: Editor`），不进入打包产物；工程用版本控制时，可把 `Plugins/AgentTools/` 加入忽略列表。

## 项目知识

Skill 只包含通用能力。项目专属的流程脚本与参考资料（登录、进入常用界面、业务验证路径等）放在各工程 `.codebuddy/ue-editor/lib/` 与 `.codebuddy/ue-editor/references/`，见 `skills/ue-editor/SKILL.md`。
