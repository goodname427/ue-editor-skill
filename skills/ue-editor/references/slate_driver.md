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
  - `expect_hit` (`str`，默认空) — 唯一可见预期控件的 Locator，严格断言：实际命中路径须包含它
  - `check_target` (`bool`，默认 false) — 未给 `expect_hit` 时校验"光标下最上层控件是目标本身或其子节点"。目标被抽屉/弹窗盖住、或目标是 HitTestInvisible 的文字（点击会穿透到别处）时判失败，不发送按下
- **返回**: `str` — JSON 对象，包含 `success`, `match_count`, `target`, `pos`, `hit`；校验模式另含 `request_id`。
- **注意**: 此处 `hit` 是排队前快照，可能是目标合法子节点，不一致不直接证明遮挡；实际路由还可能受捕获/预处理器影响。校验在下一帧发送前与悬停更新后按控件身份执行，失败不再发按下；结果用 `GetInputResult` 读回。业务效果仍需状态/日志确认。

### ClickAt

在桌面坐标处点击。

```python
print(lib.click_at(1520.0, 640.0, 'Right', False))
```

- **参数**: `x` (`float`), `y` (`float`), `button` (`str`), `double_click` (`bool`), `expect_hit` (`str`，默认空)
- **返回**: `str` — JSON 对象，包含 `success`, `pos`, `hit`；断言模式另含 `request_id`

### GetInputResult

`lib.get_input_result(request_id)` 回读最近 64 次输入结果（点击校验、滚动回读、文本回读共用）。`pending=true` 为未完成，完成包含 `success`、`clicks_sent` 与实际 `hit`（文本输入为 `expected`/`actual`，滚动为 `handled`/`moved`）；首次失败可为 0 次，双击第二次失败可为 1 次。调用方不得因失败自动重放；模态回调可能使结果长时间 pending。滚动回读要等固定帧数，CLI 的 `--timeout` 要大于该等待。

`ui click --expect-hit=<Locator>` 会输出 `[input-request]`，CLI 的 exec/sequence 自动跨帧回读并在失败时返回 `InputAssertionFailed` / `InputWaitTimeout`。项目直接调 API 时须自行用只读等待与 `GetInputResult` 确认，或使用 ui Lib；不能把排队成功视作断言完成。

### ScrollAt

在桌面坐标处滚动滚轮（作用于该位置下的控件，如列表、细节面板），并在几帧后回读光标下内容是否真的移动。

```python
print(lib.scroll_at(1520.0, 640.0, -3.0))
```

- **参数**: `x` (`float`), `y` (`float`), `delta` (`float`) — 正数向上；`frames` (`int`，默认 8) — 滚动后等几帧再回读，覆盖平滑滚动
- **返回**: `str` — JSON 对象，包含 `success`, `pos`, `hit`（排队前）、`request_id`。结果用 `GetInputResult` 读回，含 `handled`（是否有控件消费滚轮）、`moved`（光标下最上层控件的几何是否变化）、`hit`（回读时）、`message`
- **判读**：`handled=false` 说明该点没有可滚动控件接收滚轮；`handled=true, moved=false` 可能是已到边界，也可能只被外围面板接管。两者都不等于"滚轮没送达"，但都不能当作滚动生效；需要确认位置时读滚动容器自身的偏移或截图

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
- **返回**: `str` — JSON 对象，包含 `success`, `focus`（排队时的焦点，不是输入完成后的）
- **注意**: 只追加，不清空旧内容。数字/搜索框把新值接在旧值后面（`1` + `100000` → `1100000`）是常见坑；要写入确定的值用 `InputText`

### InputText

原子文本输入：聚焦 → 全选 → 输入 → 可选提交 → 等两帧回读。

```python
print(lib.input_text('name=EditableTextBox_Num', '', 0, '5', True, True))
```

