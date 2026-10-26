#include "AgentSlateDriverFunctionLib.h"

#include "AgentJson.h"
#include "Containers/Ticker.h"
#include "CoreGlobals.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "Framework/Application/SlateUser.h"
#include "GenericPlatform/GenericPlatformInputDeviceMapper.h"
#include "HAL/IConsoleManager.h"
#include "InputCoreTypes.h"
#include "Layout/ArrangedChildren.h"
#include "Layout/Clipping.h"
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
#include "Widgets/Text/SMultiLineEditableText.h"
#include "Widgets/Text/SRichTextBlock.h"
#include "Widgets/Text/STextBlock.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Widgets/Layout/SBorder.h"
#endif

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

static bool SDPushClip(const FArrangedWidget& Arranged, FSlateClippingManager& Clipping)
{
	bool bClipToBounds, bAlwaysClip, bIntersectClipBounds;
	Arranged.Widget->CalculateCullingAndClippingRules(Arranged.Geometry, Arranged.Geometry.GetRenderBoundingRect(), bClipToBounds, bAlwaysClip, bIntersectClipBounds);
	if (bClipToBounds)
	{
		FSlateClippingZone Zone(Arranged.Geometry);
		Zone.SetShouldIntersectParent(bIntersectClipBounds);
		Zone.SetAlwaysClip(bAlwaysClip);
		Clipping.PushClip(Zone);
	}
	return bClipToBounds;
}

static FSlateRect SDVisibleRect(const FSDWidgetInfo& Info, const FSlateClippingManager& Clipping)
{
	FSlateRect Rect(Info.Pos.X, Info.Pos.Y, Info.Pos.X + Info.Size.X, Info.Pos.Y + Info.Size.Y);
	const TOptional<FSlateClippingState> State = Clipping.GetActiveClippingState();
	if (State.IsSet())
	{
		auto Intersect = [&Rect](const FSlateClippingZone& Zone)
		{
			const FSlateRect Bounds = Zone.GetBoundingBox();
			Rect.Left = FMath::Max(Rect.Left, Bounds.Left);
			Rect.Top = FMath::Max(Rect.Top, Bounds.Top);
			Rect.Right = FMath::Max(Rect.Left, FMath::Min(Rect.Right, Bounds.Right));
			Rect.Bottom = FMath::Max(Rect.Top, FMath::Min(Rect.Bottom, Bounds.Bottom));
		};
		if (State->ScissorRect.IsSet())
		{
			Intersect(State->ScissorRect.GetValue());
		}
		else
		{
			for (const FSlateClippingZone& Zone : State->StencilQuads)
			{
				Intersect(Zone);
			}
		}
	}
	return Rect;
}

struct FSDMatch
{
	FString WindowTitle;
	FSDWidgetInfo Info;
	TSharedPtr<SWidget> Widget;
	bool bQueryOnly = false;
	bool bGeometryValid = true;
	bool bClipped = false;
	FSlateRect VisibleRect;
	FString HiddenBy;
};

static void SDFindNode(const FArrangedWidget& Arranged, FSlateClippingManager& Clipping, const FSDLocator& Locator, const FString& WindowTitle, TArray<FSDMatch>& OutMatches, bool bIncludeHidden = false, FString HiddenBy = FString(), bool bGeometryValid = true)
{
	const bool bPushedClip = bGeometryValid && SDPushClip(Arranged, Clipping);
	ON_SCOPE_EXIT
	{
		if (bPushedClip)
		{
			Clipping.PopClip();
		}
	};
	FSDWidgetInfo Info = SDMakeInfo(Arranged);
	if (HiddenBy.IsEmpty() && !Arranged.Widget->GetVisibility().IsVisible())
	{
		HiddenBy = (Info.Name.IsEmpty() ? Info.Type : Info.Name) + TEXT(":") + Arranged.Widget->GetVisibility().ToString();
	}
	bGeometryValid = bGeometryValid && HiddenBy.IsEmpty();
	const bool bNodeGeometryValid = bGeometryValid && Info.Size.X > 0 && Info.Size.Y > 0;
	if ((bIncludeHidden || bNodeGeometryValid) && SDMatchLocator(Info, Locator))
	{
		const FSlateRect VisibleRect = SDVisibleRect(Info, Clipping);
		const bool bOnScreen = bNodeGeometryValid && VisibleRect.Right > VisibleRect.Left && VisibleRect.Bottom > VisibleRect.Top;
		if (bIncludeHidden || bOnScreen)
		{
			FSDMatch& Match = OutMatches.AddDefaulted_GetRef();
			Match.WindowTitle = WindowTitle;
			Match.bClipped = bNodeGeometryValid && (FMath::RoundToInt(VisibleRect.Left) != FMath::RoundToInt(Info.Pos.X)
				|| FMath::RoundToInt(VisibleRect.Top) != FMath::RoundToInt(Info.Pos.Y)
				|| FMath::RoundToInt(VisibleRect.Right - VisibleRect.Left) != FMath::RoundToInt(Info.Size.X)
				|| FMath::RoundToInt(VisibleRect.Bottom - VisibleRect.Top) != FMath::RoundToInt(Info.Size.Y));
			Match.VisibleRect = VisibleRect;
			Match.Info = MoveTemp(Info);
			Match.Widget = Arranged.Widget;
			Match.bQueryOnly = bIncludeHidden;
			Match.bGeometryValid = bNodeGeometryValid;
			Match.HiddenBy = HiddenBy;
		}
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
		SDFindNode(Children[ChildIndex], Clipping, Locator, WindowTitle, OutMatches, bIncludeHidden, HiddenBy, bGeometryValid);
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
				SDFindNode(FArrangedWidget(Child, FGeometry()), Clipping, Locator, WindowTitle, OutMatches, true, HiddenBy, false);
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
		FSlateClippingManager Clipping;
		SDFindNode(FArrangedWidget(Window, Window->GetWindowGeometryInScreen()), Clipping, Locator, Window->GetTitle().ToString(), OutMatches, bIncludeHidden);
	}
}

