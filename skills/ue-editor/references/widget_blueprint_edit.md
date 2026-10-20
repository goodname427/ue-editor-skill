# Widget 蓝图写操作流程

> 本文档收录通过脚本修改 Widget 蓝图的已验证流程。读写组合都在 Skill lib 的 `ue_wbp`，函数一览见 [widget_blueprint_info.md](widget_blueprint_info.md)。
> 多行脚本写成 `.py` 后用 `ue_cli.py exec --file <path>` 执行。

## 通用约定

- **改前签出**：`.uasset` 在版本库里通常是独占签出，改前先签出（P4：`p4 edit -c <CL> <file>`）；只读文件 `save_asset` 会失败或弹窗。
- **改前先读**：用 `ue_wbp.widgets(path)`（或 `wbp_edit list`）确认控件名，再按名字操作。
- **改后收尾**：`ue_wbp.save(path)`（编译 + 保存）；脚本外可直接 `ue_cli.py exec --action wbp_edit save <路径>...`。
- **项目收尾步骤**：工程若有依赖蓝图结构的生成步骤（如脚本层类型声明），在项目 actions / references 里约定并在保存后执行，本 Skill 不内置。

## 优先用 wbp_edit 入口

改名、勾变量、加控件、换控件、移除控件用 `exec --action wbp_edit ...`，用法见脚本 docstring；默认改完即编译保存（`--no-save` 可关）：

```bash
exec --action wbp_edit list  /Game/UI/XXX/WBP_Foo
exec --action wbp_edit rename /Game/UI/XXX/WBP_Foo ScrollBox_173 ScrollView_List
exec --action wbp_edit set   /Game/UI/XXX/WBP_Foo ScrollView_List bIsVariable=True Visibility=Collapsed
exec --action wbp_edit set   /Game/UI/XXX/WBP_Foo ScrollView_List ZOrder=3 --slot              # 改它所在插槽的属性
exec --action wbp_edit add   /Game/UI/XXX/WBP_Foo CanvasPanel_Root Btn_Confirm Button --text=确定 --copy=Btn_Cancel --anchor=0,0,0,0 --offset=100,200,160,48 --align=0.5,0.5
exec --action wbp_edit replace /Game/UI/XXX/WBP_Foo BP_Child /Game/UI/XXX/WBP_Child2   # 默认沿用旧控件的槽位与变量状态
exec --action wbp_edit remove /Game/UI/XXX/WBP_Foo Btn_Confirm
```

`wbp_edit` 覆盖不到的场景（批量建树、复制属性以外的样式改造等）在脚本里直接用 `ue_wbp`，它就是 `wbp_edit` 背后的实现；不要再手写一份 `new_object` / `add_child_to_*` / 移出 Transient 的流程。

## 脚本里改控件

```python
import ue_wbp
P = '/Game/UI/XXX/WBP_Foo'
print(ue_wbp.rename_widget(P, 'ScrollBox_173', 'ScrollView_List'))
print(ue_wbp.set_prop(P, 'ScrollView_List', 'bIsVariable', 'True'))     # 返回回读值 'True'
ue_wbp.add_widget(P, 'CanvasPanel_Root', 'Btn_Confirm', 'Button', text='确定', copy_from='Btn_Cancel',
                  slot={'anchor': (0, 0, 0, 0), 'offset': (100, 200, 160, 48), 'align': (0.5, 0.5)})
ue_wbp.add_widget(P, 'HBox_Bar', 'Img_Icon', 'Image', var=False, slot={'padding': (4, 0, 4, 0), 'size': (1, 'fill'), 'valign': 'center'})
ue_wbp.replace_widget(P, 'BP_Child', '/Game/UI/XXX/WBP_Child2')      # 沿用旧插槽与"是变量"
ue_wbp.remove_widget(P, 'Btn_Old')
print(ue_wbp.props(P, 'Btn_Confirm', slot=True)['LayoutData'])
if not ue_wbp.save(P):
    raise RuntimeError('save failed; check out the asset first')
```

- **改名**：同步变量引用、属性/动画/导航绑定；新名字与控件树里任何控件重名、含空格、以数字开头时直接报错。不要用 Python 的 `widget.rename(...)` 改控件名：它不同步这些引用，撞名时引擎会直接 fatal。
- **改属性**：`set_prop` 的值按 UE 文本格式给（`True`、`Collapsed`），属性名是 C++ 属性名；写后回读，解析失败报错。批量用 `set_props(P, name, {...})`，插槽属性加 `slot=True`。
- **插槽参数**：`slot` 字典见 `ue_wbp.check_slot`。CanvasPanel 用 `anchor` / `offset` / `align`（给了任一项就整体重设，没给的项按 0）；横向/纵向/Overlay 用 `padding` / `size` / `halign` / `valign`。参数在改资产之前校验，不合法时什么都不会改。
- **"是变量"**：新建控件的 `bIsVariable` 默认值随类不同（Widget 基类是 true，多数面板和 TextBlock 显式 false），`add_widget` 总是显式写入（默认勾上，`var=False` 不勾），`replace_widget` 默认沿用旧控件。
- **子蓝图实例**：类写蓝图路径（`/Game/.../WBP_Child`），或 UMG 类名（`Button`、项目类）。
- **样式**：`copy_from` 从同树控件复制 `ue_wbp.STYLE_PROPS` 里两边都有的属性（`widget_style` / `font` / `item_style` / `scroll_bar_style` / `content_padding` / `foreground_color` / `max_list_height`）；文字子控件用 `text_font_from` 复制 `font`。
- **顺序**：没有插入 API，新控件只能追加到父面板末尾；`replace_widget` 换出来的新控件也在末尾，同一父面板有多个子控件时顺序会变。
- **移除**：控件从父面板拿掉后移到 `/Engine/Transient`（换一个没被占用的名字，同名对象已在 Transient 时引擎重命名会 fatal），这样原名可以立刻再用。
- 需要控件对象本身（调引擎 API）时用 `ue_wbp.widget(P, name)`；任意层级的控件都平铺挂在 WidgetTree 下，路径不带父控件名。

## 改父类

```python
unreal.BlueprintEditorLibrary.reparent_blueprint(bp, unreal.load_class(None, '/Script/MyModule.MyBaseWidget'))
```

## 移动或改名资产

```python
ok = unreal.EditorAssetLibrary.rename_asset(src, dst)   # 自动修引用
```

- 批量移动与引用检查用 `exec --action asset_move check/move/redirectors`。
- 引用方会被编辑器自动 P4 签出，期间编辑器可能无响应 1~3 分钟。执行时加 `--timeout 300`；即使返回 `Timeout` 也**不要重发**，用 `exec "print(1)"` 探测恢复后核对结果。
- 改名后逐个 `save_asset` 引用方（`asset_move move --save-referencers`）。
- P4 侧保留历史：对新文件 `p4 revert -k`，再 `p4 move -k -c <CL> <old> <new>`。
- 旧路径会残留 ObjectRedirector，确认无引用后 `p4 revert` + `p4 delete`；`delete_asset` 不会真删磁盘文件，且包仍被编辑器（打开的编辑器、已加载的类型等）占用时会报 `... is in use` 删不掉，关编辑器后再删。
