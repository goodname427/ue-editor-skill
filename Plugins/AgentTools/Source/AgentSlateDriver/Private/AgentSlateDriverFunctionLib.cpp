#include "AgentSlateDriverFunctionLib.h"

#include "AgentJson.h"
#include "Containers/Ticker.h"
#include "CoreGlobals.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "Framework/Application/SlateUser.h"
#include "InputCoreTypes.h"
#include "Layout/ArrangedChildren.h"
#include "Layout/WidgetPath.h"
#include "Misc/ScopeExit.h"
#include "Types/ReflectionMetadata.h"
#include "Widgets/SToolTip.h"
#include "Widgets/SViewport.h"
#include "Widgets/SWindow.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Input/SEditableText.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Input/SMultiLineEditableTextBox.h"
#include "Widgets/Text/SInlineEditableTextBlock.h"
#include "Widgets/Text/SRichTextBlock.h"
#include "Widgets/Text/STextBlock.h"

// ==================== JSON辅助 ====================

static FString SDRectJson(const FVector2D& Pos, const FVector2D& Size)
{
	return FString::Printf(TEXT("[%d,%d,%d,%d]"), FMath::RoundToInt(Pos.X), FMath::RoundToInt(Pos.Y), FMath::RoundToInt(Size.X), FMath::RoundToInt(Size.Y));
}

static FString SDPointJson(const FVector2D& Pos)
{
	return FString::Printf(TEXT("[%d,%d]"), FMath::RoundToInt(Pos.X), FMath::RoundToInt(Pos.Y));
}

static FString SDResult(bool bSuccess, const FString& Message, const TArray<FString>& ExtraFields = TArray<FString>())
{
	TArray<FString> Fields;
	Fields.Add(AgentJson::PairBool(TEXT("success"), bSuccess));
	if (!Message.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("message"), Message));
	}
	Fields.Append(ExtraFields);
	return AgentJson::Object(Fields);
}

// ==================== 控件信息 ====================

struct FSDWidgetInfo
{
	FString Type;
	FString Name;
	FString Class;
	FString Tag;
	FString Text;
	FString Hint;
	FString Label;
	bool bClickable = false;
	FVector2D Pos = FVector2D::ZeroVector;
	FVector2D Size = FVector2D::ZeroVector;
};

static FString SDGetWidgetText(const TSharedRef<SWidget>& Widget)
{
	static const FName Type_STextBlock(TEXT("STextBlock"));
	static const FName Type_SRichTextBlock(TEXT("SRichTextBlock"));
	static const FName Type_SEditableText(TEXT("SEditableText"));
	static const FName Type_SEditableTextBox(TEXT("SEditableTextBox"));
	static const FName Type_SMultiLineEditableTextBox(TEXT("SMultiLineEditableTextBox"));
	static const FName Type_SInlineEditableTextBlock(TEXT("SInlineEditableTextBlock"));
	static const FName Type_SDockTab(TEXT("SDockTab"));

	const FName Type = Widget->GetType();
	if (Type == Type_STextBlock)
	{
		return StaticCastSharedRef<STextBlock>(Widget)->GetText().ToString();
	}
	if (Type == Type_SRichTextBlock)
	{
		return StaticCastSharedRef<SRichTextBlock>(Widget)->GetText().ToString();
	}
	if (Type == Type_SEditableText)
	{
		return StaticCastSharedRef<SEditableText>(Widget)->GetText().ToString();
	}
	if (Type == Type_SEditableTextBox)
	{
		return StaticCastSharedRef<SEditableTextBox>(Widget)->GetText().ToString();
	}
	if (Type == Type_SMultiLineEditableTextBox)
	{
		return StaticCastSharedRef<SMultiLineEditableTextBox>(Widget)->GetText().ToString();
	}
	if (Type == Type_SInlineEditableTextBlock)
	{
		return StaticCastSharedRef<SInlineEditableTextBlock>(Widget)->GetText().ToString();
	}
	if (Type == Type_SDockTab)
	{
		return StaticCastSharedRef<SDockTab>(Widget)->GetTabLabel().ToString();
	}
	return FString();
}

// 输入框的提示文字（如 "Search Assets"），用于区分同类输入框
static FString SDGetWidgetHint(const TSharedRef<SWidget>& Widget)
{
	static const FName Type_SEditableText(TEXT("SEditableText"));
	static const FName Type_SEditableTextBox(TEXT("SEditableTextBox"));
	static const FName Type_SSearchBox(TEXT("SSearchBox"));

	const FName Type = Widget->GetType();
	if (Type == Type_SEditableText)
	{
		return StaticCastSharedRef<SEditableText>(Widget)->GetHintText().ToString();
	}
	if (Type == Type_SEditableTextBox || Type == Type_SSearchBox)
	{
		return StaticCastSharedRef<SEditableTextBox>(Widget)->GetHintText().ToString();
	}
	return FString();
}

// 按钮类控件：可交互，或已禁用但类型是按钮/勾选框（SButton 禁用后 IsInteractable 为 false，精简模式会丢掉）
static bool SDIsClickable(const TSharedRef<SWidget>& Widget, const FString& Type)
{
	return Widget->IsInteractable()
		|| (!Widget->IsEnabled() && (Type.Contains(TEXT("Button")) || Type.Contains(TEXT("CheckBox"))));
}

