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
- 卸载：`python install.py --uninstall --skills <Skill目录> --project <工程目录>`，只删除本仓库创建的链接和插件目录。

## 更新

```bash
git pull
```

所有已安装的 Skill 目录和工程立即使用新版本；插件源码有改动时重新编译工程编辑器目标。安装时若 `.uplugin` 退化为复制，增减插件模块后重跑一次 `install.py`。

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