static FString SDMatchJson(const FSDMatch& Match)
{
	TArray<FString> Fields;
	Fields.Add(AgentJson::Pair(TEXT("window"), Match.WindowTitle));
	Fields.Append(SDNodeFields(Match.Info, Match.Widget.ToSharedRef()));
	if (Match.bClipped)
	{
		Fields.Add(AgentJson::PairBool(TEXT("clipped"), true));
		Fields.Add(AgentJson::PairRaw(TEXT("visible_rect"), SDRectJson(FVector2D(Match.VisibleRect.Left, Match.VisibleRect.Top),
			FVector2D(Match.VisibleRect.Right - Match.VisibleRect.Left, Match.VisibleRect.Bottom - Match.VisibleRect.Top))));
	}
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

// 新请求占一个 id 并登记 pending；旧结果滚动淘汰
static int32 SDRegisterInput()
{
	const int32 RequestId = ++SDNextInputRequest;
	SDInputResults.Remove(RequestId - 64);
	SDInputResults.Add(RequestId, SDResult(true, FString(), {AgentJson::PairBool(TEXT("pending"), true)}));
	return RequestId;
}

static bool SDIsAncestorOf(const TSharedPtr<SWidget>& Ancestor, const TSharedPtr<SWidget>& Widget)
{
	int32 Guard = 0;
	for (TSharedPtr<SWidget> Parent = Widget.IsValid() ? Widget->GetParentWidget() : nullptr;
		Parent.IsValid() && Guard++ < 256; Parent = Parent->GetParentWidget())
	{
		if (Parent.Get() == Ancestor.Get())
		{
			return true;
		}
	}
	return false;
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

// ==================== 输入时间线 ====================
// 输入只提供原子步骤，全部排在一条时间线上：每帧最多完成一步，相邻两步至少隔一帧，前一步完成才执行下一步，
// 某步失败时取消其后所有步骤。点击、长按、拖动、文本输入等组合由 Skill 的 Python 模块 ue_input 拼装。

enum class ESDStep : uint8
{
	Running,
	Done,
	Failed,
};

struct FSDTimelineStep
{
	int32 RequestId = 0;
	TFunction<ESDStep()> Run;
};

static TArray<FSDTimelineStep> SDTimeline;
static bool bSDTimelineTicking = false;

static TMap<FKey, FKeyEvent> SDHeldKeys;
static TSet<FKey> SDHeldButtons;
// 每次按下递增；看门狗只抬起自己那次按下，不误抬已经抬起又重新按下的键
static TMap<FKey, int32> SDHoldSerials;
static int32 SDNextHoldSerial = 0;
static TOptional<FVector2D> SDPointerPos;

// 只在本次输入执行期间打开后台输入开关，结束后恢复
static void SDWithBackgroundInput(const TFunction<void(FSlateApplication&)>& Action)
{
	FSlateApplication& SlateApp = FSlateApplication::Get();
	const bool bHandleInactiveInput = SlateApp.GetHandleDeviceInputWhenApplicationNotActive();
	SlateApp.SetHandleDeviceInputWhenApplicationNotActive(true);
	ON_SCOPE_EXIT
	{
		SlateApp.SetHandleDeviceInputWhenApplicationNotActive(bHandleInactiveInput);
	};
	Action(SlateApp);
}

static bool SDIsPending(int32 RequestId)
{
	const FString* Result = SDInputResults.Find(RequestId);
	return Result && Result->Contains(TEXT("\"pending\":true"));
}

static void SDClearHover();

static void SDSetInputResult(int32 RequestId, bool bSuccess, const FString& Message, TArray<FString> Fields = TArray<FString>())
{
	if (!bSuccess)
	{
		SDClearHover();
	}
	if (RequestId != 0 && SDInputResults.Contains(RequestId))
	{
		Fields.Insert(AgentJson::PairBool(TEXT("pending"), false), 0);
		SDInputResults[RequestId] = SDResult(bSuccess, Message, Fields);
	}
}

static void SDCancelTimeline(const FString& Message)
{
	for (const FSDTimelineStep& Step : SDTimeline)
	{
		if (SDIsPending(Step.RequestId))
		{
			SDSetInputResult(Step.RequestId, false, Message);
		}
	}
	SDTimeline.Empty();
	SDClearHover();
}

static bool SDTickTimeline(float)
{
	if (!FSlateApplication::IsInitialized() || SDTimeline.Num() == 0)
	{
		SDTimeline.Empty();
		bSDTimelineTicking = false;
		return false;
	}
	const FSDTimelineStep Step = SDTimeline[0];
	ESDStep State = ESDStep::Running;
	SDWithBackgroundInput([&](FSlateApplication&)
	{
		State = Step.Run();
	});
	if (State != ESDStep::Running)
	{
		// 步骤没写结果时按完成状态补一条，调用方总能读到终态
		if (SDIsPending(Step.RequestId))
		{
			SDSetInputResult(Step.RequestId, State == ESDStep::Done, State == ESDStep::Done ? FString() : FString(TEXT("Input step failed")));
		}
		if (SDTimeline.Num() > 0 && SDTimeline[0].RequestId == Step.RequestId)
		{
			SDTimeline.RemoveAt(0);
		}
		if (State == ESDStep::Failed)
		{
			SDCancelTimeline(TEXT("Cancelled because an earlier queued input failed"));
		}
	}
	if (SDTimeline.Num() == 0)
	{
		bSDTimelineTicking = false;
		return false;
	}
	return true;
}

// 登记请求并排进时间线；Run 每帧调用一次直到不再返回 Running
static int32 SDTimelineAdd(TFunction<ESDStep(int32)> Run)
{
	const int32 RequestId = SDRegisterInput();
	SDTimeline.Add({RequestId, [RequestId, Run = MoveTemp(Run)]() { return Run(RequestId); }});
	if (!bSDTimelineTicking)
	{
		bSDTimelineTicking = true;
		FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateStatic(&SDTickTimeline));
	}
	return RequestId;
}

static FString SDQueued(int32 RequestId, TArray<FString> ExtraFields = TArray<FString>())
{
	ExtraFields.Add(AgentJson::PairInt(TEXT("request_id"), RequestId));
	return SDResult(true, FString(), ExtraFields);
}

static FVector2D SDPointer()
{
	return SDPointerPos.IsSet() ? SDPointerPos.GetValue() : FSlateApplication::Get().GetCursorPos();
}

static FKeyEvent SDMakeKeyEvent(const FKey& Key, bool bCtrl, bool bShift, bool bAlt)
{
	const uint32* KeyCodePtr = nullptr;
	const uint32* CharCodePtr = nullptr;
	FInputKeyManager::Get().GetCodesFromKey(Key, KeyCodePtr, CharCodePtr);
	const FModifierKeysState ModifierKeys(bShift, false, bCtrl, false, bAlt, false, false, false, false);
	const uint32 UserIndex = static_cast<uint32>(FSlateApplication::Get().GetUserIndexForKeyboard());
	return FKeyEvent(Key, ModifierKeys, UserIndex, false, CharCodePtr ? *CharCodePtr : 0, KeyCodePtr ? *KeyCodePtr : 0);
}

static void SDReleaseKey(const FKey& Key)
{
	FKeyEvent Event;
	if (SDHeldKeys.RemoveAndCopyValue(Key, Event))
	{
		SDHoldSerials.Remove(Key);
		FSlateApplication::Get().ProcessKeyUpEvent(Event);
	}
}

// 按住或悬停保持期间关闭自动光标移动，避免真实光标的位置覆盖注入路径
static TOptional<int32> SDSavedSyntheticMoves;
static double SDHoverDeadline = 0.0;
static bool bSDHoverTicking = false;
static constexpr double SDHoverSeconds = 10.0;

static void SDSuppressSyntheticMoves(bool bSuppress)
{
	IConsoleVariable* Var = IConsoleManager::Get().FindConsoleVariable(TEXT("Slate.EnableSyntheticCursorMoves"));
	if (!Var)
	{
		return;
	}
	if (bSuppress && !SDSavedSyntheticMoves.IsSet())
	{
		SDSavedSyntheticMoves = Var->GetInt();
		Var->Set(0, static_cast<EConsoleVariableFlags>(Var->GetFlags() & ECVF_SetByMask));
	}
	else if (!bSuppress && SDSavedSyntheticMoves.IsSet())
	{
		Var->Set(SDSavedSyntheticMoves.GetValue(), static_cast<EConsoleVariableFlags>(Var->GetFlags() & ECVF_SetByMask));
		SDSavedSyntheticMoves.Reset();
	}
}

static void SDClearHover()
{
	SDHoverDeadline = 0.0;
	SDSuppressSyntheticMoves(SDHeldButtons.Num() > 0);
}

static void SDKeepHover()
{
	SDHoverDeadline = FPlatformTime::Seconds() + SDHoverSeconds;
	SDSuppressSyntheticMoves(true);
	if (!bSDHoverTicking)
	{
		bSDHoverTicking = true;
		FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([](float)
		{
			if (FSlateApplication::IsInitialized() && FPlatformTime::Seconds() < SDHoverDeadline)
			{
				return true;
			}
			SDClearHover();
			bSDHoverTicking = false;
			return false;
		}));
	}
}