// 在子孙里找第一个处于折叠/隐藏状态的文字（工具栏纯图标按钮的名字就在这里，如 "Save Current Level"）
static FString SDFindHiddenLabel(const TSharedRef<SWidget>& Widget, int32 Depth, bool bHiddenPath)
{
	static const FName Type_STextBlock(TEXT("STextBlock"));

	if (Depth > 0)
	{
		bHiddenPath = bHiddenPath || !Widget->GetVisibility().IsVisible();
		if (bHiddenPath && Widget->GetType() == Type_STextBlock)
		{
			const FString Text = StaticCastSharedRef<STextBlock>(Widget)->GetText().ToString();
			if (!Text.IsEmpty())
			{
				return Text;
			}
		}
	}
	if (Depth >= 4)
	{
		return FString();
	}
	FChildren* Children = Widget->GetChildren();
	for (int32 Index = 0; Children && Index < Children->Num(); ++Index)
	{
		const FString Found = SDFindHiddenLabel(Children->GetChildAt(Index), Depth + 1, bHiddenPath);
		if (!Found.IsEmpty())
		{
			return Found;
		}
	}
	return FString();
}

static FString SDGetToolTipText(const TSharedRef<SWidget>& Widget)
{
	static const FName Type_SToolTip(TEXT("SToolTip"));

	const TSharedPtr<IToolTip> ToolTip = Widget->GetToolTip();
	if (!ToolTip.IsValid() || ToolTip->IsEmpty())
	{
		return FString();
	}
	const TSharedRef<SWidget> ToolTipWidget = ToolTip->AsWidget();
	if (ToolTipWidget->GetType() != Type_SToolTip)
	{
		return FString();
	}
	return StaticCastSharedRef<SToolTip>(ToolTipWidget)->GetTextTooltip().ToString();
}

// 无文字的按钮类控件的可读名称：先取折叠的文字子节点，没有再取 tooltip 第一行
static FString SDGetWidgetLabel(const TSharedRef<SWidget>& Widget)
{
	FString Label = SDFindHiddenLabel(Widget, 0, false);
	if (Label.IsEmpty())
	{
		Label = SDGetToolTipText(Widget);
	}
	int32 LineEnd = INDEX_NONE;
	if (Label.FindChar(TEXT('\n'), LineEnd))
	{
		Label.LeftInline(LineEnd);
	}
	Label.TrimStartAndEndInline();
	return Label.Len() > 60 ? Label.Left(60) + TEXT("...") : Label;
}

static FSDWidgetInfo SDMakeInfo(const FArrangedWidget& Arranged)
{
	FSDWidgetInfo Info;
	const TSharedRef<SWidget>& Widget = Arranged.Widget;
	Info.Type = Widget->GetTypeAsString();
	// UMG 控件通过 ReflectionMetaData 反查蓝图中的控件名与 UWidget 类
	if (const TSharedPtr<FReflectionMetaData> MetaData = Widget->GetMetaData<FReflectionMetaData>())
	{
		Info.Name = MetaData->Name.ToString();
		if (const UClass* WidgetClass = MetaData->Class.Get())
		{
			Info.Class = WidgetClass->GetName();
		}
	}
	const FName Tag = Widget->GetTag();
	if (!Tag.IsNone())
	{
		Info.Tag = Tag.ToString();
	}
	Info.Text = SDGetWidgetText(Widget);
	Info.Hint = SDGetWidgetHint(Widget);
	Info.bClickable = SDIsClickable(Widget, Info.Type);
	if (Info.Text.IsEmpty() && Info.bClickable)
	{
		Info.Label = SDGetWidgetLabel(Widget);
	}
	Info.Pos = Arranged.Geometry.GetAbsolutePosition();
	Info.Size = Arranged.Geometry.GetAbsoluteSize();
	return Info;
}

static FString SDFindOwnerName(TSharedPtr<SWidget> Widget)
{
	while (Widget.IsValid())
	{
		if (const TSharedPtr<FReflectionMetaData> MetaData = Widget->GetMetaData<FReflectionMetaData>())
		{
			return MetaData->Name.ToString();
		}
		Widget = Widget->GetParentWidget();
	}
	return FString();
}

static TArray<FString> SDNodeFields(const FSDWidgetInfo& Info, const TSharedRef<SWidget>& Widget)
{
	TArray<FString> Fields;
	Fields.Add(AgentJson::Pair(TEXT("type"), Info.Type));
	if (!Info.Name.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("name"), Info.Name));
	}
	if (!Info.Class.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("class"), Info.Class));
	}
	if (!Info.Tag.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("tag"), Info.Tag));
	}
	if (!Info.Text.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("text"), Info.Text.Len() > 80 ? Info.Text.Left(80) + TEXT("...") : Info.Text));
	}
	if (!Info.Hint.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("hint"), Info.Hint));
	}
	if (!Info.Label.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("label"), Info.Label));
	}
	Fields.Add(AgentJson::PairRaw(TEXT("rect"), SDRectJson(Info.Pos, Info.Size)));
	const EVisibility Visibility = Widget->GetVisibility();
	if (Visibility != EVisibility::Visible)
	{
		Fields.Add(AgentJson::Pair(TEXT("vis"), Visibility.ToString()));
	}
	if (!Widget->IsEnabled())
	{
		Fields.Add(AgentJson::PairBool(TEXT("enabled"), false));
	}
	if (Widget->IsInteractable())
	{
		Fields.Add(AgentJson::PairBool(TEXT("interactable"), true));
	}
	if (Widget->HasKeyboardFocus())
	{
		Fields.Add(AgentJson::PairBool(TEXT("focus"), true));
	}
	if (Widget->IsHovered())
	{
		Fields.Add(AgentJson::PairBool(TEXT("hover"), true));
	}
	return Fields;
}

static FString SDDescribeWidget(const TSharedPtr<SWidget>& Widget, const FGeometry& Geometry)
{
	if (!Widget.IsValid())
	{
		return TEXT("null");
	}
	const TSharedRef<SWidget> WidgetRef = Widget.ToSharedRef();
	TArray<FString> Fields = SDNodeFields(SDMakeInfo(FArrangedWidget(WidgetRef, Geometry)), WidgetRef);
	const FString OwnerName = SDFindOwnerName(Widget);
	if (!OwnerName.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("owner"), OwnerName));
	}
	return AgentJson::Object(Fields);
}