- **参数**: `locator` (`str`), `window_filter` (`str`), `match_index` (`int`), `text` (`str`), `replace` (`bool`，默认 true，先全选替换旧内容), `commit` (`bool`，默认 true，按 Enter 触发 OnTextCommitted)
- **返回**: `str` — JSON 对象，包含 `success`, `match_count`, `target`, `editable`（实际写入的输入框）, `request_id`
- **回读**: 用 `GetInputResult` 读结果，含 `expected` / `actual`。实际值不等于请求值即失败 —— 业务侧改值、被上限截断、格式化成 `1,000` 都会显形；提交后控件消失时 `actual = (target destroyed)` 视为通过
- **注意**: 命中容器（如 UMG 的 `EditableTextBox` 外层）时会自动取其中第一个可编辑控件。不用 `SetText` 写值：那样不触发 OnTextChanged，业务侧收不到修改

### 按住 / 抬起 / 移动

`PressKey` / `ClickWidget` 是一次性的按下+抬起。长按、按住直到某个条件、拖动用下面这组原语拼装：

| 接口 | 作用 |
|---|---|
| `key_down(key, ctrl, shift, alt, hold_seconds=0, max_hold_seconds=30)` | 按下键盘/手柄键。`hold_seconds>0` 时按住这么久后自动抬起（长按），结果在抬起后完成；为 0 时一直按住 |
| `key_up(key)` | 抬起 `key_down` 按住的键；没按住时判失败 |
| `mouse_down(locator, window, index, x, y, button='Left', hold_seconds=0, max_hold_seconds=30)` | `locator` 非空时按在控件中心，并在执行时校验落点最上层控件是目标或其子节点，被遮挡时判失败、不发按下；`locator` 为空时按在 `(x, y)` |
| `mouse_up(button='Left')` | 在当前指针位置抬起 |
| `mouse_move(x, y, frames=1)` | 指针从当前位置分 `frames` 帧线性移到 `(x, y)`；有键按住时就是拖动，回读里 `dragging=true` |
| `release_all_input()` | 下一帧取消队列里所有未执行的步骤，抬起本库按住的全部键；回读 `released` 是被抬起的键名 |

- **一条时间线**：除 `release_all_input` 外，这些调用排在同一条输入时间线上，前一步完成（包括多帧移动、按住等待）才执行下一步，相邻两步至少隔一帧。所以 `mouse_down → mouse_move → mouse_up` 可以连着调用，不用等。某一步失败时，排在它后面的步骤全部取消，回读消息为 `Cancelled because an earlier queued input failed`。
- **防止一直按着**：按住的键记在本库内，`max_hold_seconds` 到了自动抬起（0 表示不设上限，不建议）。Agent 中途失败时，至多按住到这个上限；也可以随时调 `release_all_input`。
- **回读**：都返回 `request_id`，结果用 `GetInputResult` 读。`key_down` 含 `handled`（是否有控件处理），定时长按含 `held_seconds`，`mouse_down`/`mouse_up`/`mouse_move` 含 `pos` 与 `hit`。
- **合成事件只走 Slate**：游戏侧 `PlayerController.is_input_key_down` / `get_input_key_time_down` 能读到按住状态（PIE 实测）。不会产生系统级按键重复，按住字母键不会在输入框里连续出字。编辑器在后台时，关卡视口不是 realtime，飞行镜头这类依赖逐帧 tick 的效果未必看得到。

```python
lib.mouse_down('', '', 0, -2264, 800, 'Left', 0, 30)   # 按住
lib.mouse_move(-2264, 500, 20)                          # 20 帧拖到目标
lib.mouse_up('Left')                                    # 抬起
lib.key_down('E', False, False, False, 1.5, 31.5)       # 长按 E 1.5 秒
```

## 典型流程

同一次调用中排队的输入在下一帧按顺序执行，可以写在一起：

```python
lib.focus_widget('hint~=Search', '', 0)
lib.press_key('A', True, False, False)      # Ctrl+A 全选旧内容
lib.type_text('WBP_Foo')
lib.press_key('Enter', False, False, False)
```

输入与提交可用：`exec --lib ui type WBP_Foo --focus="hint~=Search" --enter`。带 `--focus` 的 `ui type` 走 `InputText`：先全选替换旧内容、提交、回读，实际值不符即失败；要保留旧内容追加用 `--append`。排队顺序只保证按下/字符的顺序，按键抬起独立延迟；依赖前一步抬起或业务完成的操作拆成多次调用，用 `--wait-until` 确认。执行后用 `ui focus` / `ui tree` 或截图确认结果。