static void SDReleaseButton(const FKey& Button)
{
	if (SDHeldButtons.Remove(Button) > 0)
	{
		SDHoldSerials.Remove(Button);
		const FVector2D Pos = SDPointer();
		FSlateApplication::Get().ProcessMouseButtonUpEvent(SDMakePointerEvent(Pos, Pos, SDHeldButtons, Button, 0.0f));
		if (SDHeldButtons.Num() == 0)
		{
			SDClearHover();
		}
	}
}

static void SDArmWatchdog(const FKey& Key, int32 Serial, float MaxHoldSeconds)
{
	if (MaxHoldSeconds <= 0.f)
	{
		return;
	}
	const double Deadline = FPlatformTime::Seconds() + MaxHoldSeconds;
	FTSTicker::GetCoreTicker().AddTicker(FTickerDelegate::CreateLambda([Key, Serial, Deadline](float)
	{
		if (FPlatformTime::Seconds() < Deadline)
		{
			return true;
		}
		const int32* Current = SDHoldSerials.Find(Key);
		if (FSlateApplication::IsInitialized() && Current && *Current == Serial)
		{
			SDWithBackgroundInput([&](FSlateApplication&)
			{
				if (Key.IsMouseButton())
				{
					SDReleaseButton(Key);
				}
				else
				{
					SDReleaseKey(Key);
				}
			});
		}
		return false;
	}));
}

// ==================== 手柄模拟轴 ====================

FString UAgentSlateDriverFunctionLib::AnalogInput(const FString& KeyName, float Value, int32 DeviceId)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FKey Key(*KeyName);
	const bool bTrigger = Key == EKeys::Gamepad_LeftTriggerAxis || Key == EKeys::Gamepad_RightTriggerAxis;
	if (!Key.IsGamepadKey() || !Key.IsAxis1D() || !FMath::IsFinite(Value) || Value < (bTrigger ? 0.f : -1.f) || Value > 1.f || DeviceId < -1)
	{
		return SDResult(false, TEXT("Supply a gamepad Axis1D key, a finite value in range, and a valid device id"));
	}
	IPlatformInputDeviceMapper& Mapper = IPlatformInputDeviceMapper::Get();
	const FInputDeviceId Device = DeviceId == -1 ? Mapper.GetDefaultInputDevice() : FInputDeviceId::CreateFromInternalId(DeviceId);
	const FPlatformUserId User = Mapper.GetUserForInputDevice(Device);
	const TOptional<int32> SlateUser = FSlateApplication::Get().GetUserIndexForInputDevice(Device);
	if (!Device.IsValid() || !User.IsValid() || !SlateUser.IsSet() || SlateUser.GetValue() < 0)
	{
		return SDResult(false, TEXT("Input device has no valid platform/Slate user mapping"));
	}
	bool bHandled = false;
	SDWithBackgroundInput([&](FSlateApplication& SlateApp)
	{
		bHandled = SlateApp.OnControllerAnalog(Key.GetFName(), User, Device, Value);
	});
	return SDResult(true, FString(), {AgentJson::PairBool(TEXT("handled"), bHandled),
		AgentJson::PairInt(TEXT("device_id"), Device.GetId()), AgentJson::PairInt(TEXT("platform_user"), User.GetInternalId()),
		AgentJson::PairInt(TEXT("slate_user"), SlateUser.GetValue())});
}