// ==================== Locator ====================

struct FSDLocatorCond
{
	FString Key;
	FString Value;
	bool bContains = false;
};

struct FSDLocator
{
	FString Plain;
	TArray<FSDLocatorCond> Conds;

	bool IsEmpty() const
	{
		return Plain.IsEmpty() && Conds.Num() == 0;
	}
};

static FSDLocator SDParseLocator(const FString& Locator)
{
	FSDLocator Result;
	const FString Trimmed = Locator.TrimStartAndEnd();
	if (Trimmed.IsEmpty())
	{
		return Result;
	}
	if (!Trimmed.Contains(TEXT("=")))
	{
		Result.Plain = Trimmed;
		return Result;
	}
	TArray<FString> Parts;
	Trimmed.ParseIntoArray(Parts, TEXT(";"), true);
	for (const FString& Part : Parts)
	{
		int32 EqualIndex = INDEX_NONE;
		if (!Part.FindChar(TEXT('='), EqualIndex))
		{
			continue;
		}
		FSDLocatorCond Cond;
		FString KeyPart = Part.Left(EqualIndex).TrimStartAndEnd();
		Cond.bContains = KeyPart.EndsWith(TEXT("~"));
		if (Cond.bContains)
		{
			KeyPart.LeftChopInline(1);
		}
		Cond.Key = KeyPart.TrimStartAndEnd().ToLower();
		Cond.Value = Part.Mid(EqualIndex + 1).TrimStartAndEnd();
		Result.Conds.Add(Cond);
	}
	return Result;
}

static bool SDMatchLocator(const FSDWidgetInfo& Info, const FSDLocator& Locator)
{
	if (!Locator.Plain.IsEmpty())
	{
		return Info.Name.Equals(Locator.Plain, ESearchCase::IgnoreCase)
			|| Info.Tag.Equals(Locator.Plain, ESearchCase::IgnoreCase)
			|| Info.Text.Equals(Locator.Plain, ESearchCase::IgnoreCase)
			|| Info.Hint.Equals(Locator.Plain, ESearchCase::IgnoreCase)
			|| Info.Label.Equals(Locator.Plain, ESearchCase::IgnoreCase);
	}
	if (Locator.Conds.Num() == 0)
	{
		return false;
	}
	for (const FSDLocatorCond& Cond : Locator.Conds)
	{
		const FString* Field = nullptr;
		if (Cond.Key == TEXT("name")) Field = &Info.Name;
		else if (Cond.Key == TEXT("tag")) Field = &Info.Tag;
		else if (Cond.Key == TEXT("text")) Field = &Info.Text;
		else if (Cond.Key == TEXT("hint")) Field = &Info.Hint;
		else if (Cond.Key == TEXT("label")) Field = &Info.Label;
		else if (Cond.Key == TEXT("type")) Field = &Info.Type;
		else if (Cond.Key == TEXT("class")) Field = &Info.Class;
		if (!Field)
		{
			return false;
		}
		// 类型名可能带模板包装（如 TToolCompatibleMixin<SDesignerView>），精确匹配时也认内层类型
		const bool bMatch = Cond.bContains
			? Field->Contains(Cond.Value, ESearchCase::IgnoreCase)
			: Field->Equals(Cond.Value, ESearchCase::IgnoreCase)
				|| (Cond.Key == TEXT("type") && Field->EndsWith(TEXT("<") + Cond.Value + TEXT(">"), ESearchCase::IgnoreCase));
		if (!bMatch)
		{
			return false;
		}
	}
	return true;
}

// ==================== 窗口与遍历 ====================

static void SDGetWindows(const FString& WindowFilter, TArray<TSharedRef<SWindow>>& OutWindows)
{
	TArray<TSharedRef<SWindow>> AllWindows;
	FSlateApplication::Get().GetAllVisibleWindowsOrdered(AllWindows);
	for (const TSharedRef<SWindow>& Window : AllWindows)
	{
		if (WindowFilter.IsEmpty() || Window->GetTitle().ToString().Contains(WindowFilter, ESearchCase::IgnoreCase))
		{
			OutWindows.Add(Window);
		}
	}
}

static FString SDWindowRectJson(const TSharedRef<SWindow>& Window)
{
	return SDRectJson(Window->GetPositionInScreen(), Window->GetSizeInScreen());
}

struct FSDDumpContext
{
	FSDLocator Root;
	int32 RootMatchIndex = -1;
	int32 RootMatchCount = 0;
	int32 MaxDepth = 0;
	bool bIncludeHidden = false;
	bool bCompact = true;
	int32 MaxNodes = 3000;
	int32 NodeCount = 0;
	bool bTruncated = false;
	TArray<FString> Nodes;
};

static bool SDIsWorthEmitting(const FSDWidgetInfo& Info, const TSharedRef<SWidget>& Widget)
{
	static const FName Type_SObjectWidget(TEXT("SObjectWidget"));

	if (Info.Size.X <= 0 || Info.Size.Y <= 0)
	{
		return false;
	}
	// 每个 UMG 控件都有名字，只凭名字输出会让 UMG 界面几乎不被精简；纯布局/装饰控件（Panel、Image 等）
	// 不输出，只保留 UserWidget 边界（SObjectWidget）作结构标记。需要它们时用 FindWidgets 或关闭精简模式
	return !Info.Tag.IsEmpty() || !Info.Text.IsEmpty() || !Info.Hint.IsEmpty() || !Info.Label.IsEmpty()
		|| Info.bClickable || Widget->SupportsKeyboardFocus()
		|| (!Info.Name.IsEmpty() && Widget->GetType() == Type_SObjectWidget);
}

