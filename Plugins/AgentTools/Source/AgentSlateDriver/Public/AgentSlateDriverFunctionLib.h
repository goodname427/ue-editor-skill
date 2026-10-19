#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AgentSlateDriverFunctionLib.generated.h"

/**
 * Slate 层编辑器操控工具库
 * 读取所有可见窗口的 Slate 控件树（含编辑器面板与 PIE 视口内的 UMG），并合成鼠标/键盘输入，
 * 让 Agent 像人一样操作编辑器。主要供 Agent 通过 Python Remote Execution 调用。
 *
 * 坐标均为桌面绝对像素（与 Win32 窗口坐标一致）。
 * Locator 语法：
 *   - 纯字符串：按 UMG 名称、Tag、文本或输入框提示文字精确匹配
 *   - key=value：精确匹配（不区分大小写），key 取 name / tag / text / hint / type / class；type 也匹配模板包装内的类型名
 *   - key~=value：包含匹配
 *   - 多个条件用 ; 连接，需全部满足，如 type=SButton;text~=保存
 * 输入类接口在下一帧执行（返回时尚未生效），避免模态对话框阻塞本次 Python 调用。
 */
UCLASS()
class UAgentSlateDriverFunctionLib : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:

	// ==================== 控件树读取 ====================

	/**
	 * 列出所有可见窗口（从后往前排序）
	 * @return JSON数组，每个元素包含 title, rect, active
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString ListWindows();

	/** 本进程已排布的 PIE 视口；JSON 数组包含 world, instance, window, rect */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString ListPIEViewports();

	/**
	 * 导出可见窗口的 Slate 控件树
	 * @param WindowFilter 窗口标题子串（不区分大小写），为空则导出所有可见窗口
	 * @param RootLocator 只导出命中该 Locator 的子树，为空则导出整棵树
	 * @param MaxDepth 最大输出深度，0 为不限
	 * @param bIncludeHidden 是否包含 Collapsed/Hidden 控件
	 * @param bCompact 精简模式：只输出有名称/Tag/文本或可交互/可聚焦的控件，深度按已输出的祖先计算
	 * @param MaxNodes 最多输出节点数，超出后截断
	 * @param RootMatchIndex 根 Locator 命中多个时只导出第几个（从 0 开始），-1 为全部
	 * @return JSON对象，包含 windows（每个窗口含 title, rect, nodes）、node_count、truncated；指定根时另含 root_match_count
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString DumpSlateTree(const FString& WindowFilter, const FString& RootLocator, int32 MaxDepth = 0, bool bIncludeHidden = false, bool bCompact = true, int32 MaxNodes = 3000, int32 RootMatchIndex = -1);

	/**
	 * 查找命中 Locator 的可见控件
	 * @param Locator 控件定位串
	 * @param WindowFilter 窗口标题子串，为空则在所有可见窗口中查找
	 * @param bIncludeHidden 查询隐藏/未排布的已有节点；返回 query_only、geometry_valid、hidden_by
	 * @return JSON数组；隐藏模式的下标与坐标不能用于普通点击
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString FindWidgets(const FString& Locator, const FString& WindowFilter, bool bIncludeHidden = false);

	// ==================== 键盘焦点 ====================

	/**
	 * 获取当前键盘焦点控件
	 * @return JSON对象（控件节点信息，含 owner），无焦点时为 null
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString GetKeyboardFocus();

	/**
	 * 把键盘焦点直接设到命中 Locator 的控件（下一帧执行，与后续输入按顺序排队）
	 * 不经过点击路由，编辑器窗口不在前台时也可靠；目标须支持键盘焦点（如 SEditableText）
	 * @return JSON对象，包含 success, match_count, target
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString FocusWidget(const FString& Locator, const FString& WindowFilter, int32 MatchIndex = 0);

	// ==================== 鼠标输入 ====================

	/**
	 * 在桌面坐标处点击
	 * @param Button Left / Right / Middle
	 * @param bDoubleClick 是否双击
	 * @return JSON对象，包含 success, pos, hit（坐标下最上层控件）
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString ClickAt(float X, float Y, const FString& Button = TEXT("Left"), bool bDoubleClick = false, const FString& ExpectHit = TEXT(""));

	/**
	 * 点击命中 Locator 的控件中心
	 * @param MatchIndex 多个命中时取第几个（从 0 开始）
	 * @param ExpectHit 非空时须唯一匹配可见控件；实际发送前校验命中/捕获路径包含该控件
	 * @return JSON对象，包含 success, match_count, target, pos, hit；断言模式另含 request_id
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString ClickWidget(const FString& Locator, const FString& WindowFilter, int32 MatchIndex = 0, const FString& Button = TEXT("Left"), bool bDoubleClick = false, const FString& ExpectHit = TEXT(""));

	/** 最近 64 次断言点击结果；pending=true 未执行，false 时包含 success 与 clicks_sent */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString GetInputResult(int32 RequestId);

	/**
	 * 在桌面坐标处滚动滚轮
	 * @param Delta 滚动量，正数向上
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString ScrollAt(float X, float Y, float Delta);

	// ==================== 键盘输入 ====================

	/**
	 * 向当前键盘焦点发送一次按键（下一帧按下，再过两帧抬起）
	 * @param KeyName FKey 名称，如 Enter / Escape / Tab / Delete / F5 / S / Up
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString PressKey(const FString& KeyName, bool bCtrl = false, bool bShift = false, bool bAlt = false);

	/**
	 * 向当前键盘焦点逐字输入文本（字符事件，可含中文）
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString TypeText(const FString& Text);
};