// ==================== 光标原子接口 ====================

FString UAgentSlateDriverFunctionLib::UsePlatformCursorForCursorUser(bool bUsePlatformCursor)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	FSlateApplication& SlateApp = FSlateApplication::Get();
	const FVector2D Position = SlateApp.GetCursorPos();
	const TSharedPtr<ICursor> PlatformCursor = SlateApp.GetPlatformCursor();
	if (!PlatformCursor.IsValid())
	{
		return SDResult(false, TEXT("Platform cursor is unavailable"));
	}
	const int32 CursorType = static_cast<int32>(PlatformCursor->GetType());
	SlateApp.UsePlatformCursorForCursorUser(bUsePlatformCursor);
	return SDResult(true, FString(), {AgentJson::PairRaw(TEXT("pos"), SDPointJson(Position)),
		AgentJson::PairBool(TEXT("visible"), CursorType != static_cast<int32>(EMouseCursor::None))});
}

FString UAgentSlateDriverFunctionLib::SetCursorPosition(float X, float Y)
{
	if (!FSlateApplication::IsInitialized() || !FMath::IsFinite(X) || !FMath::IsFinite(Y))
	{
		return SDResult(false, TEXT("Slate is unavailable or cursor position is invalid"));
	}
	FSlateApplication::Get().SetCursorPos(FVector2D(X, Y));
	return SDResult(true, FString());
}

FString UAgentSlateDriverFunctionLib::SetCursorVisibility(bool bVisible)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const TSharedPtr<FSlateUser> User = FSlateApplication::Get().GetCursorUser();
	if (!User.IsValid())
	{
		return SDResult(false, TEXT("Slate cursor user is unavailable"));
	}
	User->SetCursorVisibility(bVisible);
	return SDResult(true, FString());
}

// 会接收鼠标按下的路径：有捕获时是捕获者路径，否则是光标下的命中路径
static FWidgetPath SDInputPathAt(const FVector2D& Pos)
{
	FSlateApplication& SlateApp = FSlateApplication::Get();
	const uint32 UserIndex = static_cast<uint32>(SlateApp.GetUserIndexForMouse());
	const TSharedPtr<FSlateUser> User = SlateApp.GetUser(UserIndex);
	if (User.IsValid() && User->HasCapture(FSlateApplicationBase::CursorPointerIndex))
	{
		const FPointerEvent Probe = SDMakePointerEvent(Pos, Pos, SDHeldButtons, EKeys::Invalid, 0.0f);
		return User->GetCaptorPath(FSlateApplicationBase::CursorPointerIndex, FWeakWidgetPath::EInterruptedPathHandling::ReturnInvalid, &Probe);
	}
	return SlateApp.LocateWindowUnderMouse(Pos, SlateApp.GetInteractiveTopLevelWindows(), false, UserIndex);
}