// 用 ArrangeChildren 从窗口几何逐层计算子控件几何（与 Widget Reflector 一致），不依赖控件缓存的几何
static void SDDumpNode(const FArrangedWidget& Arranged, int32 Depth, bool bInRoot, FSDDumpContext& Context)
{
	if (Context.bTruncated)
	{
		return;
	}
	const TSharedRef<SWidget>& Widget = Arranged.Widget;
	const FSDWidgetInfo Info = SDMakeInfo(Arranged);
	bool bIsRoot = false;
	if (!bInRoot && SDMatchLocator(Info, Context.Root))
	{
		// 根 Locator 命中多个时，RootMatchIndex 只导出其中第 N 个（按遍历顺序）
		const int32 MatchIndex = Context.RootMatchCount++;
		if (Context.RootMatchIndex < 0 || MatchIndex == Context.RootMatchIndex)
		{
			bInRoot = true;
			bIsRoot = true;
			Depth = 0;
		}
	}
	int32 ChildDepth = Depth;
	if (bInRoot)
	{
		if (Context.MaxDepth > 0 && Depth > Context.MaxDepth)
		{
			return;
		}
		if (bIsRoot || !Context.bCompact || SDIsWorthEmitting(Info, Widget))
		{
			if (Context.NodeCount >= Context.MaxNodes)
			{
				Context.bTruncated = true;
				return;
			}
			TArray<FString> Fields;
			Fields.Add(AgentJson::PairInt(TEXT("d"), Depth));
			Fields.Append(SDNodeFields(Info, Widget));
			Context.Nodes.Add(AgentJson::Object(Fields));
			++Context.NodeCount;
			ChildDepth = Depth + 1;
		}
	}
	FArrangedChildren Children(Context.bIncludeHidden ? EVisibility::All : EVisibility::Visible, true);
	Widget->ArrangeChildren(Arranged.Geometry, Children);
	for (int32 ChildIndex = 0; ChildIndex < Children.Num(); ++ChildIndex)
	{
		SDDumpNode(Children[ChildIndex], ChildDepth, bInRoot, Context);
	}
}

struct FSDMatch
{
	FString WindowTitle;
	FSDWidgetInfo Info;
	TSharedPtr<SWidget> Widget;
	bool bQueryOnly = false;
	bool bGeometryValid = true;
	FString HiddenBy;
};

static void SDFindNode(const FArrangedWidget& Arranged, const FSDLocator& Locator, const FString& WindowTitle, TArray<FSDMatch>& OutMatches, bool bIncludeHidden = false, FString HiddenBy = FString(), bool bGeometryValid = true)
{
	FSDWidgetInfo Info = SDMakeInfo(Arranged);
	if (HiddenBy.IsEmpty() && !Arranged.Widget->GetVisibility().IsVisible())
	{
		HiddenBy = (Info.Name.IsEmpty() ? Info.Type : Info.Name) + TEXT(":") + Arranged.Widget->GetVisibility().ToString();
	}
	bGeometryValid = bGeometryValid && HiddenBy.IsEmpty();
	const bool bNodeGeometryValid = bGeometryValid && Info.Size.X > 0 && Info.Size.Y > 0;
	if ((bIncludeHidden || bNodeGeometryValid) && SDMatchLocator(Info, Locator))
	{
		FSDMatch& Match = OutMatches.AddDefaulted_GetRef();
		Match.WindowTitle = WindowTitle;
		Match.Info = MoveTemp(Info);
		Match.Widget = Arranged.Widget;
		Match.bQueryOnly = bIncludeHidden;
		Match.bGeometryValid = bNodeGeometryValid;
		Match.HiddenBy = HiddenBy;
	}
	FArrangedChildren Children(bIncludeHidden ? EVisibility::All : EVisibility::Visible, true);
	Arranged.Widget->ArrangeChildren(Arranged.Geometry, Children);
	TSet<const SWidget*> ArrangedWidgets;
	for (int32 ChildIndex = 0; ChildIndex < Children.Num(); ++ChildIndex)
	{
		if (bIncludeHidden)
		{
			ArrangedWidgets.Add(&Children[ChildIndex].Widget.Get());
		}
		SDFindNode(Children[ChildIndex], Locator, WindowTitle, OutMatches, bIncludeHidden, HiddenBy, bGeometryValid);
	}
	if (bIncludeHidden)
	{
		// 未参与布局的已有子节点仍可查结构，但不给可用于输入的几何
		FChildren* StructuralChildren = Arranged.Widget->GetChildren();
		for (int32 Index = 0; StructuralChildren && Index < StructuralChildren->Num(); ++Index)
		{
			const TSharedRef<SWidget> Child = StructuralChildren->GetChildAt(Index);
			if (!ArrangedWidgets.Contains(&Child.Get()))
			{
				SDFindNode(FArrangedWidget(Child, FGeometry()), Locator, WindowTitle, OutMatches, true, HiddenBy, false);
			}
		}
	}
}

static void SDFindMatches(const FSDLocator& Locator, const FString& WindowFilter, TArray<FSDMatch>& OutMatches, bool bIncludeHidden = false)
{
	TArray<TSharedRef<SWindow>> Windows;
	SDGetWindows(WindowFilter, Windows);
	for (const TSharedRef<SWindow>& Window : Windows)
	{
		SDFindNode(FArrangedWidget(Window, Window->GetWindowGeometryInScreen()), Locator, Window->GetTitle().ToString(), OutMatches, bIncludeHidden);
	}
}

static FString SDMatchJson(const FSDMatch& Match)
{
	TArray<FString> Fields;
	Fields.Add(AgentJson::Pair(TEXT("window"), Match.WindowTitle));
	Fields.Append(SDNodeFields(Match.Info, Match.Widget.ToSharedRef()));
	if (Match.bQueryOnly)
	{
		Fields.Add(AgentJson::PairBool(TEXT("query_only"), true));
		Fields.Add(AgentJson::PairBool(TEXT("geometry_valid"), Match.bGeometryValid));
		Fields.Add(AgentJson::PairBool(TEXT("visible_path"), Match.HiddenBy.IsEmpty()));
		if (!Match.HiddenBy.IsEmpty())
		{
			Fields.Add(AgentJson::Pair(TEXT("hidden_by"), Match.HiddenBy));
		}
	}
	return AgentJson::Object(Fields);
}

