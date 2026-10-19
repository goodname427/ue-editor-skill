# Widget 蓝图写操作流程

> 本文档收录通过脚本修改 Widget 蓝图的已验证流程。读取类接口见 [widget_blueprint_info.md](widget_blueprint_info.md)。
> 多行脚本写成 `.py` 后用 `ue_cli.py exec --file <path>` 执行。

## 通用约定

- **改前签出**：`.uasset` 在版本库里通常是独占签出，改前先签出（P4：`p4 edit -c <CL> <file>`）；只读文件 `save_asset` 会失败或弹窗。
- **改前先读**：用 `get_all_widgets_flat(path)` 确认控件名，再按名字操作。
- **改后收尾**：`BlueprintEditorLibrary.compile_blueprint(bp)` → `EditorAssetLibrary.save_asset(path, only_if_is_dirty=False)`；脚本外可直接 `ue_cli.py exec --lib wbp_edit save <路径>...`。
- **TS 类型（仅 Puerts 工程）**：修改已有蓝图的变量后，保存时编辑器会自动刷新 `ue_bp.d.ts`；新增蓝图或新增控件需执行 `Puerts.Gen PATH=<蓝图所在目录>` 增量生成（`exec --lib wbp_edit save ... --gen` 会顺带执行）。非 Puerts 工程加 `--no-gen`。

## 优先用 wbp_edit Lib

改名、勾变量、加控件、换控件、移除控件用 `exec --lib wbp_edit ...`，用法见脚本 docstring；`add` / `replace` / `remove` 默认编译保存并执行 `Puerts.Gen`（`--no-gen` / `--no-save` 可关）：

```bash
exec --lib wbp_edit list  /Game/UI/XXX/WBP_Foo
exec --lib wbp_edit rename /Game/UI/XXX/WBP_Foo ScrollBox_173 ScrollView_List
exec --lib wbp_edit set   /Game/UI/XXX/WBP_Foo ScrollView_List bIsVariable=True Visibility=Collapsed
exec --lib wbp_edit add   /Game/UI/XXX/WBP_Foo CanvasPanel_Root Btn_Confirm Button --text=确定 --copy=Btn_Cancel --anchor=0,0,0,0 --offset=100,200,160,48 --align=0.5,0.5
exec --lib wbp_edit replace /Game/UI/XXX/WBP_Foo BP_Child /Game/UI/XXX/WBP_Child2   # 默认沿用旧控件的槽位与变量状态
exec --lib wbp_edit remove /Game/UI/XXX/WBP_Foo Btn_Confirm
```

Lib 覆盖不到的场景（复制属性以外的样式改造、批量建树、改父类等）按下面手写脚本，用到的手法与接口相同。

## 取 WidgetTree 与控件对象

```python
import unreal
P = '/Game/UI/XXX/WBP_Foo'          # 包路径
N = 'WBP_Foo'                       # 资产名
bp = unreal.EditorAssetLibrary.load_asset(P)
tree = unreal.find_object(None, P + '.' + N + ':WidgetTree')
panel = unreal.find_object(None, P + '.' + N + ':WidgetTree.CanvasPanel_Root')
```

- 必须先 `load_asset`，否则 `find_object` 返回 `None`。
- 控件都挂在 WidgetTree 下平铺成子对象：任意层级的控件路径都是 `...:WidgetTree.<控件名>`，不用带父控件名。

## 改名并勾选"是变量"

```python
lib = unreal.AgentWidgetBlueprintInfoFunctionLib
print(lib.rename_child_widget(P, 'ScrollBox_173', 'ScrollView_List'))
print(lib.set_widget_property(P, 'ScrollView_List', 'bIsVariable', 'True'))
```

- `set_widget_property` 的值按 UE 文本格式给（`True`、`Collapsed`），属性名是 C++ 属性名；批量设置用 `set_widget_properties`。
- 该接口不检查 `ImportText` 是否真的写进去，改完用 `get_all_widgets_flat` 的 `is_variable` 或 `get_widget_detail_info` 回读。

## 新增控件

```python
b = unreal.new_object(unreal.Button, tree, 'Btn_Confirm')
slot = panel.add_child_to_canvas(b)                     # CanvasPanel
# slot = hbox.add_child_to_horizontal_box(b)            # HorizontalBox，返回的 slot 设 padding/size/alignment
# slot = vbox.add_child_to_vertical_box(b)              # VerticalBox
layout = unreal.AnchorData()
layout.anchors = unreal.Anchors(minimum=unreal.Vector2D(0, 0), maximum=unreal.Vector2D(0, 0))
layout.offsets = unreal.Margin(0, 150, 1000, 600)
layout.alignment = unreal.Vector2D(0, 0)
slot.set_layout(layout)
lib.set_widget_property(P, 'Btn_Confirm', 'bIsVariable', 'True')
```

- 子蓝图实例：类用 `unreal.EditorAssetLibrary.load_blueprint_class('/Game/.../WBP_Child')` 或 `unreal.load_class(None, '/Game/.../WBP_Child.WBP_Child_C')`。
- 样式可从同树已有控件复制：`new.set_editor_property('widget_style', old.get_editor_property('widget_style'))`；文字控件复制 `font`；ComboBoxString 还要 `item_style` / `scroll_bar_style` / `content_padding` / `foreground_color` / `max_list_height`。
- 没有 insert/replace API，新控件只能追加到父面板末尾；按钮等 Content 控件用 `add_child` 挂文字子控件。
- 回读槽位用 `get_widget_slot_info(path, name)`；CanvasPanel 槽位在 Python 侧读 `slot.get_layout()`，横/纵/Overlay 槽位读 `padding` / `size` / `horizontal_alignment` / `vertical_alignment`。

## 删除或替换控件

```python
transient = unreal.find_object(None, '/Engine/Transient')
old = unreal.find_object(None, P + '.' + N + ':WidgetTree.BP_Child')
panel.remove_child(old)
old.rename('BP_Child_Removed', transient)               # 腾出名字，否则同名 new_object 冲突
new = unreal.new_object(new_cls, tree, 'BP_Child')
panel.add_child_to_canvas(new).set_layout(layout)
```

## 改父类

```python
unreal.BlueprintEditorLibrary.reparent_blueprint(bp, unreal.load_class(None, '/Script/MyModule.MyBaseWidget'))
```

## 移动或改名资产

```python
ok = unreal.EditorAssetLibrary.rename_asset(src, dst)   # 自动修引用
```

- 批量移动与引用检查用 `exec --lib asset_move check/move/redirectors`。
- 引用方会被编辑器自动 P4 签出，期间编辑器可能无响应 1~3 分钟。执行时加 `--timeout 300`；即使返回 `Timeout` 也**不要重发**，用 `exec "print(1)"` 探测恢复后核对结果。
- 改名后逐个 `save_asset` 引用方（`asset_move move --save-referencers`）。
- P4 侧保留历史：对新文件 `p4 revert -k`，再 `p4 move -k -c <CL> <old> <new>`。
- 旧路径会残留 ObjectRedirector，确认无引用后 `p4 revert` + `p4 delete`；`delete_asset` 不会真删磁盘文件，且包仍被编辑器（打开的编辑器、已加载的类型等）占用时会报 `... is in use` 删不掉，关编辑器后再删。
- 不同目录下的同名蓝图会在 `ue_bp.d.ts` 中重复声明（tsc 只认第一个），移动时改成不冲突的名字。