// 透明文字允许命中自己的祖先，兄弟节点和遮挡控件仍拒绝
static bool SDHitsTarget(const FWidgetPath& Path, const TSharedPtr<SWidget>& Target, const FVector2D& Pos, FString& HitVia)
{
	HitVia.Empty();
	if (!Path.IsValid() || Path.Widgets.Num() == 0 || !Target.IsValid() || !Target->GetVisibility().IsVisible())
	{
		return false;
	}
	const TSharedPtr<SWidget> Top = Path.Widgets.Last().Widget;
	if (Top == Target || SDIsAncestorOf(Target, Top))
	{
		return true;
	}
	if (Target->GetVisibility().IsHitTestVisible() || !SDIsAncestorOf(Top, Target))
	{
		return false;
	}
	FWidgetPath TargetPath;
	if (!FSlateApplication::Get().GeneratePathToWidgetUnchecked(Target.ToSharedRef(), TargetPath)
		|| !TargetPath.IsValid() || !TargetPath.Widgets.Last().Geometry.IsUnderLocation(Pos))
	{
		return false;
	}
	FSlateClippingManager Clipping;
	for (int32 Index = 0; Index < TargetPath.Widgets.Num(); ++Index)
	{
		const TSharedRef<SWidget>& Widget = TargetPath.Widgets[Index].Widget;
		if (!Widget->IsEnabled() || !Widget->GetVisibility().IsVisible())
		{
			return false;
		}
		SDPushClip(TargetPath.Widgets[Index], Clipping);
	}
	const TOptional<FSlateClippingState> State = Clipping.GetActiveClippingState();
	if (State.IsSet() && !State->IsPointInside(Pos))
	{
		return false;
	}
	HitVia = SDFindOwnerName(Top);
	if (HitVia.IsEmpty())
	{
		HitVia = Top->GetTypeAsString();
	}
	return true;
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSDClippingTest, "AgentTools.Slate.Clipping", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FSDClippingTest::RunTest(const FString& Parameters)
{
	const TSharedRef<STextBlock> Text = SNew(STextBlock).Text(FText::FromString(TEXT("ClipTarget"))).Visibility(EVisibility::HitTestInvisible);
	const FSDLocator Locator = SDParseLocator(TEXT("text=ClipTarget"));
	FSlateClippingManager Clipping;
	Clipping.PushClip(FSlateClippingZone(FSlateRect(0, 0, 100, 100)));
	const FArrangedWidget Partial(Text, FGeometry::MakeRoot(FVector2D(80, 100), FSlateLayoutTransform(FVector2D(10, 80))));
	TArray<FSDMatch> Matches;
	SDFindNode(Partial, Clipping, Locator, FString(), Matches);
	TestEqual(TEXT("Partially clipped target remains queryable"), Matches.Num(), 1);
	if (Matches.Num() == 1)
	{
		TestTrue(TEXT("Partial clipping is marked"), Matches[0].bClipped);
		TestEqual(TEXT("Visible bottom uses parent clip"), Matches[0].VisibleRect.Bottom, 100.0f);
	}
	const FArrangedWidget Outside(Text, FGeometry::MakeRoot(FVector2D(80, 100), FSlateLayoutTransform(FVector2D(10, 120))));
	Matches.Reset();
	SDFindNode(Outside, Clipping, Locator, FString(), Matches);
	TestEqual(TEXT("Fully clipped target is excluded"), Matches.Num(), 0);
	SDFindNode(Outside, Clipping, Locator, FString(), Matches, true);
	TestEqual(TEXT("Diagnostic query retains clipped target"), Matches.Num(), 1);
	if (Matches.Num() == 1)
	{
		TestTrue(TEXT("Diagnostic target is clipped and query-only"), Matches[0].bClipped && Matches[0].bQueryOnly);
		TestEqual(TEXT("Fully clipped target has no visible height"), Matches[0].VisibleRect.Bottom - Matches[0].VisibleRect.Top, 0.0f);
	}
	Text->SetClipping(EWidgetClipping::ClipToBoundsWithoutIntersecting);
	Matches.Reset();
	SDFindNode(Outside, Clipping, Locator, FString(), Matches);
	TestEqual(TEXT("WithoutIntersecting resets ordinary parent clip"), Matches.Num(), 1);
	TestEqual(TEXT("Traversal restores parent clip stack"), Clipping.GetStackDepth(), 1);
	Clipping.ResetClippingState();
	FSlateClippingZone Always(FSlateRect(0, 0, 100, 100));
	Always.SetAlwaysClip(true);
	Clipping.PushClip(Always);
	Matches.Reset();
	SDFindNode(Outside, Clipping, Locator, FString(), Matches);
	TestEqual(TEXT("AlwaysClip cannot be escaped"), Matches.Num(), 0);
	Text->SetClipping(EWidgetClipping::Inherit);

	const TSharedRef<SBorder> Border = SNew(SBorder).Padding(FMargin(0, 120, 0, -120)).Clipping(EWidgetClipping::ClipToBounds)[Text];
	const TSharedRef<SWindow> Window = SNew(SWindow).ClientSize(FVector2D(200, 100)).CreateTitleBar(false).SupportsMaximize(false).SupportsMinimize(false)[Border];
	FSlateApplication::Get().AddWindow(Window, false);
	ON_SCOPE_EXIT
	{
		FSlateApplication::Get().RequestDestroyWindow(Window);
	};
	Window->SlatePrepass();
	FWidgetPath TargetPath;
	if (!TestTrue(TEXT("Fixture target has an arranged path"), FSlateApplication::Get().GeneratePathToWidgetUnchecked(Text, TargetPath)))
	{
		return false;
	}
	const FWidgetPath AncestorPath = TargetPath.GetPathDownTo(Window);
	const FGeometry& Geometry = TargetPath.Widgets.Last().Geometry;
	const FVector2D Pos = Geometry.LocalToAbsolute(Geometry.GetLocalSize() * 0.5f);
	FString HitVia;
	TestFalse(TEXT("Clipped transparent target cannot fall through to an ancestor"), SDHitsTarget(AncestorPath, Text, Pos, HitVia));
	Border->SetPadding(FMargin(0));
	FSlateApplication::Get().GeneratePathToWidgetUnchecked(Text, TargetPath);
	const FGeometry& VisibleGeometry = TargetPath.Widgets.Last().Geometry;
	const FVector2D VisiblePos = VisibleGeometry.LocalToAbsolute(VisibleGeometry.GetLocalSize() * 0.5f);
	TestTrue(TEXT("Visible transparent target retains ancestor routing"), SDHitsTarget(AncestorPath, Text, VisiblePos, HitVia));
	Border->SetEnabled(false);
	TestFalse(TEXT("Disabled ancestor still rejects input"), SDHitsTarget(AncestorPath, Text, VisiblePos, HitVia));
	TestFalse(TEXT("Unrelated target still rejects input"), SDHitsTarget(AncestorPath, SNew(STextBlock), VisiblePos, HitVia));
	TestTrue(TEXT("Contains operator remains literal"), SDMatchLocator(SDMakeInfo(Partial), SDParseLocator(TEXT("text~=Target"))));
	TestFalse(TEXT("Contains operator is not a regex"), SDMatchLocator(SDMakeInfo(Partial), SDParseLocator(TEXT("text~=^ClipTarget$"))));
	return true;
}
#endif

static FString SDPathHitJson(const FWidgetPath& Path)
{
	if (!Path.IsValid() || Path.Widgets.Num() == 0)
	{
		return TEXT("null");
	}
	const FArrangedWidget& Top = Path.Widgets.Last();
	return SDDescribeWidget(Top.Widget, Top.Geometry);
}

static bool SDResolveMatch(const FString& Locator, const FString& WindowFilter, int32 MatchIndex, TArray<FString>& ExtraFields, FSDMatch& OutMatch, FString& OutError)
{
	const FSDLocator ParsedLocator = SDParseLocator(Locator);
	if (ParsedLocator.IsEmpty())
	{
		OutError = TEXT("Locator is empty");
		return false;
	}
	TArray<FSDMatch> Matches;
	SDFindMatches(ParsedLocator, WindowFilter, Matches);
	ExtraFields.Add(AgentJson::PairInt(TEXT("match_count"), Matches.Num()));
	if (!Matches.IsValidIndex(MatchIndex))
	{
		OutError = FString::Printf(TEXT("No widget at match index %d"), MatchIndex);
		return false;
	}
	OutMatch = Matches[MatchIndex];
	ExtraFields.Add(AgentJson::PairRaw(TEXT("target"), SDMatchJson(OutMatch)));
	return true;
}

// ==================== 文本控件 ====================

static bool SDIsEditableText(const TSharedRef<SWidget>& Widget)
{
	static const FName Type_SEditableText(TEXT("SEditableText"));
	static const FName Type_SEditableTextBox(TEXT("SEditableTextBox"));
	static const FName Type_SMultiLineEditableText(TEXT("SMultiLineEditableText"));
	static const FName Type_SMultiLineEditableTextBox(TEXT("SMultiLineEditableTextBox"));
	const FName Type = Widget->GetType();
	return Type == Type_SEditableText || Type == Type_SEditableTextBox || Type == Type_SMultiLineEditableText || Type == Type_SMultiLineEditableTextBox;
}

// 命中的控件本身不接受焦点时（如外层容器），往下找第一个可编辑控件
static TSharedPtr<SWidget> SDFindEditableChild(const TSharedRef<SWidget>& Widget, int32 Depth = 0)
{
	if (SDIsEditableText(Widget))
	{
		return Widget;
	}
	if (Depth >= 4 || !Widget->GetChildren())
	{
		return nullptr;
	}
	for (int32 Index = 0; Index < Widget->GetChildren()->Num(); ++Index)
	{
		if (const TSharedPtr<SWidget> Found = SDFindEditableChild(Widget->GetChildren()->GetChildAt(Index), Depth + 1))
		{
			return Found;
		}
	}
	return nullptr;
}

static void SDSelectAllText(const TSharedRef<SWidget>& Widget)
{
	static const FName Type_SEditableText(TEXT("SEditableText"));
	static const FName Type_SEditableTextBox(TEXT("SEditableTextBox"));
	static const FName Type_SMultiLineEditableText(TEXT("SMultiLineEditableText"));
	static const FName Type_SMultiLineEditableTextBox(TEXT("SMultiLineEditableTextBox"));
	const FName Type = Widget->GetType();
	if (Type == Type_SEditableText)
	{
		StaticCastSharedRef<SEditableText>(Widget)->SelectAllText();
	}
	else if (Type == Type_SEditableTextBox)
	{
		StaticCastSharedRef<SEditableTextBox>(Widget)->SelectAllText();
	}
	else if (Type == Type_SMultiLineEditableText)
	{
		StaticCastSharedRef<SMultiLineEditableText>(Widget)->SelectAllText();
	}
	else if (Type == Type_SMultiLineEditableTextBox)
	{
		StaticCastSharedRef<SMultiLineEditableTextBox>(Widget)->SelectAllText();
	}
}

// ==================== 焦点与文本 ====================

FString UAgentSlateDriverFunctionLib::FocusWidget(const FString& Locator, const FString& WindowFilter, int32 MatchIndex)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	TArray<FString> ExtraFields;
	FSDMatch Match;
	FString Error;
	if (!SDResolveMatch(Locator, WindowFilter, MatchIndex, ExtraFields, Match, Error))
	{
		return SDResult(false, Error, ExtraFields);
	}
	const TSharedRef<SWidget> Widget = Match.Widget.ToSharedRef();
	const TSharedPtr<SWidget> Focusable = Widget->SupportsKeyboardFocus() ? TSharedPtr<SWidget>(Widget) : SDFindEditableChild(Widget);
	if (!Focusable.IsValid() || !Focusable->SupportsKeyboardFocus())
	{
		return SDResult(false, TEXT("Widget does not support keyboard focus and has no editable child"), ExtraFields);
	}
	ExtraFields.Add(AgentJson::PairRaw(TEXT("focusable"), SDDescribeWidget(Focusable, Focusable->GetTickSpaceGeometry())));
	// 直接设焦点，不依赖点击路由（编辑器不在前台时点击可能拿不到焦点）
	const TWeakPtr<SWidget> WeakFocusable = Focusable;
	const int32 RequestId = SDTimelineAdd([WeakFocusable](int32 Id)
	{
		const TSharedPtr<SWidget> Target = WeakFocusable.Pin();
		if (!Target.IsValid())
		{
			SDSetInputResult(Id, false, TEXT("Widget was destroyed before focus"));
			return ESDStep::Failed;
		}
		FSlateApplication::Get().SetKeyboardFocus(Target, EFocusCause::SetDirectly);
		return ESDStep::Done;
	});
	return SDQueued(RequestId, ExtraFields);
}