// ==================== 输入辅助 ====================

// 下一帧再执行输入：点击可能弹出模态对话框并在内部阻塞，延后执行可让本次 Python 调用先返回
static void SDQueueInput(TFunction<void()> Action)
{
	FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([Action = MoveTemp(Action)](float)
	{
		if (FSlateApplication::IsInitialized())
		{
			FSlateApplication& SlateApp = FSlateApplication::Get();
			// 焦点、鼠标、键盘的回包都可能请求捕获；仅在本次输入执行期间允许后台处理
			const bool bHandleInactiveInput = SlateApp.GetHandleDeviceInputWhenApplicationNotActive();
			SlateApp.SetHandleDeviceInputWhenApplicationNotActive(true);
			ON_SCOPE_EXIT
			{
				SlateApp.SetHandleDeviceInputWhenApplicationNotActive(bHandleInactiveInput);
			};
			Action();
		}
		return false;
	}));
}

static FKey SDParseMouseButton(const FString& Button)
{
	if (Button.IsEmpty() || Button.Equals(TEXT("Left"), ESearchCase::IgnoreCase))
	{
		return EKeys::LeftMouseButton;
	}
	if (Button.Equals(TEXT("Right"), ESearchCase::IgnoreCase))
	{
		return EKeys::RightMouseButton;
	}
	if (Button.Equals(TEXT("Middle"), ESearchCase::IgnoreCase))
	{
		return EKeys::MiddleMouseButton;
	}
	return EKeys::Invalid;
}

static FString SDDescribeHit(const FVector2D& Pos)
{
	FSlateApplication& SlateApp = FSlateApplication::Get();
	const FWidgetPath Path = SlateApp.LocateWindowUnderMouse(Pos, SlateApp.GetInteractiveTopLevelWindows());
	if (!Path.IsValid())
	{
		return TEXT("null");
	}
	const FArrangedWidget& HitWidget = Path.Widgets.Last();
	return SDDescribeWidget(HitWidget.Widget, HitWidget.Geometry);
}

static FPointerEvent SDMakePointerEvent(const FVector2D& Pos, const FVector2D& LastPos, const TSet<FKey>& PressedButtons, const FKey& EffectingButton, float WheelDelta)
{
	FSlateApplication& SlateApp = FSlateApplication::Get();
	return FPointerEvent(
		static_cast<uint32>(SlateApp.GetUserIndexForMouse()),
		FSlateApplicationBase::CursorPointerIndex,
		Pos,
		LastPos,
		PressedButtons,
		EffectingButton,
		WheelDelta,
		SlateApp.GetModifierKeys());
}

static TMap<int32, FString> SDInputResults;
static int32 SDNextInputRequest = 0;

static FString SDSendClick(const FVector2D Pos, const FKey Button, const bool bDoubleClick, const TSharedPtr<SWidget>& Expected = nullptr, bool bCheckHit = false)
{
	FSlateApplication& SlateApp = FSlateApplication::Get();
	const TSet<FKey> NoButtons;
	TSet<FKey> PressedButtons;
	PressedButtons.Add(Button);
	const FPointerEvent DownEvent = SDMakePointerEvent(Pos, Pos, PressedButtons, Button, 0.0f);
	const FPointerEvent UpEvent = SDMakePointerEvent(Pos, Pos, NoButtons, Button, 0.0f);
	FWidgetPath Path;
	TArray<FString> Fields;
	int32 ClicksSent = 0;

	auto CheckPath = [&]()
	{
		Path = SlateApp.LocateWindowUnderMouse(Pos, SlateApp.GetInteractiveTopLevelWindows(), false, DownEvent.GetUserIndex());
		const TSharedPtr<FSlateUser> User = SlateApp.GetUser(DownEvent.GetUserIndex());
		if (User.IsValid() && User->HasCapture(DownEvent.GetPointerIndex()))
		{
			Path = User->GetCaptorPath(DownEvent.GetPointerIndex(), FWeakWidgetPath::EInterruptedPathHandling::ReturnInvalid, &DownEvent);
		}
		if (!Path.IsValid())
		{
			return false;
		}
		if (!bCheckHit)
		{
			return true;
		}
		if (!Expected.IsValid() || !Expected->IsEnabled())
		{
			return false;
		}
		// 比较真实控件身份，允许命中预期控件的子节点；不比较名称或矩形
		for (int32 Index = 0; Index < Path.Widgets.Num(); ++Index)
		{
			const FArrangedWidget& Widget = Path.Widgets[Index];
			if (&Widget.Widget.Get() == Expected.Get() && Widget.Widget->GetVisibility().IsVisible())
			{
				return true;
			}
		}
		return false;
	};
	auto Finish = [&](bool bSuccess)
	{
		Fields.Add(AgentJson::PairBool(TEXT("pending"), false));
		Fields.Add(AgentJson::PairInt(TEXT("clicks_sent"), ClicksSent));
		Fields.Add(AgentJson::PairRaw(TEXT("pos"), SDPointJson(Pos)));
		if (Path.IsValid())
		{
			const FArrangedWidget& Hit = Path.Widgets.Last();
			Fields.Add(AgentJson::PairRaw(TEXT("hit"), SDDescribeWidget(Hit.Widget, Hit.Geometry)));
		}
		return SDResult(bSuccess, bSuccess ? FString() : TEXT("Hit assertion failed or target unavailable; no further mouse down sent"), Fields);
	};
	if (!CheckPath())
	{
		return Finish(false);
	}
	// 移动可能改变悬停或捕获，再查一次路径才发送按下
	SlateApp.ProcessMouseMoveEvent(SDMakePointerEvent(Pos, SlateApp.GetCursorPos(), NoButtons, EKeys::Invalid, 0.0f));
	if (!CheckPath())
	{
		return Finish(false);
	}
	SlateApp.ProcessMouseButtonDownEvent(Path.GetWindow()->GetNativeWindow(), DownEvent);
	++ClicksSent;
	// 已发按下必须配对抬起，不因回调销毁控件而遗留按住状态
	SlateApp.ProcessMouseButtonUpEvent(UpEvent);
	if (bDoubleClick)
	{
		if (!CheckPath())
		{
			return Finish(false);
		}
		SlateApp.ProcessMouseButtonDoubleClickEvent(Path.GetWindow()->GetNativeWindow(), DownEvent);
		++ClicksSent;
		SlateApp.ProcessMouseButtonUpEvent(UpEvent);
	}
	return Finish(true);
}

