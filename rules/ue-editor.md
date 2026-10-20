---
description: 使用 ue-editor Skill 操作 UE 编辑器时，把已验证的项目流程与知识沉淀到工程 .codebuddy/ue-editor 的 lib/actions/references
alwaysApply: true
enabled: true
updatedAt: 2026-10-20T00:00:00.000Z
provider:
---

# ue-editor：项目 lib / actions / references 沉淀

适用于任何使用 `ue-editor` Skill 操作 UE 编辑器的任务；纯读工程代码、不连编辑器的任务不适用。

1. **第一次用 ue-editor 操作编辑器时（进 PIE、操作界面、改蓝图/资产、跑脚本等），立即在 todo 里加一项**「收尾：更新项目 ue-editor lib/actions/references」。长任务的收尾要求容易被遗忘，清单项能留到结束。
2. 工程 `.codebuddy/ue-editor/` 下 `lib/`、`actions/`、`references/` 的更新属于本任务已授权的交付物，不受"未经要求不主动创建文档"和"只做要求的事"的限制。
3. 收录判据，三类各放各的：
   - **actions**（`.py` 入口、`.sequence.json` 步骤清单）：跑通过一次、下次同类任务还会走的流程（导航、取数、改资产/蓝图、批量操作等）。入口只读 `ARGS` / `OPTS`、做事、打印；清单参数写成 `"{名字}"` 显式交给各步。
   - **lib**（可 `import` 的 `.py` 模块）：被两个以上入口用到的项目函数（如页签、弹窗、状态判据）。只定义函数，导入无副作用、不存跨调用状态；模块名不用 `ue_` 前缀（留给 Skill）。通用的查找、点击、输入、WBP 读写用 Skill 的 `ue_input` / `ue_wbp`，不在项目里再写一份。
   - **references**（`.md`）：项目入口、前置条件、控件、坑与已证实限制。独立于脚本，脚本没跑通也收录已核实知识。
   只有回答单个问题的只读诊断代码算一次性探针，按坐标摸索出的导航流程不算。
4. 开始前先读项目已有 lib/actions/references 并复用；更新同主题文件，不新建平行文档，不复制通用 Skill 内容，不收录未经核实的结论，不以写入记忆代替项目资料。
5. 收尾回复必须按 lib / actions / references 列出新增/更新的文件；没有值得收录的内容时写明原因，不造文件。
