# 看见与操作编辑器

用于自行确认界面效果、像人一样操作编辑器，不必等用户手动检查。编辑器面板、资产编辑器、弹出菜单与 PIE 界面用同一套接口；PIE 游戏界面的注意点见[下文](#pie-游戏界面)。

| 需求 | 做法 |
|------|------|
| 看结构（控件名、文本、坐标） | `exec --action ui tree` / `ui find` |
| 操作（点击、输入、按键、滚动） | `exec --action ui click` / `type` / `key` / `scroll` |
| 看视觉效果（样式、遮挡、对齐） | `screenshot`，可按控件的 `rect` 截取局部 |

`ui` 的完整用法见 `scripts/actions/ui.py` docstring；底层接口与 Locator 语法见 [slate_driver.md](slate_driver.md)。

结构确认优先控件树（精确、省 token），视觉效果再配合截图。按控件截取优先 `screenshot --widget`；仅当文字直接绘制在视口或控件查不到时才用坐标裁剪，不把缩放后的截图坐标直接当桌面坐标。不要用 Python 侧 UMG 的 `get_cached_geometry` 取坐标：实测 PIE 正常绘制时也全为 0。

## 控制开销

UI 操作每一步都要"操作 → 等一帧 → 观察"，比脚本贵得多。按下面的顺序选：

1. **能用脚本做的不走 UI**：查资产用 AssetRegistry、改蓝图用 WBP 编辑接口、启停 PIE 用 `exec --action pie`。UI 操作只用于确认效果，或没有 API 的操作。
2. **定位用 `find`，不用 `tree`**：`find` 只返回命中的几行；`tree` 用来第一次摸清陌生界面，并且要带根 Locator 和 `--depth`。整窗 `tree` 有数百行，上万 token。
3. **操作和确认放在同一次调用**：给操作加 `--wait-until`，等期望的控件出现或消失，省掉单独的观察调用：

   ```bash
   python scripts/ue_cli.py exec --action ui click "text=Window" --wait-until "unreal.AgentSlateDriverFunctionLib.find_widgets('text=Enable Fullscreen','') != '[]'" --wait 5
   ```

   多个互不依赖结果的步骤（如点击、截图、关闭）可以写在同一条 shell 命令里顺序执行。

   **等待条件必须是"操作前不成立、操作后才成立"**。例如输入搜索词后用 `text~=MainMenu` 等结果，会被搜索框自己的文字满足，等于没等；要加类型限定结果项，如 `type=SInlineEditableTextBlock;text~=MainMenu`。CLI 会在执行前预检一次条件，已经成立时输出 `[warning]`。

   **等待条件里的名称要先用 `ui find` 确认过**，不要按功能猜类名：按"选服弹窗"猜成 `class~=SelectServer`，实际类名不同就会一直超时。超时只说明条件没满足，不等于操作无效；先 `ui find` 看界面实际变成了什么，再查日志。
4. **截图只截需要的区域**：`screenshot --widget=<Locator>` 直接按控件截，`screenshot --popup` 截刚打开的菜单，都不用先查坐标；已有 `rect` 时用 `--rect=`。

## 要点

- **定位停靠面板**：`--window` 只匹配独立窗口标题，内容浏览器、细节面板等都在主窗口里。用根 Locator：`ui tree "type=SContentBrowser" --index=0`；命中多个时输出末尾会提示数量。
- **树参数**：带值选项写 `--max=120` / `--depth=5` / `--index=0`；`--max 120` 会被脚本解析为布尔标记，现已明确报错。根定位器未命中也报错；树截断先核对参数，再判断是否存在子树读取问题。
- **纯图标按钮**：工具栏等图标按钮没有文字，精简树里用 `label="Save Current Level"` 标出名称（取自折叠的文字子节点或 tooltip），可直接 `ui find "label=Save Current Level"` 定位。禁用的按钮也会列出，带 `!disabled`。
- **页面切换后重新定位**：导航、弹窗、列表刷新或返回上层后，重新 `ui find`；`--index` 是当次匹配结果的下标，不是稳定 ID，不能跨页面沿用。优先用稳定名称/Tag 或文字与类型组合；重名时先查看当前页面根子树确认目标。`--window` 不是 UMG 页面作用域，当前不显示的导航先返回对应层级再找。
- **条目内层按钮**：标题或整行不一定可点击。点击返回成功但没有业务效果时，先 `ui tree "name=<条目名>" --depth=5` 找带 `@click` 的内层按钮；核对输出中的 target、match_count 与 topmost hit。命中视口或别的控件时，不算目标按钮已生效，也不能仅靠换下标重试。
- **命中断言**：`ui click "name=Btn_Apply" --expect-hit="name=Btn_Apply"` 预期 locator 须唯一匹配当前可见控件；排队时保留控件身份，实际执行及悬停更新后按命中/捕获路径检查，允许合法子节点。失败不继续发送按下；CLI 自动跨帧读取请求结果并失败退出，支持与 `--wait-until` / `--wait-log` 组合。`clicks_sent=0` 为未发按下，双击可能第二次失败时为 1，不能重放整次动作。断言是发送前几何路径检查，不证明处理器或业务响应成功；预处理器同步改树/捕获仍可能改变最终路由，业务效果仍用日志/状态确认。
- **输入文字**：用 `--focus` 直接设焦点再输入，例如 `ui type WBP_Foo --focus="hint~=Search" --enter`。后台（编辑器不在前台）也能聚焦和输入；聚焦后焦点没落到目标（如业务逻辑在下一帧把焦点改走）时 focus 步骤或全选步骤直接失败，回包带当前 `focus` 与 `app_active`，按现场重查后重试，不要靠先点击再输入绕过。不带 `--focus` 的 `ui type` 在字符没进输入框（焦点不是输入框或字符未被处理）时也判失败。带 `--focus` 的 `ui type` 原子替换（全选 → 输入 → 加 `--enter` 时提交 → 回读），实际值与请求值不符时命令失败；要往已有内容后追加用 `--append`。只在提交时同步业务值的输入框（数量框常见）必须加 `--enter`，否则框里显示新值、业务仍是旧值。提交后业务把值截到上下限时回读也会不符，`actual` 就是截断后的值，不是输入丢字。
- **同一行的控件**：`--in-row-of=<锚点Locator>` 只取垂直中心落在锚点纵向范围内的命中，`--index` 变为行内序号，例如 `ui click "name=Btn_Next" --in-row-of="text=V-Sync"`。锚点须唯一可见；`ui find ... --in-row-of=` 列出行内命中及其全集下标。只认横向同一行，标题在上、按钮在下的两行条目仍要按容器结构定位。`--index` 越界时报错会列出该 Locator 自己的前 5 个命中。
- **点击前校验**：`ui click` 默认断言最上层命中是目标或其子节点；目标为 `HitTestInvisible` / `SelfHitTestInvisible` 时，也允许命中它的实际祖先，但要求目标当前几何仍包含落点、路径可见且可用，结果附真实容器 `hit_via`。命中相邻条目、遮挡层或禁用目标仍失败。列表/页签优先直接用文字 Locator 点；确实需坐标点击时先找条目/按钮容器 rect 而非内层 TextBlock rect，并加 `--expect-hit=<目标Locator>`，不要靠 `--no-check` 绕过点错邻居。回读页面状态/日志才算业务生效。
- **悬停保持**：`ui move` 不移动真实鼠标，每次移动完成后保持注入的悬停 10 秒；继续 move 会续期，`ui release`、最后一个鼠标键抬起、排队输入失败或到期会结束。保持期间临时抑制 Slate 自动光标移动，结束恢复原开关值，不永久关闭。真实鼠标输入仍可能改变命中。`hover` 只是命中节点的 Slate `IsHovered`，不代表业务 Tips 已出现；用已确认的浮窗 Locator/内容作等待条件，随后查询或截图。先移出再移入可重新触发 Enter；重复同点 move 只续期，不保证再次触发 Enter。原生 Slate ToolTip 还有真实光标/前台等条件，不能据此宣称所有浮窗都可后台触发。
- **滚动回读**：`ui scroll` 返回 `handled` / `moved`。`handled` 是整条事件路径有没有控件处理滚轮，不一定是滚动容器本身；`moved=false` 表示光标下内容没移动（已到边界、容器 `ConsumeMouseWheel=Never` 不响应滚轮，或被外围面板接管）。`handled=true` 且 `moved=false` 时，先读容器的 `consume_mouse_wheel` 与 `get_scroll_offset()` 再下结论。queued 成功不代表滚动生效。容器不吃滚轮时改用 `ui drag` 拖动内容。
- **长按与按住**：`ui click ... --hold=秒`、`ui key <键> --hold=秒` 是定时长按，命令在抬起后才返回。要按住到某个条件成立，用 `ui keydown` / `ui mousedown` 加 CLI 的 `--wait-until`，然后 `ui keyup` / `ui mouseup`。键盘有现成清单：`sequence --action hold-until --param key=E --param "until=<条件表达式>"`。拖动用 `ui drag <起点> --to=x,y [--frames=20]`，或者 `mousedown` → `move` → `mouseup`。这些命令都排在同一条时间线上，前一步失败时后面的步骤自动取消。按住的键到 `--max-hold`（默认 30 秒）会自动抬起，sequence 中途失败也会自动释放；需要时手动 `ui release`。`mousedown` 和 `ui click` 一样校验落点是否被遮挡。
- **输入在下一帧执行**：本次输出里的焦点、状态都是输入执行前的；用 `--wait-until` 在同一次调用里确认，或在下一次调用里用 `ui find` / 截图确认。
- **隐藏控件查询**：`ui find "name=<控件名>" --hidden` 查询已有隐藏/未排布节点，显示 `hidden_by` 父级隐藏原因、`!geometry` 无效坐标和 `!query-only` 标记；避免展开整棵树。所有隐藏查询结果的下标/坐标仅作诊断，点击或截图须重新查询可见目标。默认 find 仍只查可见非零尺寸节点，空结果不证明控件不存在；必要时再 `tree --hidden --full` 查层级或查蓝图静态结构。未创建或未由容器公开的节点无法保证查到。
- **资产编辑器标签页在前台时**，关卡编辑器里的面板（内容浏览器、关卡视口、PIE 视口）不可见，控件树里也找不到。

## screenshot

图像在本地用 Win32 抓取。普通窗口截图不依赖远控；`--widget` / `--pie` 先通过 AgentTools 查询目标几何，需插件已重编。

```bash
# 截取编辑器主窗口（默认存到 ./.codebuddy/temp/ue_screenshots/<时间>.png，缩到 1600 宽）
python scripts/ue_cli.py screenshot

# 只截桌面坐标区域（直接用控件的 rect，自动选中所在窗口，包括下拉菜单等弹出层）
# 副屏坐标可能为负，必须写成 --rect=... 形式，否则会被当成参数名
python scripts/ue_cli.py screenshot --rect=-2400,300,800,600

# 按 Locator 截控件（在编辑器里查 rect，需 AgentTools）；命中多个用 --index，--window 限定独立窗口
python scripts/ue_cli.py screenshot --widget="type=SContentBrowser" --index=1

# 截最上层弹出菜单/弹出层（打开菜单后直接截，不用先查坐标）
python scripts/ue_cli.py screenshot --popup

# 按窗口内像素裁剪（x,y,w,h）；--max-width 0 保留原分辨率；--out 指定输出路径
python scripts/ue_cli.py screenshot --crop 1270,330,1460,830 --max-width 0

# 列出可截取的 UE 窗口（含无标题弹出层）；--title 按标题子串选窗口
python scripts/ue_cli.py screenshot --list

# 直接截 PIE 视口并语义命名归档，一次完成；多视口先 --pie --list，再用 --instance 选择
python scripts/ue_cli.py screenshot --pie --name=feature-view --archive=.codebuddy/temp/evidence
python scripts/ue_cli.py screenshot --pie --list
python scripts/ue_cli.py screenshot --pie --instance=1 --name=feature-view --archive=.codebuddy/temp/evidence

# 刚切页/打开界面：等画面稳定（相邻两帧几乎不变）再保存，最多等 5 秒
python scripts/ue_cli.py screenshot --pie --wait-stable=5 --name=feature-view --archive=.codebuddy/temp/evidence
```

- **画面稳定**：控件树出现不等于画面画完，入场动画（淡入、位移）和异步加载期间截到的是半透明或空白画面。`--wait-stable=秒` 每 0.2 秒重抓，相邻两帧平均灰度差低于 1（0~255）才保存，结果带 `stable` / `waited` / `last_diff`；超时仍保存最后一帧并标 `stable=false`，此时画面可能仍在变化（持续动画、粒子），不能当作已就绪。只证明画面不再变化，不证明内容正确。
- `--pie` 按 WorldContext 关联真实游戏视口，结果附 world/instance，不误取编辑器 SViewport；只覆盖本编辑器进程，未排布/最小化时不可截，多个匹配不猜首项。`--instance` 使用列表中的真实编号，不是列表下标。
- `--name` + `--archive` 直接保存到证据目录，文件名自动追加时间戳与细分时间，重复截图不覆盖；不复制第二份。`--out` 保留精确路径，不能同时配 `--name` 或 `--archive`。`--pie` / `--widget` / `--rect` / `--popup` 为互斥截图目标；`--pie` 只截整视口，局部 PIE 用 `--widget` / `--rect` 的桌面坐标，不拿缩放后的整屏图当裁剪坐标。`--crop` 只用于窗口内原始坐标，不与 `--pie` / `--widget` / `--rect` 混用。
- **局部留边**：`screenshot --widget="name=Panel" --margin=8 --max-width=0`，或 `--rect=x,y,w,h --margin=8`。`--margin` 为非负桌面像素，四边扩展后裁回原窗口，不改变选窗中心；只对 `--widget` / `--rect` 生效。结果 `rect` 是实际捕获的桌面区域，`origin_size` / `saved_size` 分别是缩放前后大小。浮窗阴影、标题靠边时建议留 8 像素，再按实际截图确认。
- 坐标均为原始桌面像素；负坐标可原样传 `ui click --at=-x,y` 和 `--rect=...`。先裁剪再缩放；每张截图旁保存 `<图片>.json`，含实际抓取时的 `rect`、`origin_size`、`saved_size`。图片局部坐标用 `ui at --from-image=<PNG> --point=x,y` 或 `ui click --from-image=<PNG> --point=x,y --expect-hit=<Locator>`；横纵轴分别换算，支持负桌面原点和缩放舍入。`--at` 仍为桌面坐标，不与图片模式混用；drag 的 `--to` 仍是桌面坐标。缺失/损坏元数据或越界点不发送输入。
- 图片坐标必须是保存图片本身的像素，不是查看器再次缩放的显示坐标。换算对应截图时的位置，不承诺窗口移动或布局变化后仍有效；这类情况重新截图，并保留 `--expect-hit` / 业务终态确认。元数据文件随图片移动时需保持其中 path 一致，不能复用其他图片的 metadata。
- 编辑器弹出模态对话框（如"保存修改？"、P4 签出确认）时 Remote Execution 不响应，此时只能靠截图看清卡在哪里。
- 截图是窗口当前画面：窗口最小化时失败；设计器画面受缩放和分辨率预设影响。用 `read_file` 查看 PNG。
- `read_file` 提示当前模型不支持图片时，截图对你无效：不要根据截图下结论或推测画面，改用控件树和日志确认；需要看视觉效果的，在回复里列出截图路径交给用户看。

## PIE 游戏界面

- 键鼠与手柄模拟轴都经过 Slate 输入预处理器；文字输入派发字符事件，聚焦直接设置 Slate 焦点。键鼠接口的 success 只代表排队；同步 `analog_input` 的 success 表示单事件已处理，`handled` 仍不证明业务响应。导航可在预处理器直接完成，不要求一定经过 EnhancedInput。
- Slate 在后台默认忽略回包里的鼠标捕获、光标移动和锁定请求，不只影响点击。驱动统一在聚焦、点击、滚轮、按键、字符的同步执行期间允许后台处理，结束恢复原值；延迟抬起单独使用同样的作用域，不在等待期间常开开关。
- 按键抬起按 `GFrameCounter` 至少晚两帧，避免新增 ticker 同帧执行让等待缩水；后台世界暂停或不处理 PlayerInput 时，仍不能保证业务层在按住期间求值。
- 这不等于激活编辑器：视口首次捕获、系统光标锁定、设备轮询还有独立的前台条件；遇到这类限制仍需激活窗口。不绕过预处理器、弹窗遮挡或业务状态。
- 游戏按钮常有业务门槛（要双击、只在特定状态响应等），点了没反应先读按钮绑定的代码，再怀疑输入。
- 确认业务效果读日志：用 `log mark` 在操作前取基线，之后 `log read --since=<游标> --filter=<关键词>`；要边操作边确认用 `exec ... --log-file=<路径> --wait-log=<关键词>`。按键后找输入处理代码里的日志，判断输入有没有到业务层。路径通常为 `Saved/Logs/<项目名>.log`，参数及轮转处理见 [cli.md](cli.md#log本地日志观察)。
- **确认 PIE 世界**：先 `exec --action pie worlds`，枚举当前 PIE 上下文、PC 数量和 PC0 类名。`UnrealEditorSubsystem.get_game_world()` 默认取 PIE 实例 0，未必是要操作的客户端；返回 Login 世界不代表客户端 travel 失败。不要从 ObjectIterator 或列表第一项盲选，操作时按确认过的世界路径明确选择并在 travel 后重查；无 PC 也不单独证明世界过期。枚举不覆盖另起进程的客户端。
- **运行 TS/JS 的通道**：Python Remote Execution 只执行 Python，不自动提供运行时 TS 求值。先查当前运行环境公开接口；已启用 Inspector 时按 [editor_tools.md](editor_tools.md#运行时-js--ts-inspector-诊断) 发现目标、在现有上下文或真实调用帧只读取数并清理。控制台回显不证明业务执行，不反复猜命令、调用受保护委托或加载另一套模块；构建与重开 PIE 的项目流程查项目资料。
- **启动/切图期间远控会超时**：PIE 启动、地图加载会阻塞游戏线程，`--wait-until` 的单次求值可能超过 `--timeout`（默认 30s）。等待轮询遇到这种 `Timeout` 会继续收那条还没回来的结果，不重新发送，也不当作条件失败；若整段等待最终超时，先探测现场再决定，不要重发启动动作。
- 怎么登录、怎么进到目标界面属于项目知识，查项目文档或记忆，不在本 Skill 里。

## 常见场景

- **看 WBP 静态布局**：`exec --action open_asset <WBP路径>`，等 1~2 秒再 `screenshot`。设计器里脚本逻辑不运行，列表/数据为空。
- **看运行时界面**：分开确认会话启动、目标页面出现、数据/模型等资源就绪。`pie status=running` 不证明客户端有 PC，控件出现也不证明模型加载完成。启动后用目标控件作为页面等待条件：`exec --action pie start --wait-until "unreal.AgentSlateDriverFunctionLib.find_widgets('class=<HUD 根控件类>', '') != '[]'" --wait 120 --timeout 150`，资源就绪再查业务加载状态/日志；只有视觉证据时，在有界等待后复查截图。
  - 初期黑屏、空模型先作为加载暂态待确认，不马上归因或委派代码排查。相邻蓝图报错不等于根因；加载稳定后仍异常再分析，等待超时要保留“未就绪/未验证”的结论。
  - HUD 根控件通常铺满整个 PIE 视口，看具体区域要按其中的子控件截。
  - 引擎直接画在视口上的文字（屏幕调试信息 `Preparing ...`、`NAVMESH NEEDS TO BE REBUILT`、stat 数值等）不是 Slate 控件，控件树里没有，只能截图读。
- **菜单**：`ui click "text=Window"` 后，下拉菜单是新的无标题窗口，`ui windows` 能看到，`screenshot --popup` 直接截；`ui key Escape` 关闭。
- **下拉选项**：ComboBox 展开后的选项常是弹出层里的 `STextBlock` / 列表条目，不是另一个 `SComboBox`。用 `ui find "text=<选项文字>"`，有重名或自定义结构时查看弹层子树，点击后回读选中值。
- **布局验收**：按钮能执行不代表布局合格；长文本更新后，检查相邻控件的 `rect`、可见性和空间是否被挤压。明显异常必须列为未通过或待确认，不能因功能日志正常忽略；模型读不了图片时保留截图供人工确认。
- **证据边界**：报告区分运行证据、代码推断与未验证。同一客户端的账号差异不证明其它构建资产完整；读到数据或页面不证明消耗/请求回包通过。未改运行产物的外部探针清理，与临时业务注入后重建并重跑，是不同验证要求；没有重跑就如实说明，不能一概声称最终产物验收完成。
- **内容浏览器**：找资产应该用 AssetRegistry 脚本，界面只用于确认显示效果。要操作界面时注意：
  - 可能同时开着多个内容浏览器，用 `ui find "hint~=Search"` 列出各自的搜索框，按 `--index` 选。
  - 搜索框的提示文字随当前目录变化（`Search Assets`、`Search Blueprints` 等），不要写死。
  - 搜索只在当前目录及其子目录下进行，搜不到时先确认浏览器停在哪个目录。