static FString SDQueueClick(const FVector2D& Pos, const FString& Button, bool bDoubleClick, TArray<FString> ExtraFields, const FString& ExpectHit = FString(), const FString& WindowFilter = FString())
{
	const FKey ButtonKey = SDParseMouseButton(Button);
	if (!ButtonKey.IsValid())
	{
		return SDResult(false, FString::Printf(TEXT("Unknown mouse button: %s"), *Button));
	}
	TWeakPtr<SWidget> Expected;
	int32 RequestId = 0;
	if (!ExpectHit.IsEmpty())
	{
		const FSDLocator Locator = SDParseLocator(ExpectHit);
		TArray<FSDMatch> Matches;
		if (!Locator.IsEmpty())
		{
			SDFindMatches(Locator, WindowFilter, Matches);
		}
		if (Matches.Num() != 1)
		{
			return SDResult(false, TEXT("ExpectHit must identify exactly one visible widget"));
		}
		Expected = Matches[0].Widget;
		RequestId = ++SDNextInputRequest;
		SDInputResults.Remove(RequestId - 64);
		SDInputResults.Add(RequestId, TEXT("{\"success\":true,\"pending\":true}"));
		ExtraFields.Add(AgentJson::PairInt(TEXT("request_id"), RequestId));
	}
	ExtraFields.Add(AgentJson::PairRaw(TEXT("pos"), SDPointJson(Pos)));
	ExtraFields.Add(AgentJson::PairRaw(TEXT("hit"), SDDescribeHit(Pos)));
	SDQueueInput([Pos, ButtonKey, bDoubleClick, Expected, RequestId]()
	{
		const FString Result = SDSendClick(Pos, ButtonKey, bDoubleClick, Expected.Pin(), RequestId != 0);
		if (RequestId != 0 && SDInputResults.Contains(RequestId))
		{
			SDInputResults[RequestId] = Result;
		}
	});
	return SDResult(true, FString(), ExtraFields);
}

static FString SDDescribeFocus()
{
	const TSharedPtr<SWidget> Focused = FSlateApplication::Get().GetKeyboardFocusedWidget();
	if (!Focused.IsValid())
	{
		return TEXT("null");
	}
	return SDDescribeWidget(Focused, Focused->GetTickSpaceGeometry());
}

// ==================== 控件树读取 ====================

FString UAgentSlateDriverFunctionLib::ListWindows()
{
	if (!FSlateApplication::IsInitialized())
	{
		return TEXT("{\"error\":\"Slate is not initialized\"}");
	}
	const TSharedPtr<SWindow> ActiveWindow = FSlateApplication::Get().GetActiveTopLevelWindow();
	TArray<TSharedRef<SWindow>> Windows;
	SDGetWindows(FString(), Windows);
	TArray<FString> Items;
	for (const TSharedRef<SWindow>& Window : Windows)
	{
		TArray<FString> Fields;
		Fields.Add(AgentJson::Pair(TEXT("title"), Window->GetTitle().ToString()));
		Fields.Add(AgentJson::PairRaw(TEXT("rect"), SDWindowRectJson(Window)));
		Fields.Add(AgentJson::PairBool(TEXT("active"), ActiveWindow == Window));
		Items.Add(AgentJson::Object(Fields));
	}
	return AgentJson::Array(Items);
}

FString UAgentSlateDriverFunctionLib::ListPIEViewports()
{
	if (!GEngine || !FSlateApplication::IsInitialized())
	{
		return TEXT("[]");
	}
	FSlateApplication& SlateApp = FSlateApplication::Get();
	TArray<FString> Items;
	for (const FWorldContext& Context : GEngine->GetWorldContexts())
	{
		if (Context.WorldType != EWorldType::PIE || !Context.World() || !Context.GameViewport)
		{
			continue;
		}
		const TSharedPtr<SViewport> Viewport = Context.GameViewport->GetGameViewportWidget();
		if (!Viewport.IsValid())
		{
			continue;
		}
		const TSharedPtr<SWindow> Window = SlateApp.FindWidgetWindow(Viewport.ToSharedRef());
		if (!Window.IsValid() || !Window->IsVisible() || Window->IsWindowMinimized())
		{
			continue;
		}
		FArrangedChildren Root(EVisibility::Visible);
		Root.AddWidget(FArrangedWidget(Window.ToSharedRef(), Window->GetWindowGeometryInScreen()));
		FWidgetPath Path(Window, Root);
		if (!Path.ExtendPathTo(FWidgetMatcher(Viewport.ToSharedRef()), EVisibility::Visible))
		{
			continue;
		}
		const FGeometry& Geometry = Path.Widgets.Last().Geometry;
		if (Geometry.GetAbsoluteSize().X <= 0 || Geometry.GetAbsoluteSize().Y <= 0)
		{
			continue;
		}
		TArray<FString> Fields;
		Fields.Add(AgentJson::Pair(TEXT("world"), Context.World()->GetPathName()));
		Fields.Add(AgentJson::PairInt(TEXT("instance"), Context.PIEInstance));
		Fields.Add(AgentJson::Pair(TEXT("window"), Window->GetTitle().ToString()));
		Fields.Add(AgentJson::PairRaw(TEXT("rect"), SDRectJson(Geometry.GetAbsolutePosition(), Geometry.GetAbsoluteSize())));
		Items.Add(AgentJson::Object(Fields));
	}
	return AgentJson::Array(Items);
}