FString UAgentSlateDriverFunctionLib::SelectAllText()
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const int32 RequestId = SDTimelineAdd([](int32 Id)
	{
		const TSharedPtr<SWidget> Focused = FSlateApplication::Get().GetKeyboardFocusedWidget();
		if (!Focused.IsValid() || !SDIsEditableText(Focused.ToSharedRef()))
		{
			SDSetInputResult(Id, false, TEXT("Keyboard focus is not an editable text widget"), {AgentJson::PairRaw(TEXT("focus"), SDDescribeFocus())});
			return ESDStep::Failed;
		}
		SDSelectAllText(Focused.ToSharedRef());
		return ESDStep::Done;
	});
	return SDQueued(RequestId);
}

FString UAgentSlateDriverFunctionLib::TypeText(const FString& Text)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const int32 RequestId = SDTimelineAdd([Text](int32 Id)
	{
		FSlateApplication& SlateApp = FSlateApplication::Get();
		const uint32 UserIndex = static_cast<uint32>(SlateApp.GetUserIndexForKeyboard());
		for (const TCHAR Character : Text)
		{
			SlateApp.ProcessKeyCharEvent(FCharacterEvent(Character, FModifierKeysState(), UserIndex, false));
		}
		SDSetInputResult(Id, true, FString(), {AgentJson::PairRaw(TEXT("focus"), SDDescribeFocus())});
		return ESDStep::Done;
	});
	return SDQueued(RequestId, {AgentJson::PairRaw(TEXT("focus"), SDDescribeFocus())});
}

// ==================== 键盘 ====================

FString UAgentSlateDriverFunctionLib::KeyDown(const FString& KeyName, bool bCtrl, bool bShift, bool bAlt, float MaxHoldSeconds)
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
	if (Key.IsMouseButton())
	{
		return SDResult(false, TEXT("Mouse buttons go through MouseDown"));
	}
	if (Key.IsGamepadKey() && Key.IsAnalog())
	{
		return SDResult(false, TEXT("Gamepad axes go through AnalogInput"));
	}
	const int32 RequestId = SDTimelineAdd([Key, bCtrl, bShift, bAlt, MaxHoldSeconds](int32 Id)
	{
		if (SDHeldKeys.Contains(Key))
		{
			SDSetInputResult(Id, false, TEXT("Key is already held; release it first"));
			return ESDStep::Failed;
		}
		FSlateApplication& SlateApp = FSlateApplication::Get();
		const FKeyEvent Event = SDMakeKeyEvent(Key, bCtrl, bShift, bAlt);
		const bool bHandled = SlateApp.ProcessKeyDownEvent(Event);
		// 普通退格由字符事件处理，Ctrl/Alt 组合由按键事件处理
		if (Key == EKeys::BackSpace && !bCtrl && !bAlt)
		{
			SlateApp.ProcessKeyCharEvent(FCharacterEvent(TCHAR(8), Event.GetModifierKeys(), Event.GetUserIndex(), false));
		}
		SDHeldKeys.Add(Key, Event);
		const int32 Serial = ++SDNextHoldSerial;
		SDHoldSerials.Add(Key, Serial);
		SDArmWatchdog(Key, Serial, MaxHoldSeconds);
		SDSetInputResult(Id, true, FString(), {AgentJson::PairBool(TEXT("handled"), bHandled),
			AgentJson::PairInt(TEXT("device_id"), Event.GetInputDeviceId().GetId()),
			AgentJson::PairInt(TEXT("platform_user"), Event.GetPlatformUserId().GetInternalId()),
			AgentJson::PairInt(TEXT("slate_user"), static_cast<int32>(Event.GetUserIndex()))});
		return ESDStep::Done;
	});
	return SDQueued(RequestId, {AgentJson::PairRaw(TEXT("focus"), SDDescribeFocus())});
}

