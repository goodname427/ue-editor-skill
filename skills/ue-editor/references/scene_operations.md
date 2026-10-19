# 场景操作 API 参考

> 本文档收录 UE Editor Python API 中最常用的场景操作接口。

## EditorActorSubsystem

> 推荐使用 Subsystem API 替代已弃用的 `EditorLevelLibrary` 同名方法，避免 DeprecationWarning。

获取 Subsystem 实例：

```python
actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
```

### get_all_level_actors

```python
actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsys.get_all_level_actors()
```

- **返回**: `list[unreal.Actor]` — 当前关卡中所有 Actor
- **示例**: 获取场景中所有 Actor 并打印名称

```python
actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
for a in actor_subsys.get_all_level_actors():
    unreal.log(a.get_name())
```

### get_all_level_actors_of_class

```python
actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsys.get_all_level_actors_of_class(actor_class)
```

- **参数**: `actor_class` (`type`) — Actor 类型，如 `unreal.StaticMeshActor`
- **返回**: `list[unreal.Actor]`

```python
actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
meshes = actor_subsys.get_all_level_actors_of_class(unreal.StaticMeshActor)
```

### spawn_actor_from_class

```python
actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actor = actor_subsys.spawn_actor_from_class(actor_class, location, rotation=[0,0,0])
```

- **参数**:
  - `actor_class` (`type`) — 要生成的 Actor 类
  - `location` (`unreal.Vector`) — 世界坐标
  - `rotation` (`unreal.Rotator`, 可选) — 旋转
- **返回**: `unreal.Actor`

```python
actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
loc = unreal.Vector(100, 200, 0)
rot = unreal.Rotator(0, 90, 0)
actor = actor_subsys.spawn_actor_from_class(unreal.StaticMeshActor, loc, rot)
```

### destroy_actor

```python
actor_subsys = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actor_subsys.destroy_actor(actor)
```

- **参数**: `actor` (`unreal.Actor`) — 要删除的 Actor
- **返回**: `bool`

## EditorLevelLibrary（仍可用，暂无替代）

> 以下方法在 `EditorActorSubsystem` 中无直接替代，仍使用 `EditorLevelLibrary`。

### get_actor_reference

```python
ref = unreal.EditorLevelLibrary.get_actor_reference(path_to_actor)
```

- **参数**: `path_to_actor` (`str`) — Actor 路径
- **返回**: `unreal.Actor`

### set_actor_transform / get_actor_transform

设置/获取 Actor 的世界变换（位置、旋转、缩放）。

```python
# 获取
transform = actor.get_actor_transform()
loc = transform.translation
rot = transform.rotation.rotator()
scale = transform.scale3d

# 设置位置
actor.set_actor_location(unreal.Vector(0, 0, 100), False, False)

# 设置旋转
actor.set_actor_rotation(unreal.Rotator(0, 45, 0), False)

# 设置缩放
actor.set_actor_scale3d(unreal.Vector(2, 2, 2))
```

## EditorLoadingAndSavingUtils

### load_map

```python
unreal.EditorLoadingAndSavingUtils.load_map(map_path)
```

- **参数**: `map_path` (`str`) — 关卡资产路径，如 `/Game/Maps/MyLevel`
- **返回**: `bool`

### save_current_level

```python
unreal.EditorLoadingAndSavingUtils.save_current_level()
```

- **返回**: `bool`

### new_blank_map

```python
unreal.EditorLoadingAndSavingUtils.new_blank_map(save_existing=True)
```

- **参数**: `save_existing` (`bool`) — 是否先保存当前关卡

### get_dirty_map_packages

```python
packages = unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
```

- **返回**: `list[unreal.Package]` — 已修改未保存的地图包

## GameplayStatics（场景查询）

### get_all_actors_of_class

```python
actors = unreal.GameplayStatics.get_all_actors_of_class(world, actor_class)
```

- **参数**:
  - `world` (`unreal.World`) — 通常用 `unreal.EditorLevelLibrary.get_editor_world()`
  - `actor_class` (`type`)
- **返回**: `list[unreal.Actor]`