FString UAgentSlateDriverFunctionLib::DumpSlateTree(const FString& WindowFilter, const FString& RootLocator, int32 MaxDepth, bool bIncludeHidden, bool bCompact, int32 MaxNodes, int32 RootMatchIndex)
{
	if (!FSlateApplication::IsInitialized())
	{
		return TEXT("{\"error\":\"Slate is not initialized\"}");
	}
	FSDDumpContext Context;
	Context.Root = SDParseLocator(RootLocator);
	Context.RootMatchIndex = RootMatchIndex;
	Context.MaxDepth = MaxDepth;
	Context.bIncludeHidden = bIncludeHidden;
	Context.bCompact = bCompact;
	Context.MaxNodes = MaxNodes > 0 ? MaxNodes : 3000;
	const bool bWholeTree = Context.Root.IsEmpty();

	TArray<TSharedRef<SWindow>> Windows;
	SDGetWindows(WindowFilter, Windows);
	TArray<FString> WindowItems;
	for (const TSharedRef<SWindow>& Window : Windows)
	{
		Context.Nodes.Reset();
		SDDumpNode(FArrangedWidget(Window, Window->GetWindowGeometryInScreen()), 0, bWholeTree, Context);
		if (!bWholeTree && Context.Nodes.Num() == 0)
		{
			continue;
		}
		TArray<FString> Fields;
		Fields.Add(AgentJson::Pair(TEXT("title"), Window->GetTitle().ToString()));
		Fields.Add(AgentJson::PairRaw(TEXT("rect"), SDWindowRectJson(Window)));
		Fields.Add(AgentJson::PairRaw(TEXT("nodes"), AgentJson::Array(Context.Nodes)));
		WindowItems.Add(AgentJson::Object(Fields));
	}

	TArray<FString> Fields;
	Fields.Add(AgentJson::PairRaw(TEXT("windows"), AgentJson::Array(WindowItems)));
	Fields.Add(AgentJson::PairInt(TEXT("node_count"), Context.NodeCount));
	Fields.Add(AgentJson::PairBool(TEXT("truncated"), Context.bTruncated));
	if (!bWholeTree)
	{
		Fields.Add(AgentJson::PairInt(TEXT("root_match_count"), Context.RootMatchCount));
	}
	return AgentJson::Object(Fields);
}

FString UAgentSlateDriverFunctionLib::FindWidgets(const FString& Locator, const FString& WindowFilter, bool bIncludeHidden)
{
	if (!FSlateApplication::IsInitialized())
	{
		return TEXT("{\"error\":\"Slate is not initialized\"}");
	}
	const FSDLocator ParsedLocator = SDParseLocator(Locator);
	if (ParsedLocator.IsEmpty())
	{
		return TEXT("{\"error\":\"Locator is empty\"}");
	}
	TArray<FSDMatch> Matches;
	SDFindMatches(ParsedLocator, WindowFilter, Matches, bIncludeHidden);
	TArray<FString> Items;
	for (const FSDMatch& Match : Matches)
	{
		Items.Add(SDMatchJson(Match));
	}
	return AgentJson::Array(Items);
}

// ==================== 键盘焦点 ====================

FString UAgentSlateDriverFunctionLib::GetKeyboardFocus()
{
	if (!FSlateApplication::IsInitialized())
	{
		return TEXT("{\"error\":\"Slate is not initialized\"}");
	}
	return SDDescribeFocus();
}

FString UAgentSlateDriverFunctionLib::FocusWidget(const FString& Locator, const FString& WindowFilter, int32 MatchIndex)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FSDLocator ParsedLocator = SDParseLocator(Locator);
	if (ParsedLocator.IsEmpty())
	{
		return SDResult(false, TEXT("Locator is empty"));
	}
	TArray<FSDMatch> Matches;
	SDFindMatches(ParsedLocator, WindowFilter, Matches);
	TArray<FString> ExtraFields;
	ExtraFields.Add(AgentJson::PairInt(TEXT("match_count"), Matches.Num()));
	if (!Matches.IsValidIndex(MatchIndex))
	{
		return SDResult(false, FString::Printf(TEXT("No widget at match index %d"), MatchIndex), ExtraFields);
	}
	const FSDMatch& Match = Matches[MatchIndex];
	if (!Match.Widget->SupportsKeyboardFocus())
	{
		return SDResult(false, TEXT("Widget does not support keyboard focus; target the inner editable widget"), ExtraFields);
	}
	ExtraFields.Add(AgentJson::PairRaw(TEXT("target"), SDMatchJson(Match)));
	// 与输入一同排队到下一帧，保证"先聚焦、再输入"的顺序；直接设焦点，不依赖点击路由（编辑器不在前台时点击可能拿不到焦点）
	const TWeakPtr<SWidget> WeakWidget = Match.Widget;
	SDQueueInput([WeakWidget]()
	{
		if (const TSharedPtr<SWidget> Widget = WeakWidget.Pin())
		{
			FSlateApplication::Get().SetKeyboardFocus(Widget, EFocusCause::SetDirectly);
		}
	});
	return SDResult(true, FString(), ExtraFields);
}

// ==================== 鼠标输入 ====================

FString UAgentSlateDriverFunctionLib::ClickAt(float X, float Y, const FString& Button, bool bDoubleClick, const FString& ExpectHit)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	return SDQueueClick(FVector2D(X, Y), Button, bDoubleClick, TArray<FString>(), ExpectHit);
}