FString UAgentSlateDriverFunctionLib::KeyUp(const FString& KeyName)
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
	const int32 RequestId = SDTimelineAdd([Key](int32 Id)
	{
		if (!SDHeldKeys.Contains(Key))
		{
			SDSetInputResult(Id, false, TEXT("Key is not held by AgentTools (already released, or auto released after MaxHoldSeconds)"));
			return ESDStep::Failed;
		}
		SDReleaseKey(Key);
		return ESDStep::Done;
	});
	return SDQueued(RequestId);
}

// ==================== 鼠标 ====================

FString UAgentSlateDriverFunctionLib::MouseDown(float X, float Y, const FString& Button, bool bDoubleClick, const FString& CheckLocator, const FString& WindowFilter, int32 MatchIndex, float MaxHoldSeconds)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FKey ButtonKey = SDParseMouseButton(Button);
	if (!ButtonKey.IsValid())
	{
		return SDResult(false, FString::Printf(TEXT("Unknown mouse button: %s"), *Button));
	}
	const FVector2D Pos(X, Y);
	const bool bCheck = !CheckLocator.IsEmpty();
	TWeakPtr<SWidget> Check;
	TArray<FString> ExtraFields;
	if (bCheck)
	{
		FSDMatch Match;
		FString Error;
		if (!SDResolveMatch(CheckLocator, WindowFilter, MatchIndex, ExtraFields, Match, Error))
		{
			return SDResult(false, Error, ExtraFields);
		}
		Check = Match.Widget;
	}
	ExtraFields.Add(AgentJson::PairRaw(TEXT("pos"), SDPointJson(Pos)));
	ExtraFields.Add(AgentJson::PairRaw(TEXT("hit"), SDDescribeHit(Pos)));
	const int32 RequestId = SDTimelineAdd([ButtonKey, Pos, bDoubleClick, bCheck, Check, MaxHoldSeconds](int32 Id)
	{
		if (SDHeldButtons.Contains(ButtonKey))
		{
			SDSetInputResult(Id, false, TEXT("Mouse button is already held; release it first"));
			return ESDStep::Failed;
		}
		FString HitVia;
		auto CheckPath = [&](const FWidgetPath& Path)
		{
			if (!Path.IsValid())
			{
				SDSetInputResult(Id, false, TEXT("No window under the pointer"));
				return false;
			}
			if (!bCheck)
			{
				return true;
			}
			const TSharedPtr<SWidget> Target = Check.Pin();
			if (Target.IsValid() && !Target->IsEnabled())
			{
				SDSetInputResult(Id, false, TEXT("Target is disabled; no mouse down was sent"), {AgentJson::PairRaw(TEXT("hit"), SDPathHitJson(Path))});
				return false;
			}
			if (!SDHitsTarget(Path, Target, Pos, HitVia))
			{
				SDSetInputResult(Id, false, TEXT("Target check failed: the press point is outside the target path or covered; no mouse down was sent"),
					{AgentJson::PairRaw(TEXT("hit"), SDPathHitJson(Path))});
				return false;
			}
			return true;
		};
		FSlateApplication& SlateApp = FSlateApplication::Get();
		if (!CheckPath(SDInputPathAt(Pos)))
		{
			return ESDStep::Failed;
		}
		// 先把指针移到落点：悬停或捕获可能因此变化，再查一次才按下
		SlateApp.ProcessMouseMoveEvent(SDMakePointerEvent(Pos, SDPointer(), SDHeldButtons, EKeys::Invalid, 0.0f));
		SDPointerPos = Pos;
		const FWidgetPath Path = SDInputPathAt(Pos);
		if (!CheckPath(Path))
		{
			return ESDStep::Failed;
		}
		SDHeldButtons.Add(ButtonKey);
		SDSuppressSyntheticMoves(true);
		const FPointerEvent Event = SDMakePointerEvent(Pos, Pos, SDHeldButtons, ButtonKey, 0.0f);
		if (bDoubleClick)
		{
			SlateApp.ProcessMouseButtonDoubleClickEvent(Path.GetWindow()->GetNativeWindow(), Event);
		}
		else
		{
			SlateApp.ProcessMouseButtonDownEvent(Path.GetWindow()->GetNativeWindow(), Event);
		}
		const int32 Serial = ++SDNextHoldSerial;
		SDHoldSerials.Add(ButtonKey, Serial);
		SDArmWatchdog(ButtonKey, Serial, MaxHoldSeconds);
		TArray<FString> Fields = {AgentJson::PairRaw(TEXT("hit"), SDPathHitJson(Path))};
		if (!HitVia.IsEmpty())
		{
			Fields.Add(AgentJson::Pair(TEXT("hit_via"), HitVia));
		}
		SDSetInputResult(Id, true, FString(), Fields);
		return ESDStep::Done;
	});
	return SDQueued(RequestId, ExtraFields);
}

