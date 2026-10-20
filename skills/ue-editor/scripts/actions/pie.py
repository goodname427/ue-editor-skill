"""
PIE 启停与状态。启停请求在下一帧才生效，脚本内无法等待，需由 CLI 的 --wait-until 跨帧轮询：

  exec --action pie start --wait-until "unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()" --wait 90
  exec --action pie stop --wait-until "not unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor()"
  exec --action pie status
  exec --action pie worlds      枚举本编辑器进程当前 PIE 世界上下文，不自动选择世界

is_in_play_in_editor() 为真只说明 PIE 会话已开始，地图、着色器、界面可能仍在加载（画面右下角 Preparing Shaders 等）。
要看运行时界面，直接把目标控件出现作为等待条件（需 AgentTools）：
  --wait-until "unreal.AgentSlateDriverFunctionLib.find_widgets('class=<HUD 根控件类>', '') != '[]'" --wait 120 --timeout 150
"""
import unreal

subsystem = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
mode = ARGS[0] if ARGS else ''

if mode == 'start':
    subsystem.editor_request_begin_play()
    print('start requested')
elif mode == 'stop':
    subsystem.editor_request_end_play()
    print('stop requested')
elif mode == 'status':
    print('running' if subsystem.is_in_play_in_editor() else 'stopped')
elif mode == 'worlds':
    import json

    default_world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
    rows = []
    for world in unreal.EditorLevelLibrary.get_pie_worlds(True):
        if world is None:
            continue
        pc = unreal.GameplayStatics.get_player_controller(world, 0)
        rows.append({
            'world': world.get_path_name(),
            'default_game_world': world == default_world,
            'pc_count': unreal.GameplayStatics.get_num_player_controllers(world),
            'pc0': pc.get_path_name() if pc else None,
            'pc0_class': pc.get_class().get_name() if pc else None,
        })
    print(json.dumps({'running': subsystem.is_in_play_in_editor(), 'worlds': rows}, ensure_ascii=False))
else:
    raise RuntimeError(__doc__)
