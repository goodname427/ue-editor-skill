# Widget 蓝图读写参考

> 读取和改 Widget 蓝图（WBP）的结构、属性、函数。脚本里一律 `import ue_wbp`（`scripts/editor/ue_wbp.py`），常用写操作直接用 `exec --lib wbp_edit ...`（见 [widget_blueprint_edit.md](widget_blueprint_edit.md)）。
> `ue_wbp` 的数据来自 AgentTools 插件 `AgentWidgetBlueprintInfoLib` 模块（仅编辑器）的 C++ 原子接口，再加上引擎自带的 `BlueprintEditorLibrary` / AssetRegistry。找不到 `unreal.AgentWidgetBlueprintInfoFunctionLib` 时，说明插件没编译或没启用。

## 分工

- **C++ 只提供 Python 访问不到的原子能力**：控件树（含 `bIsVariable`）、属性的 UE 文本导出与导入、成员变量、动画绑定、属性绑定、NamedSlot 绑定、图表节点、函数签名、改控件名、加函数参数、函数描述。
- **其余都在 `ue_wbp` 里拼**：树形结构、变量控件、概览、事件列表、函数搜索、单个节点详情、批量设属性、按目录列 WBP、继承链；加函数、删函数、改函数名用 `BlueprintEditorLibrary`。不要在项目脚本里另写一份。
- 写操作只改内存。编译保存用 `wbp_edit save <路径>`，或 `BlueprintEditorLibrary.compile_blueprint` + `EditorAssetLibrary.save_asset`。改之前先签出资产。
- C++ 失败时统一返回 `{"success": false, "message": ...}`，`ue_wbp` 会把它转成 `RuntimeError` 抛出。直接调 C++ 时用 `ue_common.parse` 解析。

## ue_wbp 函数

路径写资产路径，`/Game/UI/WBP_Main` 或 `/Game/UI/WBP_Main.WBP_Main` 都行。

### 控件与属性

| 函数 | 返回 |
|---|---|
| `widgets(path)` | 平铺列表，按遍历顺序：`[{name, type, is_variable, visibility, parent, child_index}]`，`parent` 为空的是根 |
| `root(path)` | 根控件名 |
| `tree(path)` | 嵌套树：`{name, type, is_variable, visibility, children}`，子节点按 `child_index` 排序 |
| `variables(path)` | 勾了"是变量"的控件：`[{name, type}]` |
| `is_variable(path, name)` | `bool` |
| `props(path, name, slot=False)` | `{属性名: UE 文本}`，包含所有可编辑和蓝图可见的属性，`'__type__'` 是控件类名；`slot=True` 时读控件所在插槽（如 `CanvasPanelSlot` 的 `LayoutData`、`ZOrder`），根控件没有插槽会报错 |
| `set_prop(path, name, prop, value, slot=False)` | 用 UE 文本格式写入，走 `PreEditChange` / `PostEditChangeProperty`，返回写入后回读的文本。文本解析失败直接报错（例如 `Visibility=NotAThing`），不会静默写成默认值。改 `bIsVariable` 会按结构性修改处理 |
| `set_props(path, name, {prop: value}, slot=False)` | 按顺序逐个写，返回 `{prop: 回读值}`；某个失败就抛异常，前面已写的保持写入 |
| `rename_widget(path, old, new)` | 改名，并同步变量引用、属性绑定、动画绑定、导航绑定。不需要打开设计器，处理方式与设计器里改名一致 |

`rename_widget` 改名前会检查：新名字不能和控件树里任何控件同名（包括没勾"是变量"的），只能用字母、数字和 `_`，不能以数字开头，也不能和成员变量、函数重名。引擎的名字校验器不检查非变量控件，所以撞上同名对象会直接 fatal，这道检查是专门为此加的。

### 蓝图数据

| 函数 | 返回 |
|---|---|
| `members(path)` | "我的蓝图"里的成员变量：`name, type, sub_type, is_array/is_set/is_map, instance_editable, blueprint_read_only, category, default_value` |
| `animations(path)` | `[{name, duration, bindings:[{widget_name, slot_widget_name, name, tracks:[{track_name, track_type}]}], master_tracks}]`。`widget_name` 是动画实际绑定的控件，改名会同步；`name` 只是轨道上显示的名字 |
| `bindings(path)` | 属性绑定：`widget_name, property_name, function_name, source_property, kind` |
| `named_slots(path)` | 本蓝图的 NamedSlot 控件（`source=widget`，`content_*` 是放进去的子控件），以及父类 NamedSlot 在本蓝图里填入的内容（`source=binding`） |

