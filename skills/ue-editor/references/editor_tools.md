# 编辑器工具 API 参考

> 本文档收录 UE Editor Python API 中编辑器工具类常用接口。

## EditorUtilityLibrary

### get_selected_assets

```python
assets = unreal.EditorUtilityLibrary.get_selected_assets()
```

- **返回**: `list[unreal.Object]` — 当前在 Content Browser 中选中的资产

### get_selected_asset_data

```python
asset_data_list = unreal.EditorUtilityLibrary.get_selected_asset_data()
```

- **返回**: `list[unreal.AssetData]`

### get_selection_set

```python
actors = unreal.EditorUtilityLibrary.get_selection_set()
```

- **返回**: `list[unreal.Actor]` — 当前在 Viewport 中选中的 Actor 列表

## EditorLevelLibrary（编辑器功能）

### get_editor_world

```python
world = unreal.EditorLevelLibrary.get_editor_world()
```

- **返回**: `unreal.World` — 当前编辑器世界

### set_selected_level_actors

```python
unreal.EditorLevelLibrary.set_selected_level_actors(actors)
```

- **参数**: `actors` (`list[unreal.Actor]`) — 要选中的 Actor 列表

### pilot_level_actor

```python
unreal.EditorLevelLibrary.pilot_level_actor(actor)
```

- **参数**: `actor` (`unreal.Actor`) — 将视口摄像机对准该 Actor

## LevelEditorSubsystem（视口控制）

### get_level_viewport_camera_info / set_level_viewport_camera_info

```python
subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

# 获取视口摄像机位置和旋转
location, rotation = subsystem.get_level_viewport_camera_info()

# 设置视口摄像机
subsystem.set_level_viewport_camera_info(
    unreal.Vector(0, 0, 500),
    unreal.Rotator(-45, 0, 0)
)
```

## UnrealEditorSubsystem（编辑器全局）

### get_editor_world

```python
subsystem = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
world = subsystem.get_editor_world()
```

## AutomationLibrary（截图）

### take_high_res_screenshot

```python
unreal.AutomationLibrary.take_high_res_screenshot(
    resolution_x=1920,
    resolution_y=1080,
    filename='D:/Screenshots/capture.png'
)
```

- **参数**:
  - `resolution_x` (`int`)
  - `resolution_y` (`int`)
  - `filename` (`str`) — 输出文件路径
- **注意**: 只拍关卡视口，**不包含 UMG/UI**，不能用来确认界面布局。

## 控制台命令

### execute_console_command

```python
# 通过 KismetSystemLibrary 执行控制台命令
world = unreal.EditorLevelLibrary.get_editor_world()
unreal.SystemLibrary.execute_console_command(world, 'stat fps')
```

- **参数**:
  - `world` (`unreal.World`)
  - `command` (`str`) — 控制台命令字符串

### 常用控制台命令参考

| 命令 | 说明 |
|------|------|
| `stat fps` | 显示帧率 |
| `stat unit` | 显示各线程耗时 |
| `stat memory` | 显示内存使用 |
| `r.SetRes 1920x1080f` | 设置分辨率 |
| `obj list` | 列出所有对象 |

## Actor 组件查询

### get_components_by_class

```python
components = actor.get_components_by_class(unreal.StaticMeshComponent)
```

- **参数**: `component_class` (`type`)
- **返回**: `list[unreal.ActorComponent]`

### get_component_by_class

```python
comp = actor.get_component_by_class(unreal.StaticMeshComponent)
```

- **返回**: `unreal.ActorComponent` 或 `None`

### 属性读写

```python
# 读取属性
value = actor.get_editor_property('property_name')

# 写入属性
actor.set_editor_property('property_name', new_value)
```

## 运行时 JS / TS Inspector 诊断

适用于已启用兼容 Chrome DevTools Protocol（CDP）的本地运行时。它是本地调试通道，不是 Python Remote Execution 的 JS 功能；无需为只读取数改业务 bundle。只操作当前用户授权的项目调试实例，不扫描其它机器或强抢已占用的调试连接。

1. **确认目标**：先 `exec --action pie worlds` 选客户端，再从目标 GameInstance 的已公开属性、项目配置或启动日志确认调试端口。查 `http://127.0.0.1:<端口>/json/list`，使用实际返回/实现提供的 WebSocket 地址；多 PIE 不假定端口相同，配置和启用条件属于项目 Reference。
2. **建立连接**：复用本地已有 WebSocket 工具/依赖。多行 Node 探针写本地 `.cjs` 文件，不堆 `node -e` 引号，也不交给只执行 Python 的 `exec --file`。CDP 请求用独立 id 对应响应，检查协议 error 与 `exceptionDetails`；连接成功不等于表达式成功。
3. **先看已有上下文**：用 `Runtime.enable` / `Debugger.enable` 获得实际执行上下文与 `Debugger.scriptParsed` 的已加载脚本。全局求值指定已确认上下文；不存在的全局变量、空 `require.cache` 不证明业务模块未加载。不要为找对象 `require` 旧散装文件、重建模块或猜转译后的导入名，以免创建第二套实例。
4. **必要时用真实调用帧**：全局读不到业务局部状态时，从已加载脚本确认当前 URL、源码与入口位置，用 `Debugger.setBreakpointByUrl` 设置本次断点（行列从 0 开始）。只有断点已解析到目标位置，才输出 ready 并让另一次 CLI/UI 操作触发入口；不要边启动探针边抢先点击。
5. **只读取数**：收到 `Debugger.paused` 后核对函数、脚本与位置，选对应 `callFrameId` 用 `Debugger.evaluateOnCallFrame` 读取当次已有局部变量/导入。只读现有字段或快照，限量输出关键值；求值支持时启用 `throwOnSideEffect`，检查拒绝与异常，不关闭保护强行调用。只读不是协议自动保证，不能发业务请求、改账号数据或执行未知 getter。暂停期间避免等 UE Python/界面响应，先完成读取并恢复执行。
6. **必须清理**：为连接、等断点、求值设置有限超时；成功、错误、超时和中断都进入清理。用 `Debugger.removeBreakpoint` 移除本次断点，`Runtime.releaseObjectGroup` 释放本次对象组（如使用）；只对本次导致的暂停发送 `Debugger.resume` 并确认已恢复，再断开退出。不要把“进程退出”当作恢复证明，不确定是否仍暂停就先处理现场。保留有限证据、删除一次性探针，不清理其它人的断点、暂停或会话。
7. **按边界沉淀**：项目端口与世界的关联、真实加载产物、入口和作用域知识进项目 Reference；只有实际跑通且可复用的探针才升为项目 Lib。单账号/单版本成功不宣称通用跨账号、跨版本可用，不在通用 Skill 写业务变量或固定断点行号。
