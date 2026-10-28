# Slate 操控 API 参考

> 本文档收录 `UAgentSlateDriverFunctionLib` 提供的 Slate 层操控接口：读取控件树、查找控件、设置焦点、合成键鼠/手柄输入。
> 编辑器面板、资产编辑器、弹窗菜单、PIE 视口内的 UMG 使用同一套接口；后台输入边界见 [ui_verify.md](ui_verify.md#pie-游戏界面)。所有函数返回 JSON 字符串。
> 日常查看与操作优先用 `exec --action ui ...`（输出精简文本，见 `scripts/actions/ui.py` docstring）；脚本里做界面输入用 `import ue_input`，查询可以直接调用本库。

## AgentSlateDriverFunctionLib

> 位于工程插件 `Plugins/AgentTools`（`AgentSlateDriver` 模块，仅编辑器），编译后需重启编辑器。
> 找不到 `unreal.AgentSlateDriverFunctionLib` 时，说明插件未编译或未启用。

### 约定

- **坐标**：所有 `rect` / `pos` 均为桌面绝对像素 `[x, y, w, h]`，可直接传给 `ue_cli.py screenshot --rect=x,y,w,h` 截取该区域（副屏坐标可能为负，须用 `=` 形式）。
- **Locator**（定位控件）：
  - 纯字符串：按 UMG 控件名、Slate Tag、文本、输入框提示文字、按钮名称精确匹配。例如 `Btn_Confirm`、`保存`、`Search Assets`、`Save Current Level`
  - `key=value`：精确匹配（不区分大小写）；`key~=value`：字面包含匹配，不是正则。全字符串匹配用 `text=确认`，不要用 `text~=^确认$`。key 取 `name` / `tag` / `text` / `hint` / `label` / `type` / `class`
  - `label`：无文字的按钮类控件（含已禁用的）的名称，取自折叠隐藏的文字子节点，没有则取 tooltip 第一行；纯图标工具栏按钮靠它识别
  - 多个条件用 `;` 连接，需同时满足。例如 `type=SButton;text~=Compile`
  - `type=` 也匹配模板包装内的类型名：`type=SDesignerView` 能命中 `TToolCompatibleMixin<SDesignerView>`
  - `type` 是 Slate 类（`SButton`、`SObjectWidget`），`class` 是 UMG 类（`Button`、蓝图类 `WBP_Foo_C`）；树里每行写作 `名称<type:class>`。找 UserWidget 用 `class=BP_Xxx_C`，`type` 一律是 `SObjectWidget`
  - `name` / `class` 只有 UMG 控件才有（取蓝图里的控件名与 UWidget 类名，PIE 界面、WBP 设计器预览都适用）；编辑器原生面板一般靠 `text` / `hint` / `tag` / `type` 定位
- **window_filter**：只匹配**独立窗口**的标题（主窗口、浮动窗口）。停靠的面板（内容浏览器、细节面板等）都在主窗口里，要用根 Locator 定位，如 `type=SContentBrowser`；同类面板开了多个时用 match index 区分。下拉菜单等弹出层是无标题的独立窗口。
- **匹配下标**：`match_index` / `--index` 仅对应当次匹配集合，不是控件稳定 ID；页面、导航或列表变化后必须重新查找，不能复用旧下标。`DumpSlateTree`的根下标与同参数`FindWidgets`共用匹配序列，完全裁剪/零尺寸根不会挤占普通可见下标；`root_match_count`是匹配总数，不受子树输出截断影响。
- **节点字段**：`type`（Slate 类型）、`name`、`class`、`tag`、`text`、`hint`（输入框提示文字）、`rect`；文本超过摘要长度时另带 `text_full`，`read_text` 优先读完整值。标准富文本的 text 是源字符串（含标签），精确匹配源文或用字面包含；图片、自绘文字或装饰器最终显示文案不自动转换为文本。已知独立多行编辑控件的 text/hint 可读取。状态字段只在非默认时出现：`vis`、`enabled: false`、`interactable`、`focus`、`hover`
- **窗口/PIE归属**：`find_widgets`返回`window_rect`（实际所属SWindow矩形），PIE视口后代额外带`pie_instance`（真实GameViewport祖先），不用同标题或矩形重叠猜归属。新增字段不改UFUNCTION签名，须编译后回读确认。`ue_input.observe_ui(root='', instance=None, window='', depth=6, limit=80, scope='window')`默认通用窗口，`scope='pie'`才按实例筛选，instance仅用于pie；返回可交互Locator及窗口匹配数，不是稳定ref、不保证无遮挡。`ue_input.readiness(locator, window='', index=None, previous=None)`共用只读可见/启用/采样门禁，previous由调用方持有，本lib无跨调用状态；CLI的--ready-timeout负责跨帧等待。
- **输入执行时机**：键鼠/聚焦步骤排到下一帧，CLI 会回读执行结果，目标响应再用 `--wait-until` 确认。`analog_input` 是同步单事件，不排时间线；配对与持续采样由 `ue_input` 在 Python Slate 回调里组合。
- 驱动不主动定位系统光标，但事件回包可能请求移动、捕获或锁定光标，不能保证不影响用户鼠标。
- **焦点**：输入文本或按键前，用 `focus_widget` 直接把焦点设到目标上，不要依赖点击（后台时点击不保证把焦点交给输入框）。后台可以聚焦和输入；聚焦后焦点被业务逻辑改走时，focus / 全选步骤会失败并带当前焦点。

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

查找当前可见分支中命中 Locator 的控件（尺寸为 0 的不算）；父级 Hidden/Collapsed 或真实裁剪交集为空的子控件不会命中。`rect` 为渲染包围盒；部分裁剪另带 `clipped=true` / `visible_rect`。旋转/Stencil 按凸多边形计算真实交集，`visible_rect` 只用于包围盒展示，`visible_point` 为交集内部落点；`ue_input.center` 优先使用它，避免包围盒中心落在裁剪外。裁剪沿引擎栈规则计算，保留 `WithoutIntersecting` / `AlwaysClip`；可见仍不保证未被其他窗口或兄弟控件遮挡，输入校验保留。空数组不证明蓝图没有该控件，诊断用 `find_widgets(..., include_hidden=True)` 或隐藏控件树，必要时再查蓝图静态结构。

```python
print(lib.find_widgets('hint~=Search', ''))
```

- **参数**: `locator` (`str`), `window_filter` (`str`), `include_hidden` (`bool`，默认 false)
- **返回**: `str` — JSON 数组，每项附 `window`；默认可见查询下标可给其它输入接口。
- **未命中诊断**：`ui find` 先查隐藏/裁剪精确目标，再从有界可见树中给最多五个近似候选；可用 `--root=<Locator>` / `--window` 缩小候选扫描，`--no-suggest` 关闭。候选不是命中，顺序不是匹配下标，不会自动点击。脚本复用 `ue_input.suggest(locator, window='', root='', limit=5)`。
- **隐藏/裁剪诊断**：`lib.find_widgets('name=Btn_Apply', '', True)` 另查已创建隐藏、未参与布局或完全被裁剪的节点，返回 `query_only=true`、`geometry_valid`、`visible_path` 和可用的 `hidden_by`、`clipped` / `visible_rect`。`visible_path=true` 只表示祖先未 Hidden/Collapsed，不表示未裁剪。诊断模式下标/几何不可直接用于点击/截图，须重查可见目标；不保证容器未公开或未创建的节点。滚到可见位置仍须跨帧执行滚动再重新定位，不会由查询或聚焦自动完成。

### GetKeyboardFocus

```python
print(lib.get_keyboard_focus())
```

- **返回**: `str` — 当前键盘焦点控件的节点信息（含 `owner`：最近的 UMG 祖先名），无焦点时为 `null`

### WidgetAt

`lib.widget_at(x, y)` 返回坐标处最上层控件（JSON 节点），没有窗口时为 `null`。`ui at x,y` 是同一个查询。

### GetInputResult

`lib.get_input_result(request_id)` 回读最近 64 个输入步骤的结果。`pending=true` 表示还没执行完；完成后含 `success` 以及该步骤自己的字段（见下表）。调用方不得因失败自动重放；模态回调可能使结果长时间 pending。

## 输入：C++ 只给原子步骤，组合在 `ue_input`

C++ 只提供下表这些原子步骤，**点击、长按、按键、拖动、滚动回读、文本输入回读都在 Skill lib 的 `scripts/lib/ue_input.py` 里拼装**。`ui` 入口和项目脚本都 `import ue_input`，不要在别处再拼一遍，也不要直接调用下表的接口去重复实现这些组合。CLI 每次执行前都会把 `scripts/lib` 加进 `sys.path` 并清掉其中模块的缓存，所以 `git pull` 后不用重启编辑器。

| 原子步骤 | 作用 | 结果字段 |
|---|---|---|
| `focus_widget(locator, window, index)` | 把键盘焦点设到命中的控件；它本身不接受焦点时，取其中第一个可编辑控件。不经过点击路由；执行后焦点不是目标（目标已隐藏、被模态窗拦截等）时失败 | 失败时 `focus`, `app_active` |
| `select_all_text()` | 全选当前焦点所在输入框的文字；焦点不是输入框时失败 | 失败时 `focus`, `app_active` |
| `type_text(text)` | 向当前焦点逐字发送字符事件（可含中文）；只追加，不清空。本身不判失败，落地由调用方按回包判断 | `focus`, `handled`（被处理的字符数）, `chars`, `app_active` |
| `key_down(key, ctrl, shift, alt, max_hold=30)` | 数字键按下并保持；普通退格额外发字符码 8；模拟轴不可用此接口 | `handled`, `device_id`, `platform_user`, `slate_user` |
| `analog_input(key, value, device_id=-1)` | **同步单事件**，调用 `OnControllerAnalog`；只接 gamepad Axis1D，-1 取默认映射；不配对、不保持、不自动归零 | `handled`, `device_id`, `platform_user`, `slate_user` |
| `key_up(key)` | 抬起 `key_down` 按住的键；没按住时失败 | — |
| `use_platform_cursor_for_cursor_user(use_platform)` | 对标引擎平台/虚拟光标选择；同步操作，不自行定时恢复 | 切换前 `pos`, 平台 `visible` |
| `set_cursor_position(x, y)` | 对标 Slate 光标位置；使用虚拟光标时不移动 OS 光标 | — |
| `set_cursor_visibility(visible)` | 对标 SlateUser 显隐；作用于当前绑定光标 | — |
| `mouse_down(x, y, button, double, check_locator, window, index, max_hold=30)` | 先把指针移到落点再按下；`double=True` 时发双击事件。校验目标/子节点；透明目标也可命中实际祖先，但目标几何须包含落点、落点须在有效裁剪区内，路径可见且可用。相邻/遮挡/禁用/裁剪外仍失败、不发按下 | `hit`, `hit_via`（仅祖先路由） |
| `mouse_up(button, check_locator='', window='', index=0, reject_viewport=False)` | 在当前指针位置抬起；可选释放前目标校验使用指针下的真实路径、不使用捕获者路径。失败取消当前拖放并立即释放本库按钮 | `pos`, `hit_before`, `hit`, `released`（失败清理时） |
| `mouse_move(x, y, frames=1)` | 分 `frames` 帧线性移过去；有键按住时就是拖动。最后一步后保持悬停 10 秒，后续 move 续期；不会移动系统光标 | `pos`, `hit`, `dragging`, `hover_seconds` |
| `mouse_wheel(x, y, delta)` | 滚一次滚轮（正数向上） | `handled` |
| `scroll_descendant_into_view(locator, window, index=0, ancestor=0, animate=False, destination=0)` | 对标原生 ScrollBox 滚入已有后代；index 来自诊断集合，ancestor=0 是最近 ScrollBox，destination=0/1/2/3 为 IntoView/TopOrLeft/Center/BottomOrRight | `target`（排队快照） |
| `wait_input(seconds, frames)` | 时间线上等待，秒数和帧数都满足才算完成 | — |
| `release_all_input()` | **不排队**，下一帧就取消所有未完成的步骤，并抬起本库按住的全部键 | `released` |

- **一条时间线**：键鼠步骤（除 `release_all_input`）前一步完成才执行下一步，相邻两步至少隔一帧，失败取消后续。`analog_input` 是同步单事件，不排队，所以 lib 能在同次 Slate 回调发送 X/Y；持续输入由 lib 的 `analog` 完成，不在 C++ 实现组合策略。
- **排队返回**：`success` 只表示已经排进队列，另含 `request_id`。`mouse_down` 排队时还会返回 `pos`、`hit`（排队那一刻的快照）；带校验时另含 `match_count`、`target`。
- **防止一直按着**：按住的键记在本库内，到 `max_hold` 秒自动抬起（0 为不限，不建议）。
- **按住与悬停共用抑制状态**：Slate 会按真实光标位置自动补发移动（`Slate.EnableSyntheticCursorMoves`），取消注入的按下/悬停。本库按住鼠标或最后一次 move 后 10 秒内暂时置 0，续期看最新截止点；悬停到期但还有按键时不恢复，全部抬起、`release_all_input` 或排队输入失败会清除悬停保持。按键与悬停共用一次原值保存，最后一个所有者退出才恢复，原值为 0 也不强制改成 1；写入沿用当前 CVar 优先级，避免手动控制台设置后被拒绝。真实鼠标仍可改变命中，`hit.hover` 不证明业务浮窗显示，见 [ui_verify.md](ui_verify.md#要点)。
- **合成事件只走 Slate**：不移动系统光标。游戏侧 `PlayerController.is_input_key_down` / `get_input_key_time_down` 能读到按住状态（PIE 实测）。不会产生系统级按键重复，按住字母键不会在输入框里连续出字。修饰键只写入本次事件，不更新系统修饰键状态。事件回包仍可能请求捕获或锁定光标。

### ue_input 组合

| 组合 | 拼法 |
|---|---|
| `click(locator=None, at=None, window, index, button, double, hold, check=True, expect_hit=None)` | `mouse_down` →（`hold>0` 时）`wait_input(hold)` → `mouse_up`；`double` 时再加一组 `mouse_down(double=True)` → `mouse_up`。给 `locator` 时落点取控件中心，默认校验该控件；`check=False` 不校验；`expect_hit` 换一个控件做校验；给 `at=(x, y)` 时只有 `expect_hit` 会触发校验 |
| `key(name, ctrl, shift, alt, hold=0)` | `key_down` → `wait_input(hold, 1)` → `key_up`，抬起至少比按下晚两帧 |
| `analog_set(values, device_id=-1)` | 先校验整批六类轴键/值；摇杆补齐另一轴，同次调用同步发事件；**不保持、不自动归零** |
| `analog(values, hold=0, device_id=-1)` | 等待既有时间线 gate → Python Slate 回调逐帧发配对轴 → hold 到期归零并注销；hold 在 0~30 秒，0 为一次脉冲；用 `check_analog(job)` 回读 |
| `drag(start, end, frames=20, button, check_locator, window, index, drop_target='', drop_index=0, check_drop=True)` | `mouse_down` → `mouse_move(frames)` → 受校验 `mouse_up`；显式 drop_target 核实终点/子节点或有效透明祖先，否则默认拒绝空路径和 SViewport；返回 release_request_id。不证明业务接受了 Drop |
| `scroll_into_view(locator, window='', index=0, ancestor=0)` | 诊断下标定位已有后代 → 原生无动画居中请求 → 等三帧 → check_visible；一次只滚一个 ScrollBox，嵌套滚动由 sequence 分步选择 ancestor。不创建虚拟化条目、不修复 Hidden/Collapsed；确认后重新定位再点击 |
| `scroll(x, y, delta, frames=8)` | 排队前先用 `widget_at` 记下落点控件 → `mouse_wheel` → `wait_input(0, frames)` → 回读：落点控件的 `type` / `name` / `rect` 变了才算 `moved` |
| `input_text(locator, text, window, index, replace=True, commit=False)` | `focus_widget` → `select_all_text`（replace 时）→ `type_text` →（commit 时）`key('Enter')` → `wait_input(0, 2)` → 回读文字，不等于预期就失败。追加模式的预期值是旧值加新文字。控件已消失时记为 `(target destroyed)`，视为通过 |

模块还提供查询辅助：`find`、`find_one`、`match`、`center`、`widget_at`、`read_text`、`describe`（控件节点摘要，`ui` 的输出就用它），以及 `parse`（解析 JSON，`success=false` 时抛异常）。`describe` 已转义 CR/LF、文本引号、反斜杠与 U+0085 / U+2028 / U+2029 行分隔符。诊断查询用 `find(locator, window='', include_hidden=True)`；结果只用于诊断或滚入准备，点击前须重查默认可见集合。`match` 越界时错误里列出该 Locator 的前 5 个命中。同一行定位：`in_row(nodes, anchor_locator)` 返回垂直中心落在唯一锚点纵向范围内的 `(全集下标, 节点)`；`row_index(locator, anchor_locator, window, index)` 把行内序号换成全集下标，可直接交给各原子接口的 `index`。直接用 `type_chars` 时，用 `check('__import__("ue_input").check_typed(<request_id>)')` 确认字符进了输入框。

**与 CLI 的约定**：每个原子步骤打印一行 `[input-request] <id> [秒]`；需要回读的组合再打印一行 `[input-check] <表达式>`，这个表达式必须返回含 `ok` 字段的 JSON 字符串。`exec` / `sequence` 执行完脚本后，按输出顺序等每个请求完成；某个检查表达式会在它之前的请求都完成后才求值。任一步失败时报 `InputAssertionFailed`，等待超时报 `InputWaitTimeout`。所以调用方不要自己 sleep 或轮询。在 CLI 之外直接调用 C++ 时，要自己用 `get_input_result` 确认结果，不能把排队成功当作已经生效。

```python
import ue_input
ue_input.click('name=Btn_Confirm')                         # 校验落点没被遮挡
ue_input.click(at=(1520, 640), button='Right')
ue_input.key('S', ctrl=True)                               # Ctrl+S
ue_input.input_text('name=EditableTextBox_Num', '5', commit=True)
ue_input.drag((-2264, 800), (-2264, 500), frames=20)
ue_input.key_down('W'); ue_input.wait(1.5); ue_input.key_up('W')   # 等价于 key('W', hold=1.5)
```

- **数字框**：只在提交时同步业务值的输入框（`OnTextCommitted`）必须 `commit=True`，否则框里显示新值、业务还是旧值。超出业务上下限会被截断，回读失败时 `actual` 就是截断后的值。
- **滚动判读**：`handled` 只说明事件路径上有控件处理了滚轮，不代表内容动了。容器 `ConsumeMouseWheel=Never` 时会出现 `handled=true, moved=false`，这时改用 `drag` 拖动内容。
- **键盘焦点**：后台文字输入前明确聚焦输入框；手柄导航沿用当前 UI 路由，不强行聚焦业务按钮。`ui focus` 只读 Slate 键盘焦点，不保证等价于项目导航焦点。

### 手柄输入与清理

- C++ `analog_input` 对标引擎单事件接口；`ui analog Axis=value --hold=0.5` 调 lib 做配对、逐帧采样和归零。`ui analogset Axis=value` 只发一次，调用方必须显式送 0；`release_all_input` 不跟踪同步轴事件。
- `job = ue_input.analog(values, hold)` 的状态只在本次闭包持有，不存 lib 全局跨调用状态；`check_analog(job)` 返回 pending/ok/samples/设备身份。用 `ue_input.check` 等终态；检查只读取状态，不发事件。
- 正常到期、显式 `job['cancel']()`、本次等待被队列取消、PIE 结束都尝试送 0 并注销回调。显式取消在下一次 Slate 回调归零，避免非零与 0 同帧累加；归零失败如实报告。编辑器暂停/远控超时时不重放，线程恢复后清理。
- 连续多个操作用 sequence 分步并等待本次 check 完成；不要并发向同一摇杆启动多个 hold。保持最长 30 秒，不提供默认无限持轴或全局注册管理器。
- 摇杆值为 [-1,1]，扳机为 [0,1]；不接 Axis2D 合成键，不在 Skill 预先翻转 RightY，也不自动把 TriggerAxis 转成数字扳机键。
- `handled`、设备切换、调试日志或键盘焦点单独都不是输入验收终态。导航看项目焦点/选中状态，UI 动作看目标效果，gameplay 读 PlayerInput；默认设备存在不等价于 OS 有物理手柄或型号已识别。

### 临时保护用户系统光标

- `ui key/keydown/analog/analogset` 默认通过 lib 使用引擎虚拟光标，把导航的移动/隐藏写到虚拟光标，不改项目设备类型或导航逻辑。组合结束后至少保留两次 Slate 回调和 0.2 秒尾部窗口，覆盖常见短延迟焦点落地，再恢复平台绑定及进入时的显隐。这是有界操作级规避，不保证任意长的异步页面/导航会话；较长异步操作应把真实就绪状态纳入外围 `done` 判据。
- 不把系统鼠标搬回旧坐标；用户期间移动鼠标时，退出隔离仍使用用户当前真实位置。超时/异常尽力恢复并报告，不永久关闭输入或光标。
- 真正验证光标跟随、显隐或捕获时，加 `--allow-cursor-takeover`；脚本对应 `protect_cursor=False`。原生 C++ `KeyDown/AnalogInput` 和 lib `analog_input` 没有自动保护，保留原子行为。
- lib `preserve_cursor(done, timeout)` 的完成判据必须只读。状态只在本次闭包持有；不嵌套、不并发隔离，也不覆盖外部已启用的虚拟光标。多段操作用 sequence 分步等恢复终态；自定义批量操作只创建一个外围范围，内部调用设 `protect_cursor=False`。
- 保护针对 Slate cursor-user 路径；不拦截任意 OS API、真实物理输入或所有游戏捕获路径。键鼠鼠标点击/拖动的旧行为不变。