### 图表与函数

| 函数 | 返回 |
|---|---|
| `graphs(path)` | `[{name, type: Function/EventGraph/Macro/DelegateSignature/Other, node_count}]` |
| `nodes(path, graph, detailed=False)` | 节点：`node_class, title, compact_title, guid, pos_x, pos_y, enabled[, comment][, function_name]`。不加 `detailed` 只给引脚数；加了给全部引脚及连线（`links: [{node_name, node_guid, pin_name}]`） |
| `node(path, graph, guid)` | 单个节点的详细信息 |
| `events(path)` | 事件图里的事件：`[{name, type: CustomEvent/EngineEvent, graph, title}]`，其中 `name` 是事件名（如 `Construct`），不是节点标题 |
| `functions(path, keyword='')` | 函数签名：`[{name, description, node_count, inputs, outputs}]`，参数为 `{name, type[, container][, sub_type]}`；`keyword` 按函数名子串过滤，不区分大小写 |
| `function(path, name)` | 单个函数的签名 |
| `add_function(path, name)` / `remove_function` / `rename_function(path, old, new)` | 内部用 `BlueprintEditorLibrary`，先检查重名或函数是否存在；改名后会回读确认 |
| `add_param(path, func, name, type_text, output=False)` | 加输入参数，或者在 `output=True` 时加返回值（没有结果节点会自动创建）。参数类型写法：`bool/byte/int/int64/float/name/string/text`、`object:<类路径>`、`class:<类路径>`、`struct:<结构体路径>`，末尾加 `[]` 表示数组。类型写错或参数重名都会报错 |
| `set_description(path, func, text)` | 设置函数描述（入口节点的 Tooltip） |

### 资产层面

| 函数 | 返回 |
|---|---|
| `info(path)` | 概览：`name, path, parent_class, widget_count, animation_count, binding_count, function_count, root_widget_type` |
| `inheritance(path)` | 从本类到 `UserWidget` 的继承链：`[{name, path, is_blueprint}]`。蓝图层读资产注册表的 `ParentClass` 标签，原生层用 Python 类型的 `__mro__` |
| `list_dir(directory, recursive=True)` | 目录下的 WBP：`[{name, path, package_path}]`，走 AssetRegistry，不加载资产 |

## 示例

```python
import ue_wbp
p = '/Game/UI/WBP_Main'
print(ue_wbp.info(p))
for w in ue_wbp.widgets(p):
    print(w['name'], w['type'], w['parent'])
print(ue_wbp.props(p, 'Btn_Start')['Visibility'])
print(ue_wbp.set_prop(p, 'Btn_Start', 'Visibility', 'Collapsed'))     # -> 'Collapsed'
print(ue_wbp.set_prop(p, 'Btn_Start', 'ZOrder', '3', slot=True))
print([e['name'] for e in ue_wbp.events(p)])
fn = ue_wbp.add_function(p, 'UpdateScore')
ue_wbp.add_param(p, fn, 'NewScore', 'int')
ue_wbp.add_param(p, fn, 'Target', 'object:/Script/UMG.Button')
ue_wbp.add_param(p, fn, 'Names', 'string[]', output=True)
```

执行：`exec --file <脚本>`，或 `exec "import ue_wbp; print(ue_wbp.info('/Game/UI/WBP_Main'))"`。

## C++ 原子接口（`unreal.AgentWidgetBlueprintInfoFunctionLib`）

`get_widgets`、`get_widget_properties(path, name, slot)`、`get_blueprint_variables`、`get_widget_animations`、`get_property_bindings`、`get_named_slot_bindings`、`get_all_graphs`、`get_graph_nodes(path, graph, detailed)`、`get_blueprint_functions`、`rename_child_widget`、`set_widget_property(path, name, prop, value, slot)`、`add_function_param(path, func, name, pin_type, output)`、`set_function_description`。字段与上面 `ue_wbp` 对应的函数一致。`add_function_param` 的 `pin_type` 用 `BlueprintEditorLibrary.get_basic_type_by_name / get_object_reference_type / get_struct_type / get_array_type` 构造。注意 `get_basic_type_by_name` 收到不认识的名字时会静默返回 int，`ue_wbp.pin_type` 会先做校验。