FString UAgentSlateDriverFunctionLib::ClickWidget(const FString& Locator, const FString& WindowFilter, int32 MatchIndex, const FString& Button, bool bDoubleClick, const FString& ExpectHit)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FSDLocator ParsedLocator = SDParseLocator(Locator);
	if (ParsedLocator.IsEmpty())
	{
		return SDResult(false, TEXT("Locator is empty"));
	}
	TArray<FSDMatch> Matches;
	SDFindMatches(ParsedLocator, WindowFilter, Matches);
	TArray<FString> ExtraFields;
	ExtraFields.Add(AgentJson::PairInt(TEXT("match_count"), Matches.Num()));
	if (!Matches.IsValidIndex(MatchIndex))
	{
		return SDResult(false, FString::Printf(TEXT("No widget at match index %d"), MatchIndex), ExtraFields);
	}
	const FSDMatch& Match = Matches[MatchIndex];
	ExtraFields.Add(AgentJson::PairRaw(TEXT("target"), SDMatchJson(Match)));
	return SDQueueClick(Match.Info.Pos + Match.Info.Size * 0.5, Button, bDoubleClick, ExtraFields, ExpectHit, WindowFilter);
}

FString UAgentSlateDriverFunctionLib::GetInputResult(int32 RequestId)
{
	if (const FString* Result = SDInputResults.Find(RequestId))
	{
		return *Result;
	}
	return SDResult(false, TEXT("Unknown or expired input request"), {AgentJson::PairBool(TEXT("pending"), false)});
}

FString UAgentSlateDriverFunctionLib::ScrollAt(float X, float Y, float Delta)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FVector2D Pos(X, Y);
	TArray<FString> ExtraFields;
	ExtraFields.Add(AgentJson::PairRaw(TEXT("pos"), SDPointJson(Pos)));
	ExtraFields.Add(AgentJson::PairRaw(TEXT("hit"), SDDescribeHit(Pos)));
	SDQueueInput([Pos, Delta]()
	{
		FSlateApplication& SlateApp = FSlateApplication::Get();
		const TSet<FKey> NoButtons;
		SlateApp.ProcessMouseMoveEvent(SDMakePointerEvent(Pos, SlateApp.GetCursorPos(), NoButtons, EKeys::Invalid, 0.0f));
		SlateApp.ProcessMouseWheelOrGestureEvent(SDMakePointerEvent(Pos, Pos, NoButtons, EKeys::Invalid, Delta), nullptr);
	});
	return SDResult(true, FString(), ExtraFields);
}

// ==================== 键盘输入 ====================

FString UAgentSlateDriverFunctionLib::PressKey(const FString& KeyName, bool bCtrl, bool bShift, bool bAlt)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FKey Key(*KeyName);
	if (!Key.IsValid())
	{
		return SDResult(false, FString::Printf(TEXT("Unknown key: %s"), *KeyName));
	}
	TArray<FString> ExtraFields;
	ExtraFields.Add(AgentJson::PairRaw(TEXT("focus"), SDDescribeFocus()));
	SDQueueInput([Key, bCtrl, bShift, bAlt]()
	{
		FSlateApplication& SlateApp = FSlateApplication::Get();
		const uint32* KeyCodePtr = nullptr;
		const uint32* CharCodePtr = nullptr;
		FInputKeyManager::Get().GetCodesFromKey(Key, KeyCodePtr, CharCodePtr);
		const FModifierKeysState ModifierKeys(bShift, false, bCtrl, false, bAlt, false, false, false, false);
		const uint32 UserIndex = static_cast<uint32>(SlateApp.GetUserIndexForKeyboard());
		const FKeyEvent KeyEvent(Key, ModifierKeys, UserIndex, false, CharCodePtr ? *CharCodePtr : 0, KeyCodePtr ? *KeyCodePtr : 0);
		SlateApp.ProcessKeyDownEvent(KeyEvent);
		// 普通退格由字符事件处理，Ctrl/Alt 组合由按键事件处理
		if (Key == EKeys::BackSpace && !bCtrl && !bAlt)
		{
			SlateApp.ProcessKeyCharEvent(FCharacterEvent(TCHAR(8), ModifierKeys, UserIndex, false));
		}
		// 新增 ticker 可能在同帧执行，用帧号保证抬起至少晚两帧
		const uint64 ReleaseFrame = GFrameCounter + 2;
		FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([KeyEvent, ReleaseFrame](float)
		{
			if (GFrameCounter < ReleaseFrame)
			{
				return true;
			}
			if (FSlateApplication::IsInitialized())
			{
				FSlateApplication& SlateApp = FSlateApplication::Get();
				const bool bHandleInactiveInput = SlateApp.GetHandleDeviceInputWhenApplicationNotActive();
				SlateApp.SetHandleDeviceInputWhenApplicationNotActive(true);
				ON_SCOPE_EXIT
				{
					SlateApp.SetHandleDeviceInputWhenApplicationNotActive(bHandleInactiveInput);
				};
				SlateApp.ProcessKeyUpEvent(KeyEvent);
			}
			return false;
		}));
	});
	return SDResult(true, FString(), ExtraFields);
}

FString UAgentSlateDriverFunctionLib::TypeText(const FString& Text)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	TArray<FString> ExtraFields;
	ExtraFields.Add(AgentJson::PairRaw(TEXT("focus"), SDDescribeFocus()));
	SDQueueInput([Text]()
	{
		FSlateApplication& SlateApp = FSlateApplication::Get();
		const uint32 UserIndex = static_cast<uint32>(SlateApp.GetUserIndexForKeyboard());
		for (const TCHAR Character : Text)
		{
			SlateApp.ProcessKeyCharEvent(FCharacterEvent(Character, FModifierKeysState(), UserIndex, false));
		}
	});
	return SDResult(true, FString(), ExtraFields);
}
