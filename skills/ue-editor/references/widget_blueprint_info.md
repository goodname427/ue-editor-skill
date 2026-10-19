# Widget 蓝图信息读取 API 参考

> 本文档收录 `UAgentWidgetBlueprintInfoFunctionLib` 提供的 Widget 蓝图信息读取接口。
> 所有函数返回 JSON 格式字符串，便于 Agent 解析。

## AgentWidgetBlueprintInfoFunctionLib

> 位于工程插件 `Plugins/AgentTools`（`AgentWidgetBlueprintInfoLib` 模块，仅编辑器），编译后方可使用。

### GetWidgetBlueprintInfo

获取 Widget 蓝图的基础信息。

```python
info = unreal.AgentWidgetBlueprintInfoFunctionLib.get_widget_blueprint_info('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`) — Widget 蓝图资产路径
- **返回**: `str` — JSON 对象，包含 `name`, `path`, `parent_class`, `widget_count`, `animation_count`, `binding_count`, `function_count`, `root_widget_type`

### GetWidgetTreeHierarchy

获取完整的 WidgetTree 层级结构（树形 JSON）。

```python
tree = unreal.AgentWidgetBlueprintInfoFunctionLib.get_widget_tree_hierarchy('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — 嵌套 JSON 对象，每个节点包含 `name`, `type`, `visibility`, `is_variable`, `children`

### GetAllWidgetsFlat

获取 WidgetTree 中所有 Widget 的扁平列表。

```python
widgets = unreal.AgentWidgetBlueprintInfoFunctionLib.get_all_widgets_flat('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `type`, `is_variable`, `visibility`, `parent`, `child_index`

### GetWidgetDetailInfo

获取指定 Widget 的详细属性信息（含所有 UPROPERTY）。

```python
detail = unreal.AgentWidgetBlueprintInfoFunctionLib.get_widget_detail_info('/Game/UI/WBP_Main', 'TextBlock_Title')
```

- **参数**:
  - `asset_path` (`str`)
  - `widget_name` (`str`) — WidgetTree 中的 Widget 名称
- **返回**: `str` — JSON 对象，包含 `name`, `type`, `visibility`, `render_transform`, `render_opacity`, `slot`, `properties`（详细属性列表）

### GetWidgetSlotInfo

获取指定 Widget 的 Slot（布局槽）信息。

```python
slot = unreal.AgentWidgetBlueprintInfoFunctionLib.get_widget_slot_info('/Game/UI/WBP_Main', 'Image_BG')
```

- **参数**:
  - `asset_path` (`str`)
  - `widget_name` (`str`)
- **返回**: `str` — JSON 对象，包含 `slot_type` 及对应 Slot 类型的属性（CanvasPanel: `anchors`, `offset`, `alignment`, `auto_size`, `z_order`; HorizontalBox/VerticalBox: `padding`, `size`, `horizontal_alignment`, `vertical_alignment`; Overlay: `padding`, `horizontal_alignment`, `vertical_alignment`）

### GetBlueprintVariables

获取蓝图中声明的所有变量。

```python
vars = unreal.AgentWidgetBlueprintInfoFunctionLib.get_blueprint_variables('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `type`, `sub_type`, `is_array`, `is_set`, `is_map`, `instance_editable`, `blueprint_read_only`, `category`, `default_value`

### GetWidgetVariables

获取 WidgetTree 中所有标记为变量的 Widget。

```python
widget_vars = unreal.AgentWidgetBlueprintInfoFunctionLib.get_widget_variables('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `type`

### GetWidgetAnimations

获取所有 Widget 动画列表。

```python
anims = unreal.AgentWidgetBlueprintInfoFunctionLib.get_widget_animations('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `duration`, `track_count`

### GetWidgetAnimationDetail

获取指定动画的详细信息。

```python
anim_detail = unreal.AgentWidgetBlueprintInfoFunctionLib.get_widget_animation_detail('/Game/UI/WBP_Main', 'FadeIn')
```

- **参数**:
  - `asset_path` (`str`)
  - `animation_name` (`str`)
- **返回**: `str` — JSON 对象，包含 `name`, `duration`, `bindings`（绑定的 Widget 及其 Track 信息）

### GetBlueprintFunctions

获取蓝图中定义的所有函数。

```python
funcs = unreal.AgentWidgetBlueprintInfoFunctionLib.get_blueprint_functions('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `parameters`（参数列表）, `return_values`（返回值列表）

### GetBlueprintEvents

获取蓝图中的所有事件（自定义事件和引擎事件）。

```python
events = unreal.AgentWidgetBlueprintInfoFunctionLib.get_blueprint_events('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `type`（`CustomEvent` 或 `EngineEvent`）, `graph`

### GetPropertyBindings

获取所有属性绑定信息。

```python
bindings = unreal.AgentWidgetBlueprintInfoFunctionLib.get_property_bindings('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `widget_name`, `property_name`, `function_name`, `source_property`, `kind`

### GetNamedSlots

获取所有 NamedSlot 信息。

```python
slots = unreal.AgentWidgetBlueprintInfoFunctionLib.get_named_slots('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `content_name`, `content_type`

### GetAllGraphs

获取蓝图中所有图表（EventGraph、Function、Macro 等）。

```python
graphs = unreal.AgentWidgetBlueprintInfoFunctionLib.get_all_graphs('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `type`（`EventGraph`/`Function`/`Macro`/`DelegateSignature`/`Other`）, `node_count`

### GetGraphNodes

获取指定图表中所有节点的信息。

```python
nodes = unreal.AgentWidgetBlueprintInfoFunctionLib.get_graph_nodes('/Game/UI/WBP_Main', 'EventGraph')
```

- **参数**:
  - `asset_path` (`str`)
  - `graph_name` (`str`) — 图表名称（从 GetAllGraphs 获取）
- **返回**: `str` — JSON 数组，每个元素包含 `node_class`, `title`, `compact_title`, `guid`, `pos_x`, `pos_y`, `enabled`, `comment`, `input_pin_count`, `output_pin_count`

### GetNodeDetail

获取指定节点的详细信息（含所有引脚及连接关系）。

```python
detail = unreal.AgentWidgetBlueprintInfoFunctionLib.get_node_detail('/Game/UI/WBP_Main', 'EventGraph', '<node-guid>')
```

- **参数**:
  - `asset_path` (`str`)
  - `graph_name` (`str`)
  - `node_guid` (`str`) — 节点 GUID（从 GetGraphNodes 获取）
- **返回**: `str` — JSON 对象，包含 `node_class`, `title`, `guid`, `pins`（每个 pin 含 `name`, `direction`, `type`, `sub_type`, `default_value`, `links`（连接的目标节点和引脚））

### GetAllWidgetBlueprintsInDirectory

获取指定目录下所有 Widget 蓝图。

```python
wbps = unreal.AgentWidgetBlueprintInfoFunctionLib.get_all_widget_blueprints_in_directory('/Game/UI', recursive=True)
```

- **参数**:
  - `directory_path` (`str`) — 目录路径
  - `recursive` (`bool`) — 是否递归子目录（默认 True）
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `path`, `package_path`

### GetWidgetBlueprintInheritanceChain

获取 Widget 蓝图的继承链。

```python
chain = unreal.AgentWidgetBlueprintInfoFunctionLib.get_widget_blueprint_inheritance_chain('/Game/UI/WBP_Main')
```

- **参数**: `asset_path` (`str`)
- **返回**: `str` — JSON 数组，从当前类到 UUserWidget 的继承链，每个元素包含 `name`, `path`, `is_blueprint`

## ChildWidget 编辑

### RenameChildWidget

重命名 WidgetTree 中指定的 ChildWidget。

```python
result = unreal.AgentWidgetBlueprintInfoFunctionLib.rename_child_widget('/Game/UI/WBP_Main', 'TextBlock_1', 'TextBlock_Title')
```

- **参数**:
  - `asset_path` (`str`)
  - `old_widget_name` (`str`) — 当前 Widget 名称
  - `new_widget_name` (`str`) — 新的 Widget 名称
- **返回**: `str` — JSON 对象，包含 `success`, `message`

### SetWidgetProperty

设置指定 Widget 的单个属性值。

```python
result = unreal.AgentWidgetBlueprintInfoFunctionLib.set_widget_property('/Game/UI/WBP_Main', 'Button_Start', 'bIsEnabled', 'False')
```

- **参数**:
  - `asset_path` (`str`)
  - `widget_name` (`str`)
  - `property_name` (`str`) — UPROPERTY 名称（如 `Visibility`、`bIsEnabled`）
  - `property_value` (`str`) — 属性值（使用 UE 的 `ImportText` 格式）
- **返回**: `str` — JSON 对象，包含 `success`, `message`

### SetWidgetProperties

批量设置指定 Widget 的多个属性值。

```python
import json
props = json.dumps({'bIsEnabled': 'False', 'RenderOpacity': '0.5'})
result = unreal.AgentWidgetBlueprintInfoFunctionLib.set_widget_properties('/Game/UI/WBP_Main', 'Button_Start', props)
```

- **参数**:
  - `asset_path` (`str`)
  - `widget_name` (`str`)
  - `properties_json` (`str`) — JSON 对象字符串，key 为属性名，value 为属性值
- **返回**: `str` — JSON 对象，包含 `success`, `results`（每个属性的设置结果数组）

### SetWidgetSlotProperties

设置指定 Widget 的 Slot（布局槽）属性。

```python
import json
slot_props = json.dumps({'ZOrder': '5'})
result = unreal.AgentWidgetBlueprintInfoFunctionLib.set_widget_slot_properties('/Game/UI/WBP_Main', 'Image_BG', slot_props)
```

- **参数**:
  - `asset_path` (`str`)
  - `widget_name` (`str`)
  - `slot_properties_json` (`str`) — JSON 对象字符串，key 为 Slot 属性名，value 为属性值
- **返回**: `str` — JSON 对象，包含 `success`, `results`

## 蓝图函数编辑

### AddBlueprintFunction

新增一个空的蓝图函数图表。

```python
result = unreal.AgentWidgetBlueprintInfoFunctionLib.add_blueprint_function('/Game/UI/WBP_Main', 'UpdateScore')
```

- **参数**:
  - `asset_path` (`str`)
  - `function_name` (`str`)
- **返回**: `str` — JSON 对象，包含 `success`, `message`, `graph_name`

### RemoveBlueprintFunction

删除指定的蓝图函数图表。

```python
result = unreal.AgentWidgetBlueprintInfoFunctionLib.remove_blueprint_function('/Game/UI/WBP_Main', 'UpdateScore')
```

- **参数**:
  - `asset_path` (`str`)
  - `function_name` (`str`)
- **返回**: `str` — JSON 对象，包含 `success`, `message`

### RenameBlueprintFunction

重命名指定的蓝图函数。

```python
result = unreal.AgentWidgetBlueprintInfoFunctionLib.rename_blueprint_function('/Game/UI/WBP_Main', 'UpdateScore', 'RefreshScore')
```

- **参数**:
  - `asset_path` (`str`)
  - `old_function_name` (`str`)
  - `new_function_name` (`str`)
- **返回**: `str` — JSON 对象，包含 `success`, `message`

### AddFunctionInputParam

为指定函数添加输入参数。

```python
result = unreal.AgentWidgetBlueprintInfoFunctionLib.add_function_input_param('/Game/UI/WBP_Main', 'UpdateScore', 'NewScore', 'int')
```

- **参数**:
  - `asset_path` (`str`)
  - `function_name` (`str`)
  - `param_name` (`str`)
  - `param_type` (`str`) — 支持 `bool`/`int`/`float`/`string`/`text`/`name`/`object`/`class`/`struct`，未识别时回退为 wildcard
- **返回**: `str` — JSON 对象，包含 `success`, `message`

### AddFunctionOutputParam

为指定函数添加输出参数（自动定位 FunctionResult 节点）。

```python
result = unreal.AgentWidgetBlueprintInfoFunctionLib.add_function_output_param('/Game/UI/WBP_Main', 'UpdateScore', 'bSuccess', 'bool')
```

- **参数**:
  - `asset_path` (`str`)
  - `function_name` (`str`)
  - `param_name` (`str`)
  - `param_type` (`str`) — 取值同 AddFunctionInputParam
- **返回**: `str` — JSON 对象，包含 `success`, `message`

### SetFunctionDescription

设置指定函数的描述（Tooltip，写入 FunctionEntry 节点的 MetaData）。

```python
result = unreal.AgentWidgetBlueprintInfoFunctionLib.set_function_description('/Game/UI/WBP_Main', 'UpdateScore', '刷新分数显示')
```

- **参数**:
  - `asset_path` (`str`)
  - `function_name` (`str`)
  - `description` (`str`)
- **返回**: `str` — JSON 对象，包含 `success`, `message`

## 蓝图函数阅读

### GetBlueprintFunctionDetail

获取指定函数的完整信息（参数列表、描述、节点数量）。

```python
detail = unreal.AgentWidgetBlueprintInfoFunctionLib.get_blueprint_function_detail('/Game/UI/WBP_Main', 'UpdateScore')
```

- **参数**:
  - `asset_path` (`str`)
  - `function_name` (`str`)
- **返回**: `str` — JSON 对象，包含 `name`, `node_count`, `description`, `inputs`, `outputs`

### GetFunctionGraphNodes

获取指定函数图表的所有节点及连接关系（完整调用链，含每个节点详细引脚信息）。

```python
nodes = unreal.AgentWidgetBlueprintInfoFunctionLib.get_function_graph_nodes('/Game/UI/WBP_Main', 'UpdateScore')
```

- **参数**:
  - `asset_path` (`str`)
  - `function_name` (`str`)
- **返回**: `str` — JSON 数组，每个元素同 `GetNodeDetail` 的输出（含 `pins` 与 `links`）

### GetFunctionParams

获取指定函数的输入输出参数列表。

```python
params = unreal.AgentWidgetBlueprintInfoFunctionLib.get_function_params('/Game/UI/WBP_Main', 'UpdateScore')
```

- **参数**:
  - `asset_path` (`str`)
  - `function_name` (`str`)
- **返回**: `str` — JSON 对象，包含 `inputs`, `outputs` 数组，每项含 `name`, `type`, `sub_type`

### SearchBlueprintFunctions

按关键词模糊搜索函数（大小写不敏感）。

```python
matches = unreal.AgentWidgetBlueprintInfoFunctionLib.search_blueprint_functions('/Game/UI/WBP_Main', 'score')
```

- **参数**:
  - `asset_path` (`str`)
  - `keyword` (`str`)
- **返回**: `str` — JSON 数组，每个元素包含 `name`, `input_count`, `output_count`, `description`

## 典型使用流程

### 1. 了解 Widget 蓝图概况

```python
import unreal, json
lib = unreal.AgentWidgetBlueprintInfoFunctionLib
info = json.loads(lib.get_widget_blueprint_info('/Game/UI/WBP_Main'))
print(f"Widget数量: {info['widget_count']}, 动画数量: {info['animation_count']}")
```

### 2. 获取完整 WidgetTree 结构

```python
tree = json.loads(lib.get_widget_tree_hierarchy('/Game/UI/WBP_Main'))
# tree 是嵌套结构，包含 children 数组
```

### 3. 查看某个 Widget 的详细属性

```python
detail = json.loads(lib.get_widget_detail_info('/Game/UI/WBP_Main', 'Button_Start'))
for prop in detail.get('properties', []):
    print(f"  {prop['name']}: {prop['type']} = {prop['value']}")
```

### 4. 批量扫描目录下的 Widget 蓝图

```python
wbps = json.loads(lib.get_all_widget_blueprints_in_directory('/Game/UI'))
for wbp in wbps:
    info = json.loads(lib.get_widget_blueprint_info(wbp['path']))
    print(f"{wbp['name']}: {info['widget_count']} widgets")
```
