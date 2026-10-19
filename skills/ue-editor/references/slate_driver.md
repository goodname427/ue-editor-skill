# Slate 操控 API 参考

> 本文档收录 `UAgentSlateDriverFunctionLib` 提供的 Slate 层操控接口：读取控件树、查找控件、设置焦点、合成鼠标/键盘输入。
> 编辑器面板、资产编辑器、弹窗菜单、PIE 视口内的 UMG 使用同一套接口；后台输入边界见 [ui_verify.md](ui_verify.md#pie-游戏界面)。所有函数返回 JSON 字符串。
> 日常查看与操作优先用 `exec --lib ui ...`（输出精简文本，见 `scripts/lib/ui.py` docstring）；需要程序化处理结果时再直接调本库。

## AgentSlateDriverFunctionLib

> 位于工程插件 `Plugins/AgentTools`（`AgentSlateDriver` 模块，仅编辑器），编译后需重启编辑器。
> 找不到 `unreal.AgentSlateDriverFunctionLib` 时，说明插件未编译或未启用。

### 约定

- **坐标**：所有 `rect` / `pos` 均为桌面绝对像素 `[x, y, w, h]`，可直接传给 `ue_cli.py screenshot --rect=x,y,w,h` 截取该区域（副屏坐标可能为负，须用 `=` 形式）。
- **Locator**（定位控件）：
  - 纯字符串：按 UMG 控件名、Slate Tag、文本、输入框提示文字、按钮名称精确匹配。例如 `Btn_Confirm`、`保存`、`Search Assets`、`Save Current Level`
  - `key=value`：精确匹配（不区分大小写）；`key~=value`：包含匹配。key 取 `name` / `tag` / `text` / `hint` / `label` / `type` / `class`
  - `label`：无文字的按钮类控件（含已禁用的）的名称，取自折叠隐藏的文字子节点，没有则取 tooltip 第一行；纯图标工具栏按钮靠它识别
  - 多个条件用 `;` 连接，需同时满足。例如 `type=SButton;text~=Compile`
  - `type=` 也匹配模板包装内的类型名：`type=SDesignerView` 能命中 `TToolCompatibleMixin<SDesignerView>`
  - `type` 是 Slate 类（`SButton`、`SObjectWidget`），`class` 是 UMG 类（`Button`、蓝图类 `WBP_Foo_C`）；树里每行写作 `名称<type:class>`。找 UserWidget 用 `class=BP_Xxx_C`，`type` 一律是 `SObjectWidget`
  - `name` / `class` 只有 UMG 控件才有（取蓝图里的控件名与 UWidget 类名，PIE 界面、WBP 设计器预览都适用）；编辑器原生面板一般靠 `text` / `hint` / `tag` / `type` 定位
- **window_filter**：只匹配**独立窗口**的标题（主窗口、浮动窗口）。停靠的面板（内容浏览器、细节面板等）都在主窗口里，要用根 Locator 定位，如 `type=SContentBrowser`；同类面板开了多个时用 match index 区分。下拉菜单等弹出层是无标题的独立窗口。
- **匹配下标**：`match_index` / `--index` 仅对应当次匹配集合，不是控件稳定 ID；页面、导航或列表变化后必须重新查找，不能复用旧下标。
- **节点字段**：`type`（Slate 类型）、`name`、`class`、`tag`、`text`、`hint`（输入框提示文字）、`rect`；状态字段只在非默认时出现：`vis`（非 Visible）、`enabled: false`、`interactable`、`focus`、`hover`
- **输入延迟一帧**：输入类接口（含 `focus_widget`）在下一帧按调用顺序执行，返回时尚未生效；点击可能弹出模态对话框，延后执行可避免阻塞本次调用。确认结果要在下一次调用里看（约 0.5 秒后）。
- 驱动不主动定位系统光标，但事件回包可能请求移动、捕获或锁定光标，不能保证不影响用户鼠标。
- **焦点**：编辑器窗口不在前台时，点击可能拿不到键盘焦点（实测出现过：点击返回成功，文字却打进了关卡视口）。输入文本或按键前，用 `focus_widget` 直接把焦点设到目标上，不要依赖点击。

### ListWindows

列出所有可见窗口（从后往前）。

```python
print(unreal.AgentSlateDriverFunctionLib.list_windows())
```

- **返回**: `str` — JSON 数组，每个元素包含 `title`, `rect`, `active`

### ListPIEViewports

`lib.list_pie_viewports()` 返回本进程已排布的 PIE 游戏视口 JSON 数组，每项为 `world`、`instance`、`window`、`rect`。按 WorldContext.GameViewport 关联控件并从窗口根计算几何，不使用第一个 SViewport 猜客户端。空数组可能是尚未就绪/窗口隐藏，不等于 PIE 未运行；多项需明确实例选择。截图入口为 `screenshot --pie [--instance=N]`。

### DumpSlateTree

导出可见窗口的 Slate 控件树。几何由窗口几何逐层 `ArrangeChildren` 实时计算，不依赖控件缓存。

```python
lib = unreal.AgentSlateDriverFunctionLib
print(lib.dump_slate_tree('', 'type=SContentBrowser', 6, False, True, 3000, 0))
```

- **参数**:
  - `window_filter` (`str`) — 窗口标题子串，空为所有可见窗口
  - `root_locator` (`str`) — 只导出命中的子树（命中节点深度记为 0），空为整棵树
  - `max_depth` (`int`) — 最大输出深度，0 为不限
  - `include_hidden` (`bool`) — 是否包含 Collapsed/Hidden 控件
  - `compact` (`bool`) — 精简模式：只输出有名称/Tag/文本或可交互/可聚焦的控件，深度按已输出祖先计算
  - `max_nodes` (`int`) — 最多输出节点数，超出截断
  - `root_match_index` (`int`) — 根 Locator 命中多个时只导出第几个（按遍历顺序，从 0 开始），-1 为全部
- **返回**: `str` — JSON 对象，包含 `windows`（每个含 `title`, `rect`, `nodes`，节点带深度 `d`）, `node_count`, `truncated`；指定根时另含 `root_match_count`
- **提示**: 编辑器整窗节点很多，优先用 `root_locator` / `root_match_index` / `max_depth` 缩小范围；`truncated: true` 时继续缩小。

### FindWidgets

查找当前可见分支中命中 Locator 的控件（尺寸为 0 的不算）；父级 Hidden/Collapsed 的子控件也不会命中。空数组不证明蓝图没有该控件，诊断隐藏原因用 `dump_slate_tree` 的 `include_hidden=True`、`compact=False` 查看已有层级与父级可见性，必要时再查蓝图静态结构。

```python
print(lib.find_widgets('hint~=Search', ''))
```

- **参数**: `locator` (`str`), `window_filter` (`str`), `include_hidden` (`bool`，默认 false)
- **返回**: `str` — JSON 数组，每项附 `window`；默认可见查询下标可给其它输入接口。
- **隐藏诊断**：`lib.find_widgets('name=Btn_Apply', '', True)` 另查已创建隐藏或未参与布局的结构子节点，返回 `query_only=true`、`geometry_valid`、`visible_path` 和可用的 `hidden_by`。隐藏模式下标/几何不可直接用于点击/截图，须重查可见目标；不保证容器未公开或未创建的节点。

### GetKeyboardFocus

```python
print(lib.get_keyboard_focus())
```

- **返回**: `str` — 当前键盘焦点控件的节点信息（含 `owner`：最近的 UMG 祖先名），无焦点时为 `null`

### FocusWidget

把键盘焦点直接设到命中的控件（下一帧执行，与后续输入按顺序排队）。

```python
print(lib.focus_widget('hint~=Search', '', 0))
```

- **参数**: `locator` (`str`), `window_filter` (`str`), `match_index` (`int`)
- **返回**: `str` — JSON 对象，包含 `success`, `match_count`, `target`
- **注意**: 目标须支持键盘焦点。搜索框之类的复合控件要指向内部可编辑控件（`SEditableText`，带 `hint`），指向外层容器会返回失败。

### ClickWidget

点击命中控件的中心。

```python
print(lib.click_widget('Btn_Confirm', '', 0, 'Left', False))
```

- **参数**:
  - `locator` (`str`), `window_filter` (`str`)
  - `match_index` (`int`) — 多个命中时取第几个
  - `button` (`str`) — `Left` / `Right` / `Middle`
  - `double_click` (`bool`)
  - `expect_hit` (`str`，默认空) — 唯一可见预期控件的 Locator
- **返回**: `str` — JSON 对象，包含 `success`, `match_count`, `target`, `pos`, `hit`；断言模式另含 `request_id`。
- **注意**: 此处 `hit` 是排队前快照，可能是目标合法子节点，不一致不直接证明遮挡；实际路由还可能受捕获/预处理器影响。非空 `expect_hit` 在下一帧发送前与悬停更新后校验实际路径包含已解析的控件身份，失败不再发按下。业务效果仍需状态/日志确认。

### ClickAt

在桌面坐标处点击。

```python
print(lib.click_at(1520.0, 640.0, 'Right', False))
```

- **参数**: `x` (`float`), `y` (`float`), `button` (`str`), `double_click` (`bool`), `expect_hit` (`str`，默认空)
- **返回**: `str` — JSON 对象，包含 `success`, `pos`, `hit`；断言模式另含 `request_id`

### GetInputResult

`lib.get_input_result(request_id)` 回读最近 64 次断言点击的结果。`pending=true` 为未完成，完成包含 `success`、`clicks_sent` 与实际 `hit`；首次失败可为 0 次，双击第二次失败可为 1 次。调用方不得因失败自动重放；模态回调可能使结果长时间 pending。

`ui click --expect-hit=<Locator>` 会输出 `[input-request]`，CLI 的 exec/sequence 自动跨帧回读并在失败时返回 `InputAssertionFailed` / `InputWaitTimeout`。项目直接调 API 时须自行用只读等待与 `GetInputResult` 确认，或使用 ui Lib；不能把排队成功视作断言完成。

### ScrollAt

在桌面坐标处滚动滚轮（作用于该位置下的控件，如列表、细节面板）。

```python
print(lib.scroll_at(1520.0, 640.0, -3.0))
```

- **参数**: `x` (`float`), `y` (`float`), `delta` (`float`) — 正数向上
- **返回**: `str` — JSON 对象，包含 `success`, `pos`, `hit`

### PressKey

向当前键盘焦点发送一次按键：下一帧按下，按引擎帧号至少两帧后抬起。抬起时使用届时的焦点，后台世界是否处理输入仍需验证。

```python
print(lib.press_key('S', True, False, False))   # Ctrl+S
```

- **参数**: `key_name` (`str`) — FKey 名称，如 `Enter` / `Escape` / `Tab` / `Delete` / `F5` / `A` / `Up`；`ctrl`, `shift`, `alt` (`bool`)
- **返回**: `str` — JSON 对象，包含 `success`, `focus`（排队时的焦点，不是按键执行时的）
- **修饰键**：`ctrl` / `shift` / `alt` 只写入本次按键事件，不更新系统修饰键状态；依赖全局键状态的处理器未必响应。
- **退格**：普通 `BackSpace` 额外发送字符码 8，编辑框靠字符事件删除文字；Ctrl/Alt 组合不补字符，避免重复删除或影响撤销。

### TypeText

向当前键盘焦点逐字输入文本（字符事件，可含中文）。

```python
print(lib.type_text('MainMenu'))
```

- **参数**: `text` (`str`)
- **返回**: `str` — JSON 对象，包含 `success`, `focus`（排队时的焦点）

## 典型流程

同一次调用中排队的输入在下一帧按顺序执行，可以写在一起：

```python
lib.focus_widget('hint~=Search', '', 0)
lib.press_key('A', True, False, False)      # Ctrl+A 全选旧内容
lib.type_text('WBP_Foo')
lib.press_key('Enter', False, False, False)
```

输入与提交可用：`exec --lib ui type WBP_Foo --focus="hint~=Search" --enter`（不自动全选旧文字）。排队顺序只保证按下/字符的顺序，按键抬起独立延迟；依赖前一步抬起或业务完成的操作拆成多次调用，用 `--wait-until` 确认。执行后用 `ui focus` / `ui tree` 或截图确认结果。
