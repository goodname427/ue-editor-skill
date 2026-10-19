// Fill out your copyright notice in the Description page of Project Settings.

#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AgentWidgetBlueprintInfoFunctionLib.generated.h"

class UWidgetBlueprint;
class UWidget;
class UWidgetTree;
class UWidgetAnimation;
class UEdGraph;
class UEdGraphNode;
class UEdGraphPin;

/**
 * Widget蓝图信息读取工具库
 * 提供一系列静态函数用于读取Widget蓝图的完整信息，
 * 包括WidgetTree层级、Widget属性、动画、绑定、函数列表等。
 * 主要供Agent通过Python Remote Execution调用，用于UI开发辅助。
 */
UCLASS()
class UAgentWidgetBlueprintInfoFunctionLib : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:

	// ==================== Widget蓝图基础信息 ====================

	/**
	 * 获取Widget蓝图的基础信息（名称、父类、路径等）
	 * @param AssetPath Widget蓝图资产路径，如 /Game/UI/WBP_Main
	 * @return JSON格式的基础信息字符串
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetBlueprintInfo(const FString& AssetPath);

	// ==================== WidgetTree 层级结构 ====================

	/**
	 * 获取Widget蓝图的完整WidgetTree层级结构
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON格式的树形结构字符串，包含每个Widget的名称、类型、父子关系
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetTreeHierarchy(const FString& AssetPath);

	/**
	 * 获取WidgetTree中所有Widget的扁平列表
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，每个元素包含Widget名称和类型
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetAllWidgetsFlat(const FString& AssetPath);

	// ==================== 单个Widget详细信息 ====================

	/**
	 * 获取WidgetTree中指定Widget的详细属性信息
	 * @param AssetPath Widget蓝图资产路径
	 * @param WidgetName Widget名称
	 * @return JSON格式的Widget属性信息（Visibility、Slot、RenderTransform等）
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetDetailInfo(const FString& AssetPath, const FString& WidgetName);

	/**
	 * 获取指定Widget的Slot（布局槽）信息
	 * @param AssetPath Widget蓝图资产路径
	 * @param WidgetName Widget名称
	 * @return JSON格式的Slot信息（Anchors、Offset、Alignment、SizeToContent等）
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetSlotInfo(const FString& AssetPath, const FString& WidgetName);

	// ==================== 变量与属性 ====================

	/**
	 * 获取Widget蓝图中声明的所有变量（蓝图变量）
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，每个元素包含变量名、类型、是否可编辑等
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetBlueprintVariables(const FString& AssetPath);

	/**
	 * 获取Widget蓝图中所有绑定到Widget的变量（即WidgetTree中被标记为变量的Widget）
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，每个元素包含变量名和Widget类型
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetVariables(const FString& AssetPath);

	// ==================== 动画信息 ====================

	/**
	 * 获取Widget蓝图中所有动画的列表
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，每个元素包含动画名称、时长、是否循环等
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetAnimations(const FString& AssetPath);

	/**
	 * 获取指定动画的详细信息（绑定的Widget、Track信息等）
	 * @param AssetPath Widget蓝图资产路径
	 * @param AnimationName 动画名称
	 * @return JSON格式的动画详细信息
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetAnimationDetail(const FString& AssetPath, const FString& AnimationName);

	// ==================== 函数与事件 ====================

	/**
	 * 获取Widget蓝图中定义的所有函数（蓝图函数图表）
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，每个元素包含函数名、输入参数、输出参数
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetBlueprintFunctions(const FString& AssetPath);

	/**
	 * 获取Widget蓝图中定义的所有事件（Event Graph中的自定义事件）
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，每个元素包含事件名称
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetBlueprintEvents(const FString& AssetPath);

	// ==================== 属性绑定 ====================

	/**
	 * 获取Widget蓝图中所有的属性绑定信息
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，每个元素包含绑定的Widget名、属性名、绑定函数名
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetPropertyBindings(const FString& AssetPath);

	// ==================== NamedSlot ====================

	/**
	 * 获取Widget蓝图中所有的NamedSlot信息
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，包含所有NamedSlot的名称和内容
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetNamedSlots(const FString& AssetPath);

	// ==================== 蓝图图表与节点 ====================

	/**
	 * 获取Widget蓝图中所有图表（EventGraph、FunctionGraph、MacroGraph等）的列表
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，每个元素包含图表名称、类型、节点数量
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetAllGraphs(const FString& AssetPath);

	/**
	 * 获取指定图表中所有节点的信息
	 * @param AssetPath Widget蓝图资产路径
	 * @param GraphName 图表名称（从GetAllGraphs获取）
	 * @return JSON数组，每个元素包含节点类型、标题、注释、引脚信息
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetGraphNodes(const FString& AssetPath, const FString& GraphName);

	/**
	 * 获取指定图表中指定节点的详细信息（含所有引脚及连接）
	 * @param AssetPath Widget蓝图资产路径
	 * @param GraphName 图表名称
	 * @param NodeGuid 节点GUID（从GetGraphNodes获取）
	 * @return JSON对象，包含节点完整信息及引脚连接关系
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetNodeDetail(const FString& AssetPath, const FString& GraphName, const FString& NodeGuid);

	// ==================== 批量查询 ====================

	/**
	 * 获取指定目录下所有Widget蓝图的路径列表
	 * @param DirectoryPath 目录路径，如 /Game/UI
	 * @param bRecursive 是否递归子目录
	 * @return JSON数组，包含所有Widget蓝图的资产路径
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetAllWidgetBlueprintsInDirectory(const FString& DirectoryPath, bool bRecursive = true);

	/**
	 * 获取Widget蓝图的继承链信息
	 * @param AssetPath Widget蓝图资产路径
	 * @return JSON数组，从当前类到UUserWidget的继承链
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetWidgetBlueprintInheritanceChain(const FString& AssetPath);

	// ==================== ChildWidget 重命名 ====================

	/**
	 * 重命名WidgetTree中指定的ChildWidget
	 * @param AssetPath Widget蓝图资产路径
	 * @param OldWidgetName 当前Widget名称
	 * @param NewWidgetName 新的Widget名称
	 * @return JSON格式的操作结果，包含 success 和 message 字段
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString RenameChildWidget(const FString& AssetPath, const FString& OldWidgetName, const FString& NewWidgetName);

	// ==================== ChildWidget 属性编辑 ====================

	/**
	 * 设置WidgetTree中指定Widget的单个属性值
	 * @param AssetPath Widget蓝图资产路径
	 * @param WidgetName Widget名称
	 * @param PropertyName 属性名称（如 "Visibility"、"bIsEnabled"）
	 * @param PropertyValue 属性值（JSON格式字符串）
	 * @return JSON格式的操作结果，包含 success 和 message 字段
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString SetWidgetProperty(const FString& AssetPath, const FString& WidgetName, const FString& PropertyName, const FString& PropertyValue);

	/**
	 * 批量设置WidgetTree中指定Widget的多个属性值
	 * @param AssetPath Widget蓝图资产路径
	 * @param WidgetName Widget名称
	 * @param PropertiesJson JSON对象字符串，key为属性名，value为属性值
	 * @return JSON格式的操作结果，包含 success、message 和每个属性的设置结果
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString SetWidgetProperties(const FString& AssetPath, const FString& WidgetName, const FString& PropertiesJson);

	/**
	 * 设置WidgetTree中指定Widget的Slot（布局槽）属性
	 * @param AssetPath Widget蓝图资产路径
	 * @param WidgetName Widget名称
	 * @param SlotPropertiesJson JSON对象字符串，包含Slot属性（如 Anchors、Offsets、Alignment等）
	 * @return JSON格式的操作结果，包含 success 和 message 字段
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString SetWidgetSlotProperties(const FString& AssetPath, const FString& WidgetName, const FString& SlotPropertiesJson);

	// ==================== 蓝图函数编辑 ====================

	/**
	 * 在Widget蓝图中新增一个蓝图函数（空函数图表）
	 * @param AssetPath Widget蓝图资产路径
	 * @param FunctionName 新函数名称
	 * @return JSON格式的操作结果，包含 success、message 和新建图表的名称
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString AddBlueprintFunction(const FString& AssetPath, const FString& FunctionName);

	/**
	 * 删除Widget蓝图中指定的蓝图函数图表
	 * @param AssetPath Widget蓝图资产路径
	 * @param FunctionName 要删除的函数名称
	 * @return JSON格式的操作结果，包含 success 和 message 字段
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString RemoveBlueprintFunction(const FString& AssetPath, const FString& FunctionName);

	/**
	 * 重命名Widget蓝图中指定的蓝图函数
	 * @param AssetPath Widget蓝图资产路径
	 * @param OldFunctionName 当前函数名称
	 * @param NewFunctionName 新的函数名称
	 * @return JSON格式的操作结果，包含 success 和 message 字段
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString RenameBlueprintFunction(const FString& AssetPath, const FString& OldFunctionName, const FString& NewFunctionName);

	/**
	 * 为Widget蓝图中指定函数添加输入参数
	 * @param AssetPath Widget蓝图资产路径
	 * @param FunctionName 函数名称
	 * @param ParamName 参数名称
	 * @param ParamType 参数类型（如 "bool"、"int"、"float"、"string"、"object"）
	 * @return JSON格式的操作结果，包含 success 和 message 字段
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString AddFunctionInputParam(const FString& AssetPath, const FString& FunctionName, const FString& ParamName, const FString& ParamType);

	/**
	 * 为Widget蓝图中指定函数添加输出参数
	 * @param AssetPath Widget蓝图资产路径
	 * @param FunctionName 函数名称
	 * @param ParamName 参数名称
	 * @param ParamType 参数类型（如 "bool"、"int"、"float"、"string"、"object"）
	 * @return JSON格式的操作结果，包含 success 和 message 字段
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString AddFunctionOutputParam(const FString& AssetPath, const FString& FunctionName, const FString& ParamName, const FString& ParamType);

	/**
	 * 设置Widget蓝图中指定函数的描述（Tooltip）
	 * @param AssetPath Widget蓝图资产路径
	 * @param FunctionName 函数名称
	 * @param Description 函数描述文本
	 * @return JSON格式的操作结果，包含 success 和 message 字段
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintEdit")
	static FString SetFunctionDescription(const FString& AssetPath, const FString& FunctionName, const FString& Description);

	// ==================== 蓝图函数阅读 ====================

	/**
	 * 获取Widget蓝图中指定函数的完整信息（参数列表、描述、节点数量等）
	 * @param AssetPath Widget蓝图资产路径
	 * @param FunctionName 函数名称
	 * @return JSON格式的函数详细信息，包含输入输出参数、描述、图表节点数
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetBlueprintFunctionDetail(const FString& AssetPath, const FString& FunctionName);

	/**
	 * 获取Widget蓝图中指定函数图表的所有节点及连接关系（完整调用链）
	 * @param AssetPath Widget蓝图资产路径
	 * @param FunctionName 函数名称
	 * @return JSON格式的节点列表，每个节点包含类型、标题、引脚及连接信息
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetFunctionGraphNodes(const FString& AssetPath, const FString& FunctionName);

	/**
	 * 获取Widget蓝图中指定函数的输入输出参数列表
	 * @param AssetPath Widget蓝图资产路径
	 * @param FunctionName 函数名称
	 * @return JSON对象，包含 inputs 和 outputs 两个数组，每个元素含参数名和类型
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString GetFunctionParams(const FString& AssetPath, const FString& FunctionName);

	/**
	 * 搜索Widget蓝图中所有函数，返回名称匹配关键词的函数列表
	 * @param AssetPath Widget蓝图资产路径
	 * @param Keyword 搜索关键词（大小写不敏感）
	 * @return JSON数组，每个元素包含函数名、参数数量、描述
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|WidgetBlueprintInfo")
	static FString SearchBlueprintFunctions(const FString& AssetPath, const FString& Keyword);

private:
	static UWidgetBlueprint* LoadWidgetBlueprint(const FString& AssetPath);
	static UWidget* FindWidgetInTree(UWidgetBlueprint* WidgetBP, const FString& WidgetName);
	static FString WidgetToJsonObject(UWidget* Widget, bool bDetailed = false);
	static FString BuildWidgetTreeJson(UWidget* Widget, UWidgetTree* WidgetTree);
	static FString GetSlotInfoJson(UWidget* Widget);
	static UEdGraph* FindGraphByName(UWidgetBlueprint* WidgetBP, const FString& GraphName);
	static FString PinToJson(UEdGraphPin* Pin, bool bIncludeLinks = false);
	static FString NodeToJson(UEdGraphNode* Node, bool bDetailed = false);
};
