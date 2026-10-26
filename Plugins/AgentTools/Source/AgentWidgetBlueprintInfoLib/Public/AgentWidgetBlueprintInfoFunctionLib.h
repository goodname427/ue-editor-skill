// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "EdGraph/EdGraphPin.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AgentWidgetBlueprintInfoFunctionLib.generated.h"

class UWidgetBlueprint;
class UWidget;
class UEdGraph;
class UEdGraphNode;
class UEdGraphPin;

/**
 * Widget 蓝图读写工具库：只提供 UE Python 访问不到的原子能力。
 * 控件树、bIsVariable、成员变量、函数/事件图、动画、属性绑定、NamedSlot 绑定都不对 Python 公开，所以放在这里。
 * 树形结构、变量控件、概览、事件列表、函数搜索、批量设属性等组合，由 Skill 的编辑器侧模块 ue_wbp 拼装；
 * 加/删/改名函数、按目录列 WBP、继承链用引擎自带的 BlueprintEditorLibrary / AssetRegistry，不在这里重复。
 * 所有函数返回 JSON 字符串；失败统一为 {"success":false,"message":...}。
 */
UCLASS()
class UAgentWidgetBlueprintInfoFunctionLib : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:

	// ==================== 读取 ====================

	/**
	 * WidgetTree 中所有控件的平铺列表（遍历顺序），父控件为空的是根
	 * @return JSON数组，每项含 name, type, is_variable, visibility, parent, child_index
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgets(const FString& AssetPath);

	/**
	 * 导出控件（bSlot=true 时为它所在的插槽）的全部可编辑 / 蓝图可见属性，值为 UE 文本格式
	 * @return JSON对象，含 name, type（控件类或插槽类）, properties:[{name, type, value}]
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetProperties(const FString& AssetPath, const FString& WidgetName, bool bSlot = false);

	/** "我的蓝图"里声明的成员变量：name, type, sub_type, is_array/is_set/is_map, instance_editable, blueprint_read_only, category, default_value */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetBlueprintVariables(const FString& AssetPath);

	/** 全部动画：name, duration, bindings:[{widget_name（绑定的控件）, slot_widget_name, name（轨道显示名）, tracks:[{track_name, track_type}]}], master_tracks:[...] */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetAnimations(const FString& AssetPath);

	/** 属性绑定：widget_name, property_name, function_name, source_property, kind */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetPropertyBindings(const FString& AssetPath);

	/** 父类 NamedSlot 在本蓝图里填入的内容（WidgetTree.NamedSlotBindings）：name, content_name, content_type。本蓝图自己的 NamedSlot 控件从 GetWidgets 的 type 判断 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetNamedSlotBindings(const FString& AssetPath);

	/** 所有图表：name, type（Function/EventGraph/Macro/DelegateSignature/Other）, node_count */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetAllGraphs(const FString& AssetPath);

	/**
	 * 图表中的全部节点
	 * @param bDetailed false 时每个节点只给引脚数；true 时给全部引脚及连线
	 * @return JSON数组，每项含 node_class, title, compact_title, guid, pos_x, pos_y, enabled[, comment][, function_name]；事件节点的 function_name 是事件名
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetGraphNodes(const FString& AssetPath, const FString& GraphName, bool bDetailed = false);

	/** 全部蓝图函数的签名：name, description, node_count, inputs:[{name, type, sub_type}], outputs:[...] */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetBlueprintFunctions(const FString& AssetPath);

	// ==================== 写入 ====================

	/**
	 * 改控件名，并同步变量引用、属性绑定、动画绑定、导航绑定（与 WBP 设计器里改名的处理一致，不需要打开编辑器）
	 * @return JSON对象，含 success, message
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString RenameChildWidget(const FString& AssetPath, const FString& OldWidgetName, const FString& NewWidgetName);

	/**
	 * 用 UE 文本格式设置控件（bSlot=true 时为它的插槽）的一个属性，走 PreEditChange/PostEditChangeProperty
	 * 文本解析失败时判失败，不会静默写成默认值
	 * @return JSON对象，含 success, message, value（写入后回读的文本）
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString SetWidgetProperty(const FString& AssetPath, const FString& WidgetName, const FString& PropertyName, const FString& PropertyValue, bool bSlot = false);

	/** 对标 UPanelWidget::ShiftChild，移动同父控件下的插槽，保留插槽实例与属性 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString ShiftChild(const FString& AssetPath, const FString& WidgetName, int32 Index);

	/**
	 * 给蓝图函数加一个参数
	 * @param PinType 用 BlueprintEditorLibrary 的 GetBasicTypeByName / GetObjectReferenceType / GetStructType 等构造
	 * @param bOutput false 加输入参数（入口节点），true 加返回值（结果节点，没有时自动创建）
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString AddFunctionParam(const FString& AssetPath, const FString& FunctionName, const FString& ParamName, const FEdGraphPinType& PinType, bool bOutput = false);

	/** 设置蓝图函数的描述（入口节点 Tooltip） */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString SetFunctionDescription(const FString& AssetPath, const FString& FunctionName, const FString& Description);
};