FString UAgentSlateDriverFunctionLib::MouseUp(const FString& Button)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FKey ButtonKey = SDParseMouseButton(Button);
	if (!ButtonKey.IsValid())
	{
		return SDResult(false, FString::Printf(TEXT("Unknown mouse button: %s"), *Button));
	}
	const int32 RequestId = SDTimelineAdd([ButtonKey](int32 Id)
	{
		if (!SDHeldButtons.Contains(ButtonKey))
		{
			SDSetInputResult(Id, false, TEXT("Mouse button is not held by AgentTools (already released, or auto released after MaxHoldSeconds)"));
			return ESDStep::Failed;
		}
		const FVector2D Pos = SDPointer();
		SDReleaseButton(ButtonKey);
		SDSetInputResult(Id, true, FString(), {AgentJson::PairRaw(TEXT("pos"), SDPointJson(Pos)), AgentJson::PairRaw(TEXT("hit"), SDDescribeHit(Pos))});
		return ESDStep::Done;
	});
	return SDQueued(RequestId);
}

FString UAgentSlateDriverFunctionLib::MouseMove(float X, float Y, int32 Frames)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FVector2D To(X, Y);
	const int32 StepCount = FMath::Max(1, Frames);
	const TSharedRef<FVector2D> From = MakeShared<FVector2D>(FVector2D::ZeroVector);
	const TSharedRef<int32> Step = MakeShared<int32>(0);
	const int32 RequestId = SDTimelineAdd([To, StepCount, From, Step](int32 Id)
	{
		// 起点在执行时取：前面排着的按下/移动完成后才知道指针在哪
		if (*Step == 0)
		{
			*From = SDPointer();
		}
		++*Step;
		const FVector2D Last = SDPointer();
		const FVector2D Pos = FMath::Lerp(*From, To, static_cast<double>(*Step) / StepCount);
		SDKeepHover();
		FSlateApplication::Get().ProcessMouseMoveEvent(SDMakePointerEvent(Pos, Last, SDHeldButtons, EKeys::Invalid, 0.0f));
		SDPointerPos = Pos;
		if (*Step < StepCount)
		{
			return ESDStep::Running;
		}
		SDSetInputResult(Id, true, FString(), {AgentJson::PairRaw(TEXT("pos"), SDPointJson(Pos)), AgentJson::PairRaw(TEXT("hit"), SDDescribeHit(Pos)),
			AgentJson::PairBool(TEXT("dragging"), SDHeldButtons.Num() > 0), AgentJson::PairInt(TEXT("hover_seconds"), static_cast<int32>(SDHoverSeconds))});
		return ESDStep::Done;
	});
	return SDQueued(RequestId);
}

FString UAgentSlateDriverFunctionLib::MouseWheel(float X, float Y, float Delta)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const FVector2D Pos(X, Y);
	const int32 RequestId = SDTimelineAdd([Pos, Delta](int32 Id)
	{
		FSlateApplication& SlateApp = FSlateApplication::Get();
		SlateApp.ProcessMouseMoveEvent(SDMakePointerEvent(Pos, SDPointer(), SDHeldButtons, EKeys::Invalid, 0.0f));
		SDPointerPos = Pos;
		const bool bHandled = SlateApp.ProcessMouseWheelOrGestureEvent(SDMakePointerEvent(Pos, Pos, SDHeldButtons, EKeys::Invalid, Delta), nullptr);
		SDSetInputResult(Id, true, bHandled ? FString() : FString(TEXT("No widget handled the wheel event at this point")), {AgentJson::PairBool(TEXT("handled"), bHandled)});
		return ESDStep::Done;
	});
	return SDQueued(RequestId, {AgentJson::PairRaw(TEXT("pos"), SDPointJson(Pos)), AgentJson::PairRaw(TEXT("hit"), SDDescribeHit(Pos))});
}

// ==================== 等待与释放 ====================

FString UAgentSlateDriverFunctionLib::WaitInput(float Seconds, int32 Frames)
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const TSharedRef<double> Start = MakeShared<double>(-1.0);
	const TSharedRef<uint64> StartFrame = MakeShared<uint64>(0);
	const int32 RequestId = SDTimelineAdd([Seconds, Frames, Start, StartFrame](int32)
	{
		if (*Start < 0.0)
		{
			*Start = FPlatformTime::Seconds();
			*StartFrame = GFrameCounter;
		}
		const bool bTimeUp = FPlatformTime::Seconds() - *Start >= Seconds;
		const bool bFramesUp = GFrameCounter - *StartFrame >= static_cast<uint64>(FMath::Max(0, Frames));
		return bTimeUp && bFramesUp ? ESDStep::Done : ESDStep::Running;
	});
	return SDQueued(RequestId);
}

FString UAgentSlateDriverFunctionLib::ReleaseAllInput()
{
	if (!FSlateApplication::IsInitialized())
	{
		return SDResult(false, TEXT("Slate is not initialized"));
	}
	const int32 RequestId = SDRegisterInput();
	// 不排进时间线：时间线上可能正有一步在等待，紧急释放要立即生效
	SDQueueInput([RequestId]()
	{
		SDCancelTimeline(TEXT("Cancelled by ReleaseAllInput"));
		TArray<FString> Released;
		TArray<FKey> Keys;
		SDHeldKeys.GetKeys(Keys);
		Keys.Append(SDHeldButtons.Array());
		for (const FKey& Key : Keys)
		{
			Released.Add(TEXT("\"") + AgentJson::EscapeString(Key.GetFName().ToString()) + TEXT("\""));
			if (Key.IsMouseButton())
			{
				SDReleaseButton(Key);
			}
			else
			{
				SDReleaseKey(Key);
			}
		}
		SDSetInputResult(RequestId, true, FString(), {AgentJson::PairRaw(TEXT("released"), AgentJson::Array(Released))});
	});
	return SDQueued(RequestId);
}

FString UAgentSlateDriverFunctionLib::GetInputResult(int32 RequestId)
{
	if (const FString* Result = SDInputResults.Find(RequestId))
	{
		return *Result;
	}
	return SDResult(false, TEXT("Unknown or expired input request"), {AgentJson::PairBool(TEXT("pending"), false)});
}

FString UAgentSlateDriverFunctionLib::WidgetAt(float X, float Y)
{
	if (!FSlateApplication::IsInitialized())
	{
		return TEXT("null");
	}
	return SDDescribeHit(FVector2D(X, Y));
}
