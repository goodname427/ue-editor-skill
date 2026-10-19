---
description: 使用 ue-editor Skill 做 PIE/界面验证时，把已验证的项目流程与知识沉淀到工程 .codebuddy/ue-editor 的 lib/references
alwaysApply: true
enabled: true
updatedAt: 2026-10-19T00:00:00.000Z
provider:
---

# ue-editor：项目 Lib / Reference 沉淀

适用于使用 `ue-editor` Skill 做 PIE / 界面验证的任务，其余任务忽略本节。

1. **第一次进 PIE 或操作界面时，立即在 todo 里加一项**「收尾：更新项目 ue-editor Lib/Reference」。长任务的收尾要求容易被遗忘，清单项能留到结束。
2. 工程 `.codebuddy/ue-editor/lib/` 与 `.codebuddy/ue-editor/references/` 下的更新属于本任务已授权的交付物，不受"未经要求不主动创建文档"和"只做要求的事"的限制。
3. 收录判据：跑通过一次、下次同类验证还会走的导航/操作流程进 Lib（`.py` 动作与 `.sequence.json` 步骤清单）；项目入口、前置条件、控件、坑与已证实限制进 Reference。Reference 独立于 Lib，脚本没跑通也收录已核实知识。只有回答单个问题的只读诊断代码算一次性探针，按坐标摸索出的导航流程不算。
4. 开始前先读项目已有 lib/references 并复用；更新同主题文件，不新建平行文档，不复制通用 Skill 内容，不收录未经核实的结论，不以写入记忆代替项目资料。
5. 收尾回复必须列出新增/更新的文件；没有值得收录的内容时写明原因，不造文件。
