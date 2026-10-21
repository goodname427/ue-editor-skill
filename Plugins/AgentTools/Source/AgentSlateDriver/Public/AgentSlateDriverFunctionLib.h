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
 * 只提供原子能力：查询控件，以及排在一条时间线上的输入步骤（按下、抬起、移动、滚轮、聚焦、全选、字符、等待）。
 * 点击、长按、拖动、文本输入等组合由 Skill 的 Python 模块 ue_input 拼装，不在这里重复实现。
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

	/** 坐标处最上层控件（JSON 节点），没有窗口时为 null */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString WidgetAt(float X, float Y);

	/**
	 * 获取当前键盘焦点控件
	 * @return JSON对象（控件节点信息，含 owner），无焦点时为 null
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString GetKeyboardFocus();

	/** 输入步骤的结果（保留最近 64 个）；pending=true 表示还没执行完 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString GetInputResult(int32 RequestId);

	// ==================== 输入步骤 ====================
	// 每个调用排一步到同一条时间线：前一步完成才执行下一步，相邻两步至少隔一帧，某步失败时取消其后所有步骤。
	// 返回 JSON 含 success（只表示已排队）与 request_id；执行结果用 GetInputResult 读。
	// 按住的键/鼠标键记在本库内，到 MaxHoldSeconds 自动抬起（0 为不限），防止调用方中途失败把键一直按着。

	/** 把键盘焦点设到命中的控件；它本身不接受焦点时取其中第一个可编辑控件。不经过点击路由 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString FocusWidget(const FString& Locator, const FString& WindowFilter, int32 MatchIndex = 0);

	/** 全选当前键盘焦点所在输入框的文字；焦点不是输入框时判失败 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString SelectAllText();

	/** 向当前键盘焦点逐字发送字符事件（可含中文）；只追加，不清空旧内容 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString TypeText(const FString& Text);

	/** 按下键盘/手柄键并保持，直到 KeyUp / ReleaseAllInput；普通退格额外发字符码 8。结果含 handled */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString KeyDown(const FString& KeyName, bool bCtrl = false, bool bShift = false, bool bAlt = false, float MaxHoldSeconds = 30.f);

	/** 抬起经 KeyDown 按住的键；没按住时判失败 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString KeyUp(const FString& KeyName);

	/** 同步发送一个手柄 Axis1D 事件；DeviceId=-1 使用默认映射，保持/配对/归零由 lib 组合 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString AnalogInput(const FString& KeyName, float Value, int32 DeviceId = -1);

	/** 对标 Slate 的平台/虚拟光标选择；返回切换前位置和平台光标类型，生命周期由 lib 管理 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString UsePlatformCursorForCursorUser(bool bUsePlatformCursor);

	/** 对标 Slate 光标位置接口；虚拟光标模式下不移动系统光标 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString SetCursorPosition(float X, float Y);

	/** 对标 SlateUser 光标可见性接口 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString SetCursorVisibility(bool bVisible);

	/**
	 * 先把指针移到坐标处，再按下鼠标键并保持，直到 MouseUp / ReleaseAllInput
	 * @param bDoubleClick 以双击事件代替按下（双击 = 按下、抬起、双击按下、抬起）
	 * @param CheckLocator 非空时执行前校验：落点最上层控件须是该控件或其子节点、且控件可用，否则判失败、不发按下
	 * @return 排队时另含 pos, hit；校验模式另含 match_count, target。结果含执行时的 hit
	 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString MouseDown(float X, float Y, const FString& Button = TEXT("Left"), bool bDoubleClick = false, const FString& CheckLocator = TEXT(""), const FString& WindowFilter = TEXT(""), int32 MatchIndex = 0, float MaxHoldSeconds = 30.f);

	/** 在当前指针位置抬起经 MouseDown 按住的鼠标键；没按住时判失败。结果含 pos, hit */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString MouseUp(const FString& Button = TEXT("Left"));

	/** 指针从当前位置分 Frames 帧线性移到坐标处；有键按住时就是拖动。结果含 pos, hit, dragging */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString MouseMove(float X, float Y, int32 Frames = 1);

	/** 在坐标处滚一次滚轮（正数向上）。结果含 handled：事件路径上有没有控件处理，不代表内容真的动了 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString MouseWheel(float X, float Y, float Delta);

	/** 时间线上等待：至少 Seconds 秒且至少 Frames 帧 */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString WaitInput(float Seconds = 0.f, int32 Frames = 0);

	/** 不排队，下一帧就取消时间线上所有未完成的步骤，并抬起本库按住的全部键；结果含 released */
	UFUNCTION(BlueprintCallable, Category = "AgentTools|SlateDriver")
	static FString ReleaseAllInput();
};
