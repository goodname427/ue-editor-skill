// Fill out your copyright notice in the Description page of Project Settings.

#include "AgentWidgetBlueprintInfoFunctionLib.h"

#include "WidgetBlueprint.h"
#include "Blueprint/UserWidget.h"
#include "Blueprint/WidgetTree.h"
#include "Blueprint/WidgetBlueprintGeneratedClass.h"
#include "Components/Widget.h"
#include "Components/PanelWidget.h"
#include "Components/PanelSlot.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/OverlaySlot.h"
#include "Components/GridSlot.h"
#include "Components/SizeBox.h"
#include "Components/NamedSlot.h"
#include "Animation/WidgetAnimation.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Engine/Blueprint.h"
#include "EdGraph/EdGraph.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_FunctionEntry.h"
#include "K2Node_Event.h"
#include "K2Node_CustomEvent.h"
#include "MovieScene.h"
#include "Tracks/MovieScenePropertyTrack.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "K2Node_EditablePinBase.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "AgentJson.h"

UWidgetBlueprint* UAgentWidgetBlueprintInfoFunctionLib::LoadWidgetBlueprint(const FString& AssetPath)
{
	FString FullPath = AssetPath;
	// 如果路径不包含类型后缀，自动补全
	if (!FullPath.Contains(TEXT(".")))
	{
		FString AssetName = FPackageName::GetShortName(FullPath);
		FullPath = FullPath + TEXT(".") + AssetName;
	}
	UObject* Asset = StaticLoadObject(UWidgetBlueprint::StaticClass(), nullptr, *FullPath);
	return Cast<UWidgetBlueprint>(Asset);
}

UWidget* UAgentWidgetBlueprintInfoFunctionLib::FindWidgetInTree(UWidgetBlueprint* WidgetBP, const FString& WidgetName)
{
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return nullptr;
	}
	return WidgetBP->WidgetTree->FindWidget(FName(*WidgetName));
}

// ==================== Widget蓝图基础信息 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetBlueprintInfo(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

	UClass* GenClass = WidgetBP->GeneratedClass;
	FString ParentClassName = GenClass && GenClass->GetSuperClass() ? GenClass->GetSuperClass()->GetName() : TEXT("None");
	FString BlueprintName = WidgetBP->GetName();
	FString BlueprintPath = WidgetBP->GetPathName();

	int32 WidgetCount = 0;
	if (WidgetBP->WidgetTree)
	{
		TArray<UWidget*> AllWidgets;
		WidgetBP->WidgetTree->GetAllWidgets(AllWidgets);
		WidgetCount = AllWidgets.Num();
	}

	int32 AnimCount = 0;
#if WITH_EDITORONLY_DATA
	AnimCount = WidgetBP->Animations.Num();
#endif

	int32 BindingCount = 0;
#if WITH_EDITORONLY_DATA
	BindingCount = WidgetBP->Bindings.Num();
#endif

	int32 FuncCount = WidgetBP->FunctionGraphs.Num();

	TArray<FString> Pairs;
	Pairs.Add(AgentJson::Pair(TEXT("name"), BlueprintName));
	Pairs.Add(AgentJson::Pair(TEXT("path"), BlueprintPath));
	Pairs.Add(AgentJson::Pair(TEXT("parent_class"), ParentClassName));
	Pairs.Add(AgentJson::PairInt(TEXT("widget_count"), WidgetCount));
	Pairs.Add(AgentJson::PairInt(TEXT("animation_count"), AnimCount));
	Pairs.Add(AgentJson::PairInt(TEXT("binding_count"), BindingCount));
	Pairs.Add(AgentJson::PairInt(TEXT("function_count"), FuncCount));

	FString RootWidgetType = TEXT("None");
	if (WidgetBP->WidgetTree && WidgetBP->WidgetTree->RootWidget)
	{
		RootWidgetType = WidgetBP->WidgetTree->RootWidget->GetClass()->GetName();
	}
	Pairs.Add(AgentJson::Pair(TEXT("root_widget_type"), RootWidgetType));

	return AgentJson::Object(Pairs);
}

// ==================== WidgetTree 层级结构 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::BuildWidgetTreeJson(UWidget* Widget, UWidgetTree* WidgetTree)
{
	if (!Widget)
	{
		return TEXT("null");
	}

	TArray<FString> Pairs;
	Pairs.Add(AgentJson::Pair(TEXT("name"), Widget->GetName()));
	Pairs.Add(AgentJson::Pair(TEXT("type"), Widget->GetClass()->GetName()));
	Pairs.Add(AgentJson::Pair(TEXT("visibility"), UEnum::GetValueAsString(Widget->GetVisibility())));
	Pairs.Add(AgentJson::PairBool(TEXT("is_variable"), Widget->bIsVariable));

	UPanelWidget* PanelWidget = Cast<UPanelWidget>(Widget);
	if (PanelWidget)
	{
		TArray<FString> ChildrenJson;
		for (int32 i = 0; i < PanelWidget->GetChildrenCount(); ++i)
		{
			UWidget* Child = PanelWidget->GetChildAt(i);
			if (Child)
			{
				ChildrenJson.Add(BuildWidgetTreeJson(Child, WidgetTree));
			}
		}
		Pairs.Add(AgentJson::PairRaw(TEXT("children"), AgentJson::Array(ChildrenJson)));
	}

	return AgentJson::Object(Pairs);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetTreeHierarchy(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint or WidgetTree is null\"}");
	}

	UWidget* RootWidget = WidgetBP->WidgetTree->RootWidget;
	return BuildWidgetTreeJson(RootWidget, WidgetBP->WidgetTree);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetAllWidgetsFlat(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return TEXT("[]");
	}

	TArray<UWidget*> AllWidgets;
	WidgetBP->WidgetTree->GetAllWidgets(AllWidgets);

	TArray<FString> Items;
	for (UWidget* Widget : AllWidgets)
	{
		if (!Widget) continue;

		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), Widget->GetName()));
		Pairs.Add(AgentJson::Pair(TEXT("type"), Widget->GetClass()->GetName()));
		Pairs.Add(AgentJson::PairBool(TEXT("is_variable"), Widget->bIsVariable));
		Pairs.Add(AgentJson::Pair(TEXT("visibility"), UEnum::GetValueAsString(Widget->GetVisibility())));

		// 获取父Widget名称
		int32 ChildIndex = INDEX_NONE;
		UPanelWidget* Parent = UWidgetTree::FindWidgetParent(Widget, ChildIndex);
		Pairs.Add(AgentJson::Pair(TEXT("parent"), Parent ? Parent->GetName() : TEXT("")));
		Pairs.Add(AgentJson::PairInt(TEXT("child_index"), ChildIndex));

		Items.Add(AgentJson::Object(Pairs));
	}

	return AgentJson::Array(Items);
}

// ==================== 单个Widget详细信息 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::WidgetToJsonObject(UWidget* Widget, bool bDetailed)
{
	if (!Widget)
	{
		return TEXT("null");
	}

	TArray<FString> Pairs;
	Pairs.Add(AgentJson::Pair(TEXT("name"), Widget->GetName()));
	Pairs.Add(AgentJson::Pair(TEXT("type"), Widget->GetClass()->GetName()));
	Pairs.Add(AgentJson::Pair(TEXT("visibility"), UEnum::GetValueAsString(Widget->GetVisibility())));
	Pairs.Add(AgentJson::PairBool(TEXT("is_variable"), Widget->bIsVariable));
	Pairs.Add(AgentJson::PairBool(TEXT("is_enabled"), Widget->GetIsEnabled()));

	// RenderTransform
	FWidgetTransform Transform = Widget->GetRenderTransform();
	FString TransformJson = FString::Printf(
		TEXT("{\"translation\":[%.2f,%.2f],\"scale\":[%.2f,%.2f],\"shear\":[%.2f,%.2f],\"angle\":%.2f}"),
		Transform.Translation.X, Transform.Translation.Y,
		Transform.Scale.X, Transform.Scale.Y,
		Transform.Shear.X, Transform.Shear.Y,
		Transform.Angle
	);
	Pairs.Add(AgentJson::PairRaw(TEXT("render_transform"), TransformJson));
	Pairs.Add(AgentJson::PairFloat(TEXT("render_opacity"), Widget->GetRenderOpacity()));

	// ToolTipText
	Pairs.Add(AgentJson::Pair(TEXT("tool_tip_text"), Widget->GetToolTipText().ToString()));

	if (bDetailed)
	{
		// 列出该Widget类的所有UPROPERTY
		TArray<FString> PropItems;
		for (TFieldIterator<FProperty> PropIt(Widget->GetClass()); PropIt; ++PropIt)
		{
			FProperty* Prop = *PropIt;
			if (!Prop->HasAnyPropertyFlags(CPF_Edit | CPF_BlueprintVisible))
			{
				continue;
			}

			FString PropValue;
			const void* ValuePtr = Prop->ContainerPtrToValuePtr<void>(Widget);
			Prop->ExportTextItem_Direct(PropValue, ValuePtr, nullptr, Widget, PPF_None);

			TArray<FString> PropPairs;
			PropPairs.Add(AgentJson::Pair(TEXT("name"), Prop->GetName()));
			PropPairs.Add(AgentJson::Pair(TEXT("type"), Prop->GetCPPType()));
			PropPairs.Add(AgentJson::Pair(TEXT("value"), PropValue));
			PropItems.Add(AgentJson::Object(PropPairs));
		}
		Pairs.Add(AgentJson::PairRaw(TEXT("properties"), AgentJson::Array(PropItems)));
	}

	// Slot信息
	Pairs.Add(AgentJson::PairRaw(TEXT("slot"), GetSlotInfoJson(Widget)));

	// 子Widget数量（如果是PanelWidget）
	UPanelWidget* PanelWidget = Cast<UPanelWidget>(Widget);
	if (PanelWidget)
	{
		Pairs.Add(AgentJson::PairInt(TEXT("children_count"), PanelWidget->GetChildrenCount()));
	}

	return AgentJson::Object(Pairs);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetDetailInfo(const FString& AssetPath, const FString& WidgetName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

	UWidget* Widget = FindWidgetInTree(WidgetBP, WidgetName);
	if (!Widget)
	{
		return TEXT("{\"error\":\"Widget not found in WidgetTree\"}");
	}

	return WidgetToJsonObject(Widget, true);
}

// ==================== Slot信息 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetSlotInfoJson(UWidget* Widget)
{
	if (!Widget || !Widget->Slot)
	{
		return TEXT("null");
	}

	UPanelSlot* Slot = Widget->Slot;
	TArray<FString> Pairs;
	Pairs.Add(AgentJson::Pair(TEXT("slot_type"), Slot->GetClass()->GetName()));

	// CanvasPanelSlot
	if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(Slot))
	{
		FAnchorData LayoutData = CanvasSlot->GetLayout();
		FAnchors Anchors = LayoutData.Anchors;

		Pairs.Add(AgentJson::PairRaw(TEXT("anchors"), FString::Printf(
			TEXT("{\"minimum\":[%.4f,%.4f],\"maximum\":[%.4f,%.4f]}"),
			Anchors.Minimum.X, Anchors.Minimum.Y,
			Anchors.Maximum.X, Anchors.Maximum.Y
		)));
		Pairs.Add(AgentJson::PairRaw(TEXT("offset"), FString::Printf(
			TEXT("{\"left\":%.2f,\"top\":%.2f,\"right\":%.2f,\"bottom\":%.2f}"),
			LayoutData.Offsets.Left, LayoutData.Offsets.Top,
			LayoutData.Offsets.Right, LayoutData.Offsets.Bottom
		)));
		Pairs.Add(AgentJson::PairRaw(TEXT("alignment"), FString::Printf(
			TEXT("[%.4f,%.4f]"),
			LayoutData.Alignment.X, LayoutData.Alignment.Y
		)));
		Pairs.Add(AgentJson::PairBool(TEXT("auto_size"), CanvasSlot->GetAutoSize()));
		Pairs.Add(AgentJson::PairInt(TEXT("z_order"), CanvasSlot->GetZOrder()));
	}

	// HorizontalBoxSlot
	if (UHorizontalBoxSlot* HBoxSlot = Cast<UHorizontalBoxSlot>(Slot))
	{
		Pairs.Add(AgentJson::PairRaw(TEXT("padding"), FString::Printf(
			TEXT("{\"left\":%.2f,\"top\":%.2f,\"right\":%.2f,\"bottom\":%.2f}"),
			HBoxSlot->GetPadding().Left, HBoxSlot->GetPadding().Top,
			HBoxSlot->GetPadding().Right, HBoxSlot->GetPadding().Bottom
		)));
		Pairs.Add(AgentJson::PairRaw(TEXT("size"), FString::Printf(
			TEXT("{\"size_rule\":\"%s\",\"value\":%.4f}"),
			*UEnum::GetValueAsString(HBoxSlot->GetSize().SizeRule),
			HBoxSlot->GetSize().Value
		)));
		Pairs.Add(AgentJson::Pair(TEXT("horizontal_alignment"), UEnum::GetValueAsString(HBoxSlot->GetHorizontalAlignment())));
		Pairs.Add(AgentJson::Pair(TEXT("vertical_alignment"), UEnum::GetValueAsString(HBoxSlot->GetVerticalAlignment())));
	}

	// VerticalBoxSlot
	if (UVerticalBoxSlot* VBoxSlot = Cast<UVerticalBoxSlot>(Slot))
	{
		Pairs.Add(AgentJson::PairRaw(TEXT("padding"), FString::Printf(
			TEXT("{\"left\":%.2f,\"top\":%.2f,\"right\":%.2f,\"bottom\":%.2f}"),
			VBoxSlot->GetPadding().Left, VBoxSlot->GetPadding().Top,
			VBoxSlot->GetPadding().Right, VBoxSlot->GetPadding().Bottom
		)));
		Pairs.Add(AgentJson::PairRaw(TEXT("size"), FString::Printf(
			TEXT("{\"size_rule\":\"%s\",\"value\":%.4f}"),
			*UEnum::GetValueAsString(VBoxSlot->GetSize().SizeRule),
			VBoxSlot->GetSize().Value
		)));
		Pairs.Add(AgentJson::Pair(TEXT("horizontal_alignment"), UEnum::GetValueAsString(VBoxSlot->GetHorizontalAlignment())));
		Pairs.Add(AgentJson::Pair(TEXT("vertical_alignment"), UEnum::GetValueAsString(VBoxSlot->GetVerticalAlignment())));
	}

	// OverlaySlot
	if (UOverlaySlot* OvSlot = Cast<UOverlaySlot>(Slot))
	{
		Pairs.Add(AgentJson::PairRaw(TEXT("padding"), FString::Printf(
			TEXT("{\"left\":%.2f,\"top\":%.2f,\"right\":%.2f,\"bottom\":%.2f}"),
			OvSlot->GetPadding().Left, OvSlot->GetPadding().Top,
			OvSlot->GetPadding().Right, OvSlot->GetPadding().Bottom
		)));
		Pairs.Add(AgentJson::Pair(TEXT("horizontal_alignment"), UEnum::GetValueAsString(OvSlot->GetHorizontalAlignment())));
		Pairs.Add(AgentJson::Pair(TEXT("vertical_alignment"), UEnum::GetValueAsString(OvSlot->GetVerticalAlignment())));
	}

	return AgentJson::Object(Pairs);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetSlotInfo(const FString& AssetPath, const FString& WidgetName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

	UWidget* Widget = FindWidgetInTree(WidgetBP, WidgetName);
	if (!Widget)
	{
		return TEXT("{\"error\":\"Widget not found in WidgetTree\"}");
	}

	return GetSlotInfoJson(Widget);
}

// ==================== 变量与属性 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetBlueprintVariables(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;
	for (const FBPVariableDescription& Var : WidgetBP->NewVariables)
	{
		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), Var.VarName.ToString()));
		Pairs.Add(AgentJson::Pair(TEXT("type"), Var.VarType.PinCategory.ToString()));

		FString SubType;
		if (Var.VarType.PinSubCategoryObject.IsValid())
		{
			SubType = Var.VarType.PinSubCategoryObject->GetName();
		}
		else
		{
			SubType = Var.VarType.PinSubCategory.ToString();
		}
		Pairs.Add(AgentJson::Pair(TEXT("sub_type"), SubType));
		Pairs.Add(AgentJson::PairBool(TEXT("is_array"), Var.VarType.IsArray()));
		Pairs.Add(AgentJson::PairBool(TEXT("is_set"), Var.VarType.IsSet()));
		Pairs.Add(AgentJson::PairBool(TEXT("is_map"), Var.VarType.IsMap()));
		Pairs.Add(AgentJson::PairBool(TEXT("instance_editable"), Var.PropertyFlags & CPF_Edit ? true : false));
		Pairs.Add(AgentJson::PairBool(TEXT("blueprint_read_only"), Var.PropertyFlags & CPF_BlueprintReadOnly ? true : false));
		Pairs.Add(AgentJson::Pair(TEXT("category"), Var.Category.ToString()));

		// 默认值
		Pairs.Add(AgentJson::Pair(TEXT("default_value"), Var.DefaultValue));

		Items.Add(AgentJson::Object(Pairs));
	}

	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetVariables(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;
	TArray<UWidget*> AllWidgets;
	WidgetBP->WidgetTree->GetAllWidgets(AllWidgets);

	for (UWidget* Widget : AllWidgets)
	{
		if (!Widget || !Widget->bIsVariable)
		{
			continue;
		}

		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), Widget->GetName()));
		Pairs.Add(AgentJson::Pair(TEXT("type"), Widget->GetClass()->GetName()));

		Items.Add(AgentJson::Object(Pairs));
	}

	return AgentJson::Array(Items);
}

// ==================== 动画信息 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetAnimations(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;

#if WITH_EDITORONLY_DATA
	for (UWidgetAnimation* Anim : WidgetBP->Animations)
	{
		if (!Anim) continue;

		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), Anim->GetName()));

		UMovieScene* MovieScene = Anim->GetMovieScene();
		if (MovieScene)
		{
			FFrameRate TickResolution = MovieScene->GetTickResolution();
			FFrameRate DisplayRate = MovieScene->GetDisplayRate();
			FFrameNumber StartFrame = MovieScene->GetPlaybackRange().GetLowerBoundValue();
			FFrameNumber EndFrame = MovieScene->GetPlaybackRange().GetUpperBoundValue();
			float Duration = TickResolution.AsSeconds(FFrameTime(EndFrame - StartFrame));

			Pairs.Add(AgentJson::PairFloat(TEXT("duration"), Duration));
			Pairs.Add(AgentJson::PairInt(TEXT("track_count"), MovieScene->GetTracks().Num() + MovieScene->GetBindings().Num()));
		}

		Items.Add(AgentJson::Object(Pairs));
	}
#endif

	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetAnimationDetail(const FString& AssetPath, const FString& AnimationName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

#if WITH_EDITORONLY_DATA
	UWidgetAnimation* TargetAnim = nullptr;
	for (UWidgetAnimation* Anim : WidgetBP->Animations)
	{
		if (Anim && Anim->GetName() == AnimationName)
		{
			TargetAnim = Anim;
			break;
		}
	}

	if (!TargetAnim)
	{
		return TEXT("{\"error\":\"Animation not found\"}");
	}

	TArray<FString> Pairs;
	Pairs.Add(AgentJson::Pair(TEXT("name"), TargetAnim->GetName()));

	UMovieScene* MovieScene = TargetAnim->GetMovieScene();
	if (MovieScene)
	{
		FFrameRate TickResolution = MovieScene->GetTickResolution();
		FFrameNumber StartFrame = MovieScene->GetPlaybackRange().GetLowerBoundValue();
		FFrameNumber EndFrame = MovieScene->GetPlaybackRange().GetUpperBoundValue();
		float Duration = TickResolution.AsSeconds(FFrameTime(EndFrame - StartFrame));
		Pairs.Add(AgentJson::PairFloat(TEXT("duration"), Duration));

		// 绑定的对象
		TArray<FString> BindingItems;
		for (const FMovieSceneBinding& Binding : MovieScene->GetBindings())
		{
			TArray<FString> BindPairs;
			BindPairs.Add(AgentJson::Pair(TEXT("name"), Binding.GetName()));

			TArray<FString> TrackItems;
			for (UMovieSceneTrack* Track : Binding.GetTracks())
			{
				if (!Track) continue;
				TArray<FString> TrackPairs;
				TrackPairs.Add(AgentJson::Pair(TEXT("track_name"), Track->GetTrackName().ToString()));
				TrackPairs.Add(AgentJson::Pair(TEXT("track_type"), Track->GetClass()->GetName()));
				TrackItems.Add(AgentJson::Object(TrackPairs));
			}
			BindPairs.Add(AgentJson::PairRaw(TEXT("tracks"), AgentJson::Array(TrackItems)));

			BindingItems.Add(AgentJson::Object(BindPairs));
		}
		Pairs.Add(AgentJson::PairRaw(TEXT("bindings"), AgentJson::Array(BindingItems)));
	}

	return AgentJson::Object(Pairs);
#else
	return TEXT("{\"error\":\"Editor only data not available\"}");
#endif
}

// ==================== 函数与事件 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetBlueprintFunctions(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (!Graph) continue;

		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), Graph->GetName()));

		// 获取函数入口节点的参数信息
		TArray<FString> ParamItems;
		TArray<FString> ReturnItems;
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			UK2Node_FunctionEntry* EntryNode = Cast<UK2Node_FunctionEntry>(Node);
			if (!EntryNode) continue;

			for (UEdGraphPin* Pin : EntryNode->Pins)
			{
				if (!Pin || Pin->Direction != EGPD_Output) continue;
				if (Pin->PinName == UEdGraphSchema_K2::PN_Then) continue;

				TArray<FString> PinPairs;
				PinPairs.Add(AgentJson::Pair(TEXT("name"), Pin->PinName.ToString()));
				PinPairs.Add(AgentJson::Pair(TEXT("type"), Pin->PinType.PinCategory.ToString()));
				if (Pin->PinType.PinSubCategoryObject.IsValid())
				{
					PinPairs.Add(AgentJson::Pair(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName()));
				}
				ParamItems.Add(AgentJson::Object(PinPairs));
			}
		}
		Pairs.Add(AgentJson::PairRaw(TEXT("parameters"), AgentJson::Array(ParamItems)));

		// 获取返回值（通过FunctionResult节点）
		for (UEdGraphNode* Node : Graph->Nodes)
		{
			if (Node->GetClass()->GetName().Contains(TEXT("FunctionResult")))
			{
				for (UEdGraphPin* Pin : Node->Pins)
				{
					if (!Pin || Pin->Direction != EGPD_Input) continue;
					if (Pin->PinName == UEdGraphSchema_K2::PN_Execute) continue;

					TArray<FString> PinPairs;
					PinPairs.Add(AgentJson::Pair(TEXT("name"), Pin->PinName.ToString()));
					PinPairs.Add(AgentJson::Pair(TEXT("type"), Pin->PinType.PinCategory.ToString()));
					if (Pin->PinType.PinSubCategoryObject.IsValid())
					{
						PinPairs.Add(AgentJson::Pair(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName()));
					}
					ReturnItems.Add(AgentJson::Object(PinPairs));
				}
			}
		}
		Pairs.Add(AgentJson::PairRaw(TEXT("return_values"), AgentJson::Array(ReturnItems)));

		Items.Add(AgentJson::Object(Pairs));
	}

	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetBlueprintEvents(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;

	// 遍历EventGraphs
	for (UEdGraph* Graph : WidgetBP->UbergraphPages)
	{
		if (!Graph) continue;

		for (UEdGraphNode* Node : Graph->Nodes)
		{
			// 自定义事件
			UK2Node_CustomEvent* CustomEvent = Cast<UK2Node_CustomEvent>(Node);
			if (CustomEvent)
			{
				TArray<FString> Pairs;
				Pairs.Add(AgentJson::Pair(TEXT("name"), CustomEvent->CustomFunctionName.ToString()));
				Pairs.Add(AgentJson::Pair(TEXT("type"), TEXT("CustomEvent")));
				Pairs.Add(AgentJson::Pair(TEXT("graph"), Graph->GetName()));
				Items.Add(AgentJson::Object(Pairs));
				continue;
			}

			// 引擎事件（如Construct、Tick等）
			UK2Node_Event* EventNode = Cast<UK2Node_Event>(Node);
			if (EventNode)
			{
				TArray<FString> Pairs;
				Pairs.Add(AgentJson::Pair(TEXT("name"), EventNode->GetFunctionName().ToString()));
				Pairs.Add(AgentJson::Pair(TEXT("type"), TEXT("EngineEvent")));
				Pairs.Add(AgentJson::Pair(TEXT("graph"), Graph->GetName()));
				Items.Add(AgentJson::Object(Pairs));
			}
		}
	}

	return AgentJson::Array(Items);
}

// ==================== 属性绑定 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetPropertyBindings(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;

#if WITH_EDITORONLY_DATA
	for (const FDelegateEditorBinding& Binding : WidgetBP->Bindings)
	{
		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("widget_name"), Binding.ObjectName));
		Pairs.Add(AgentJson::Pair(TEXT("property_name"), Binding.PropertyName.ToString()));
		Pairs.Add(AgentJson::Pair(TEXT("function_name"), Binding.FunctionName.ToString()));
		Pairs.Add(AgentJson::Pair(TEXT("source_property"), Binding.SourceProperty.ToString()));
		Pairs.Add(AgentJson::Pair(TEXT("kind"), UEnum::GetValueAsString(Binding.Kind)));

		Items.Add(AgentJson::Object(Pairs));
	}
#endif

	return AgentJson::Array(Items);
}

// ==================== NamedSlot ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetNamedSlots(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;

	// 从WidgetTree中查找所有NamedSlot Widget
	TArray<UWidget*> AllWidgets;
	WidgetBP->WidgetTree->GetAllWidgets(AllWidgets);

	for (UWidget* Widget : AllWidgets)
	{
		UNamedSlot* NamedSlotWidget = Cast<UNamedSlot>(Widget);
		if (!NamedSlotWidget) continue;

		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), NamedSlotWidget->GetName()));

		// 获取Slot中的内容
		if (NamedSlotWidget->GetChildrenCount() > 0)
		{
			UWidget* Content = NamedSlotWidget->GetChildAt(0);
			if (Content)
			{
				Pairs.Add(AgentJson::Pair(TEXT("content_name"), Content->GetName()));
				Pairs.Add(AgentJson::Pair(TEXT("content_type"), Content->GetClass()->GetName()));
			}
		}
		else
		{
			Pairs.Add(AgentJson::Pair(TEXT("content_name"), TEXT("")));
			Pairs.Add(AgentJson::Pair(TEXT("content_type"), TEXT("")));
		}

		Items.Add(AgentJson::Object(Pairs));
	}

	// 也包含WidgetTree的NamedSlotBindings
	for (const auto& SlotBinding : WidgetBP->WidgetTree->NamedSlotBindings)
	{
		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), SlotBinding.Key.ToString()));
		Pairs.Add(AgentJson::Pair(TEXT("source"), TEXT("NamedSlotBinding")));
		if (SlotBinding.Value)
		{
			Pairs.Add(AgentJson::Pair(TEXT("content_name"), SlotBinding.Value->GetName()));
			Pairs.Add(AgentJson::Pair(TEXT("content_type"), SlotBinding.Value->GetClass()->GetName()));
		}
		Items.Add(AgentJson::Object(Pairs));
	}

	return AgentJson::Array(Items);
}

// ==================== 批量查询 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetAllWidgetBlueprintsInDirectory(const FString& DirectoryPath, bool bRecursive)
{
	FAssetRegistryModule& AssetRegistryModule = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry");
	IAssetRegistry& AssetRegistry = AssetRegistryModule.Get();

	FARFilter Filter;
	Filter.ClassPaths.Add(UWidgetBlueprint::StaticClass()->GetClassPathName());
	Filter.bRecursiveClasses = true;
	Filter.PackagePaths.Add(*DirectoryPath);
	Filter.bRecursivePaths = bRecursive;

	TArray<FAssetData> AssetList;
	AssetRegistry.GetAssets(Filter, AssetList);

	TArray<FString> Items;
	for (const FAssetData& Asset : AssetList)
	{
		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), Asset.AssetName.ToString()));
		Pairs.Add(AgentJson::Pair(TEXT("path"), Asset.GetObjectPathString()));
		Pairs.Add(AgentJson::Pair(TEXT("package_path"), Asset.PackagePath.ToString()));
		Items.Add(AgentJson::Object(Pairs));
	}

	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetBlueprintInheritanceChain(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->GeneratedClass)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;
	UClass* CurrentClass = WidgetBP->GeneratedClass;
	while (CurrentClass)
	{
		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), CurrentClass->GetName()));
		Pairs.Add(AgentJson::Pair(TEXT("path"), CurrentClass->GetPathName()));
		Pairs.Add(AgentJson::PairBool(TEXT("is_blueprint"), CurrentClass->ClassGeneratedBy != nullptr));
		Items.Add(AgentJson::Object(Pairs));

		if (CurrentClass == UUserWidget::StaticClass())
		{
			break;
		}
		CurrentClass = CurrentClass->GetSuperClass();
	}

	return AgentJson::Array(Items);
}

// ==================== 蓝图图表与节点 ====================

UEdGraph* UAgentWidgetBlueprintInfoFunctionLib::FindGraphByName(UWidgetBlueprint* WidgetBP, const FString& GraphName)
{
	if (!WidgetBP)
	{
		return nullptr;
	}

	TArray<UEdGraph*> AllGraphs;
	WidgetBP->GetAllGraphs(AllGraphs);
	for (UEdGraph* Graph : AllGraphs)
	{
		if (Graph && Graph->GetName() == GraphName)
		{
			return Graph;
		}
	}
	return nullptr;
}

FString UAgentWidgetBlueprintInfoFunctionLib::PinToJson(UEdGraphPin* Pin, bool bIncludeLinks)
{
	if (!Pin)
	{
		return TEXT("null");
	}

	TArray<FString> Pairs;
	Pairs.Add(AgentJson::Pair(TEXT("name"), Pin->PinName.ToString()));
	Pairs.Add(AgentJson::Pair(TEXT("direction"), Pin->Direction == EGPD_Input ? TEXT("Input") : TEXT("Output")));
	Pairs.Add(AgentJson::Pair(TEXT("type"), Pin->PinType.PinCategory.ToString()));

	if (Pin->PinType.PinSubCategoryObject.IsValid())
	{
		Pairs.Add(AgentJson::Pair(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName()));
	}

	Pairs.Add(AgentJson::PairBool(TEXT("is_array"), Pin->PinType.IsArray()));
	Pairs.Add(AgentJson::PairBool(TEXT("is_reference"), Pin->PinType.bIsReference));
	Pairs.Add(AgentJson::PairBool(TEXT("is_hidden"), Pin->bHidden));

	if (!Pin->DefaultValue.IsEmpty())
	{
		Pairs.Add(AgentJson::Pair(TEXT("default_value"), Pin->DefaultValue));
	}
	if (!Pin->DefaultTextValue.IsEmpty())
	{
		Pairs.Add(AgentJson::Pair(TEXT("default_text_value"), Pin->DefaultTextValue.ToString()));
	}

	if (bIncludeLinks)
	{
		TArray<FString> LinkItems;
		for (UEdGraphPin* LinkedPin : Pin->LinkedTo)
		{
			if (!LinkedPin || !LinkedPin->GetOwningNode()) continue;

			TArray<FString> LinkPairs;
			LinkPairs.Add(AgentJson::Pair(TEXT("node_name"), LinkedPin->GetOwningNode()->GetNodeTitle(ENodeTitleType::ListView).ToString()));
			LinkPairs.Add(AgentJson::Pair(TEXT("node_guid"), LinkedPin->GetOwningNode()->NodeGuid.ToString()));
			LinkPairs.Add(AgentJson::Pair(TEXT("pin_name"), LinkedPin->PinName.ToString()));
			LinkItems.Add(AgentJson::Object(LinkPairs));
		}
		Pairs.Add(AgentJson::PairRaw(TEXT("links"), AgentJson::Array(LinkItems)));
	}

	return AgentJson::Object(Pairs);
}

FString UAgentWidgetBlueprintInfoFunctionLib::NodeToJson(UEdGraphNode* Node, bool bDetailed)
{
	if (!Node)
	{
		return TEXT("null");
	}

	TArray<FString> Pairs;
	Pairs.Add(AgentJson::Pair(TEXT("node_class"), Node->GetClass()->GetName()));
	Pairs.Add(AgentJson::Pair(TEXT("title"), Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString()));
	Pairs.Add(AgentJson::Pair(TEXT("compact_title"), Node->GetNodeTitle(ENodeTitleType::ListView).ToString()));
	Pairs.Add(AgentJson::Pair(TEXT("guid"), Node->NodeGuid.ToString()));
	Pairs.Add(AgentJson::PairInt(TEXT("pos_x"), Node->NodePosX));
	Pairs.Add(AgentJson::PairInt(TEXT("pos_y"), Node->NodePosY));
	Pairs.Add(AgentJson::PairBool(TEXT("enabled"), Node->IsNodeEnabled()));

	if (!Node->NodeComment.IsEmpty())
	{
		Pairs.Add(AgentJson::Pair(TEXT("comment"), Node->NodeComment));
	}

	if (bDetailed)
	{
		TArray<FString> PinItems;
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (!Pin) continue;
			PinItems.Add(PinToJson(Pin, true));
		}
		Pairs.Add(AgentJson::PairRaw(TEXT("pins"), AgentJson::Array(PinItems)));
	}
	else
	{
		// 简略模式只列出非Exec引脚的名称和方向
		int32 InputCount = 0;
		int32 OutputCount = 0;
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (!Pin || Pin->bHidden) continue;
			if (Pin->Direction == EGPD_Input) InputCount++;
			else OutputCount++;
		}
		Pairs.Add(AgentJson::PairInt(TEXT("input_pin_count"), InputCount));
		Pairs.Add(AgentJson::PairInt(TEXT("output_pin_count"), OutputCount));
	}

	return AgentJson::Object(Pairs);
}

static FString GetGraphTypeString(UWidgetBlueprint* WidgetBP, UEdGraph* Graph)
{
	for (UEdGraph* G : WidgetBP->FunctionGraphs)
	{
		if (G == Graph) return TEXT("Function");
	}
	for (UEdGraph* G : WidgetBP->UbergraphPages)
	{
		if (G == Graph) return TEXT("EventGraph");
	}
	for (UEdGraph* G : WidgetBP->MacroGraphs)
	{
		if (G == Graph) return TEXT("Macro");
	}
	for (UEdGraph* G : WidgetBP->DelegateSignatureGraphs)
	{
		if (G == Graph) return TEXT("DelegateSignature");
	}
	return TEXT("Other");
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetAllGraphs(const FString& AssetPath)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("[]");
	}

	TArray<UEdGraph*> AllGraphs;
	WidgetBP->GetAllGraphs(AllGraphs);

	TArray<FString> Items;
	for (UEdGraph* Graph : AllGraphs)
	{
		if (!Graph) continue;

		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), Graph->GetName()));
		Pairs.Add(AgentJson::Pair(TEXT("type"), GetGraphTypeString(WidgetBP, Graph)));
		Pairs.Add(AgentJson::PairInt(TEXT("node_count"), Graph->Nodes.Num()));

		Items.Add(AgentJson::Object(Pairs));
	}

	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetGraphNodes(const FString& AssetPath, const FString& GraphName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* Graph = FindGraphByName(WidgetBP, GraphName);
	if (!Graph)
	{
		return TEXT("{\"error\":\"Graph not found\"}");
	}

	TArray<FString> Items;
	for (UEdGraphNode* Node : Graph->Nodes)
	{
		if (!Node) continue;
		Items.Add(NodeToJson(Node, false));
	}

	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetNodeDetail(const FString& AssetPath, const FString& GraphName, const FString& NodeGuid)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* Graph = FindGraphByName(WidgetBP, GraphName);
	if (!Graph)
	{
		return TEXT("{\"error\":\"Graph not found\"}");
	}

	FGuid TargetGuid;
	if (!FGuid::Parse(NodeGuid, TargetGuid))
	{
		return TEXT("{\"error\":\"Invalid GUID format\"}");
	}

	for (UEdGraphNode* Node : Graph->Nodes)
	{
		if (Node && Node->NodeGuid == TargetGuid)
		{
			return NodeToJson(Node, true);
		}
	}

	return TEXT("{\"error\":\"Node not found\"}");
}

// ==================== ChildWidget 重命名 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::RenameChildWidget(const FString& AssetPath, const FString& OldWidgetName, const FString& NewWidgetName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UWidget* Widget = FindWidgetInTree(WidgetBP, OldWidgetName);
	if (!Widget)
	{
		return TEXT("{\"success\":false,\"message\":\"Widget not found in WidgetTree\"}");
	}

	if (FindWidgetInTree(WidgetBP, NewWidgetName))
	{
		return FString::Printf(TEXT("{\"success\":false,\"message\":\"Widget name '%s' already exists\"}"), *AgentJson::EscapeString(NewWidgetName));
	}

	Widget->Rename(*NewWidgetName, nullptr, REN_DontCreateRedirectors);
	WidgetBP->MarkPackageDirty();

	return FString::Printf(TEXT("{\"success\":true,\"message\":\"Renamed '%s' to '%s'\"}"),
		*AgentJson::EscapeString(OldWidgetName), *AgentJson::EscapeString(NewWidgetName));
}

// ==================== ChildWidget 属性编辑 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::SetWidgetProperty(const FString& AssetPath, const FString& WidgetName, const FString& PropertyName, const FString& PropertyValue)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UWidget* Widget = FindWidgetInTree(WidgetBP, WidgetName);
	if (!Widget)
	{
		return TEXT("{\"success\":false,\"message\":\"Widget not found in WidgetTree\"}");
	}

	FProperty* Prop = FindFProperty<FProperty>(Widget->GetClass(), *PropertyName);
	if (!Prop)
	{
		return FString::Printf(TEXT("{\"success\":false,\"message\":\"Property '%s' not found on widget class '%s'\"}"),
			*AgentJson::EscapeString(PropertyName), *Widget->GetClass()->GetName());
	}

	void* ValuePtr = Prop->ContainerPtrToValuePtr<void>(Widget);
	Prop->ImportText_Direct(*PropertyValue, ValuePtr, Widget, PPF_None);
	WidgetBP->MarkPackageDirty();

	return FString::Printf(TEXT("{\"success\":true,\"message\":\"Property '%s' set to '%s'\"}"),
		*AgentJson::EscapeString(PropertyName), *AgentJson::EscapeString(PropertyValue));
}

FString UAgentWidgetBlueprintInfoFunctionLib::SetWidgetProperties(const FString& AssetPath, const FString& WidgetName, const FString& PropertiesJson)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UWidget* Widget = FindWidgetInTree(WidgetBP, WidgetName);
	if (!Widget)
	{
		return TEXT("{\"success\":false,\"message\":\"Widget not found in WidgetTree\"}");
	}

	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(PropertiesJson);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return TEXT("{\"success\":false,\"message\":\"Invalid JSON format for PropertiesJson\"}");
	}

	TArray<FString> ResultItems;
	bool bAnyFailed = false;

	for (const auto& Pair : JsonObj->Values)
	{
		const FString& PropName = Pair.Key;
		FString PropValue;
		Pair.Value->TryGetString(PropValue);

		FProperty* Prop = FindFProperty<FProperty>(Widget->GetClass(), *PropName);
		if (!Prop)
		{
			ResultItems.Add(FString::Printf(TEXT("{\"property\":\"%s\",\"success\":false,\"message\":\"Property not found\"}"),
				*AgentJson::EscapeString(PropName)));
			bAnyFailed = true;
			continue;
		}

		void* ValuePtr = Prop->ContainerPtrToValuePtr<void>(Widget);
		Prop->ImportText_Direct(*PropValue, ValuePtr, Widget, PPF_None);
		ResultItems.Add(FString::Printf(TEXT("{\"property\":\"%s\",\"success\":true}"),
			*AgentJson::EscapeString(PropName)));
	}

	WidgetBP->MarkPackageDirty();

	TArray<FString> OutPairs;
	OutPairs.Add(AgentJson::PairBool(TEXT("success"), !bAnyFailed));
	OutPairs.Add(AgentJson::PairRaw(TEXT("results"), AgentJson::Array(ResultItems)));
	return AgentJson::Object(OutPairs);
}

FString UAgentWidgetBlueprintInfoFunctionLib::SetWidgetSlotProperties(const FString& AssetPath, const FString& WidgetName, const FString& SlotPropertiesJson)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UWidget* Widget = FindWidgetInTree(WidgetBP, WidgetName);
	if (!Widget)
	{
		return TEXT("{\"success\":false,\"message\":\"Widget not found in WidgetTree\"}");
	}

	if (!Widget->Slot)
	{
		return TEXT("{\"success\":false,\"message\":\"Widget has no Slot\"}");
	}

	TSharedPtr<FJsonObject> JsonObj;
	TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(SlotPropertiesJson);
	if (!FJsonSerializer::Deserialize(Reader, JsonObj) || !JsonObj.IsValid())
	{
		return TEXT("{\"success\":false,\"message\":\"Invalid JSON format for SlotPropertiesJson\"}");
	}

	TArray<FString> ResultItems;
	bool bAnyFailed = false;

	for (const auto& Pair : JsonObj->Values)
	{
		const FString& PropName = Pair.Key;
		FString PropValue;
		Pair.Value->TryGetString(PropValue);

		FProperty* Prop = FindFProperty<FProperty>(Widget->Slot->GetClass(), *PropName);
		if (!Prop)
		{
			ResultItems.Add(FString::Printf(TEXT("{\"property\":\"%s\",\"success\":false,\"message\":\"Slot property not found\"}"),
				*AgentJson::EscapeString(PropName)));
			bAnyFailed = true;
			continue;
		}

		void* ValuePtr = Prop->ContainerPtrToValuePtr<void>(Widget->Slot);
		Prop->ImportText_Direct(*PropValue, ValuePtr, Widget->Slot, PPF_None);
		ResultItems.Add(FString::Printf(TEXT("{\"property\":\"%s\",\"success\":true}"),
			*AgentJson::EscapeString(PropName)));
	}

	WidgetBP->MarkPackageDirty();

	TArray<FString> OutPairs;
	OutPairs.Add(AgentJson::PairBool(TEXT("success"), !bAnyFailed));
	OutPairs.Add(AgentJson::PairRaw(TEXT("results"), AgentJson::Array(ResultItems)));
	return AgentJson::Object(OutPairs);
}

// ==================== 蓝图函数编辑 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::AddBlueprintFunction(const FString& AssetPath, const FString& FunctionName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			return FString::Printf(TEXT("{\"success\":false,\"message\":\"Function '%s' already exists\"}"),
				*AgentJson::EscapeString(FunctionName));
		}
	}

	UEdGraph* NewGraph = FBlueprintEditorUtils::CreateNewGraph(
		WidgetBP,
		FName(*FunctionName),
		UEdGraph::StaticClass(),
		UEdGraphSchema_K2::StaticClass()
	);

	if (!NewGraph)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to create function graph\"}");
	}

	FBlueprintEditorUtils::AddFunctionGraph<UClass>(WidgetBP, NewGraph, false, nullptr);
	WidgetBP->MarkPackageDirty();

	return FString::Printf(TEXT("{\"success\":true,\"message\":\"Function '%s' created\",\"graph_name\":\"%s\"}"),
		*AgentJson::EscapeString(FunctionName), *AgentJson::EscapeString(NewGraph->GetName()));
}

FString UAgentWidgetBlueprintInfoFunctionLib::RemoveBlueprintFunction(const FString& AssetPath, const FString& FunctionName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			TargetGraph = Graph;
			break;
		}
	}

	if (!TargetGraph)
	{
		return FString::Printf(TEXT("{\"success\":false,\"message\":\"Function '%s' not found\"}"),
			*AgentJson::EscapeString(FunctionName));
	}

	FBlueprintEditorUtils::RemoveGraph(WidgetBP, TargetGraph, EGraphRemoveFlags::Recompile);
	WidgetBP->MarkPackageDirty();

	return FString::Printf(TEXT("{\"success\":true,\"message\":\"Function '%s' removed\"}"),
		*AgentJson::EscapeString(FunctionName));
}

FString UAgentWidgetBlueprintInfoFunctionLib::RenameBlueprintFunction(const FString& AssetPath, const FString& OldFunctionName, const FString& NewFunctionName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == OldFunctionName)
		{
			TargetGraph = Graph;
			break;
		}
	}

	if (!TargetGraph)
	{
		return FString::Printf(TEXT("{\"success\":false,\"message\":\"Function '%s' not found\"}"),
			*AgentJson::EscapeString(OldFunctionName));
	}

	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == NewFunctionName)
		{
			return FString::Printf(TEXT("{\"success\":false,\"message\":\"Function name '%s' already exists\"}"),
				*AgentJson::EscapeString(NewFunctionName));
		}
	}

	FBlueprintEditorUtils::RenameGraph(TargetGraph, NewFunctionName);
	WidgetBP->MarkPackageDirty();

	return FString::Printf(TEXT("{\"success\":true,\"message\":\"Function renamed from '%s' to '%s'\"}"),
		*AgentJson::EscapeString(OldFunctionName), *AgentJson::EscapeString(NewFunctionName));
}

static FName WBPParamTypeToPinCategory(const FString& ParamType)
{
	if (ParamType.Equals(TEXT("bool"), ESearchCase::IgnoreCase))    return UEdGraphSchema_K2::PC_Boolean;
	if (ParamType.Equals(TEXT("int"), ESearchCase::IgnoreCase))     return UEdGraphSchema_K2::PC_Int;
	if (ParamType.Equals(TEXT("float"), ESearchCase::IgnoreCase))   return UEdGraphSchema_K2::PC_Real;
	if (ParamType.Equals(TEXT("string"), ESearchCase::IgnoreCase))  return UEdGraphSchema_K2::PC_String;
	if (ParamType.Equals(TEXT("text"), ESearchCase::IgnoreCase))    return UEdGraphSchema_K2::PC_Text;
	if (ParamType.Equals(TEXT("name"), ESearchCase::IgnoreCase))    return UEdGraphSchema_K2::PC_Name;
	if (ParamType.Equals(TEXT("object"), ESearchCase::IgnoreCase))  return UEdGraphSchema_K2::PC_Object;
	if (ParamType.Equals(TEXT("class"), ESearchCase::IgnoreCase))   return UEdGraphSchema_K2::PC_Class;
	if (ParamType.Equals(TEXT("struct"), ESearchCase::IgnoreCase))  return UEdGraphSchema_K2::PC_Struct;
	return UEdGraphSchema_K2::PC_Wildcard;
}

FString UAgentWidgetBlueprintInfoFunctionLib::AddFunctionInputParam(const FString& AssetPath, const FString& FunctionName, const FString& ParamName, const FString& ParamType)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			TargetGraph = Graph;
			break;
		}
	}

	if (!TargetGraph)
	{
		return FString::Printf(TEXT("{\"success\":false,\"message\":\"Function '%s' not found\"}"),
			*AgentJson::EscapeString(FunctionName));
	}

	UK2Node_FunctionEntry* EntryNode = nullptr;
	for (UEdGraphNode* Node : TargetGraph->Nodes)
	{
		EntryNode = Cast<UK2Node_FunctionEntry>(Node);
		if (EntryNode) break;
	}

	if (!EntryNode)
	{
		return TEXT("{\"success\":false,\"message\":\"Function entry node not found\"}");
	}

	FEdGraphPinType PinType;
	PinType.PinCategory = WBPParamTypeToPinCategory(ParamType);

	EntryNode->CreateUserDefinedPin(FName(*ParamName), PinType, EGPD_Output);
	FBlueprintEditorUtils::MarkBlueprintAsModified(WidgetBP);
	WidgetBP->MarkPackageDirty();

	return FString::Printf(TEXT("{\"success\":true,\"message\":\"Input param '%s' (%s) added to function '%s'\"}"),
		*AgentJson::EscapeString(ParamName), *AgentJson::EscapeString(ParamType), *AgentJson::EscapeString(FunctionName));
}

FString UAgentWidgetBlueprintInfoFunctionLib::AddFunctionOutputParam(const FString& AssetPath, const FString& FunctionName, const FString& ParamName, const FString& ParamType)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			TargetGraph = Graph;
			break;
		}
	}

	if (!TargetGraph)
	{
		return FString::Printf(TEXT("{\"success\":false,\"message\":\"Function '%s' not found\"}"),
			*AgentJson::EscapeString(FunctionName));
	}

	UEdGraphNode* ResultNode = nullptr;
	for (UEdGraphNode* Node : TargetGraph->Nodes)
	{
		if (Node && Node->GetClass()->GetName().Contains(TEXT("FunctionResult")))
		{
			ResultNode = Node;
			break;
		}
	}

	if (!ResultNode)
	{
		return TEXT("{\"success\":false,\"message\":\"Function result node not found\"}");
	}

	UK2Node_EditablePinBase* EditableResult = Cast<UK2Node_EditablePinBase>(ResultNode);
	if (!EditableResult)
	{
		return TEXT("{\"success\":false,\"message\":\"Result node is not editable\"}");
	}

	FEdGraphPinType PinType;
	PinType.PinCategory = WBPParamTypeToPinCategory(ParamType);

	EditableResult->CreateUserDefinedPin(FName(*ParamName), PinType, EGPD_Input);
	FBlueprintEditorUtils::MarkBlueprintAsModified(WidgetBP);
	WidgetBP->MarkPackageDirty();

	return FString::Printf(TEXT("{\"success\":true,\"message\":\"Output param '%s' (%s) added to function '%s'\"}"),
		*AgentJson::EscapeString(ParamName), *AgentJson::EscapeString(ParamType), *AgentJson::EscapeString(FunctionName));
}

FString UAgentWidgetBlueprintInfoFunctionLib::SetFunctionDescription(const FString& AssetPath, const FString& FunctionName, const FString& Description)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"success\":false,\"message\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			TargetGraph = Graph;
			break;
		}
	}

	if (!TargetGraph)
	{
		return FString::Printf(TEXT("{\"success\":false,\"message\":\"Function '%s' not found\"}"),
			*AgentJson::EscapeString(FunctionName));
	}

	UK2Node_FunctionEntry* EntryNode = nullptr;
	for (UEdGraphNode* Node : TargetGraph->Nodes)
	{
		EntryNode = Cast<UK2Node_FunctionEntry>(Node);
		if (EntryNode) break;
	}

	if (!EntryNode)
	{
		return TEXT("{\"success\":false,\"message\":\"Function entry node not found\"}");
	}

	EntryNode->MetaData.ToolTip = FText::FromString(Description);
	FBlueprintEditorUtils::MarkBlueprintAsModified(WidgetBP);
	WidgetBP->MarkPackageDirty();

	return FString::Printf(TEXT("{\"success\":true,\"message\":\"Description set for function '%s'\"}"),
		*AgentJson::EscapeString(FunctionName));
}

// ==================== 蓝图函数阅读 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetBlueprintFunctionDetail(const FString& AssetPath, const FString& FunctionName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			TargetGraph = Graph;
			break;
		}
	}

	if (!TargetGraph)
	{
		return FString::Printf(TEXT("{\"error\":\"Function '%s' not found\"}"), *AgentJson::EscapeString(FunctionName));
	}

	TArray<FString> Pairs;
	Pairs.Add(AgentJson::Pair(TEXT("name"), TargetGraph->GetName()));
	Pairs.Add(AgentJson::PairInt(TEXT("node_count"), TargetGraph->Nodes.Num()));

	TArray<FString> InputItems;
	TArray<FString> OutputItems;
	FString Description;

	for (UEdGraphNode* Node : TargetGraph->Nodes)
	{
		UK2Node_FunctionEntry* EntryNode = Cast<UK2Node_FunctionEntry>(Node);
		if (EntryNode)
		{
			Description = EntryNode->MetaData.ToolTip.ToString();
			for (UEdGraphPin* Pin : EntryNode->Pins)
			{
				if (!Pin || Pin->Direction != EGPD_Output) continue;
				if (Pin->PinName == UEdGraphSchema_K2::PN_Then) continue;

				TArray<FString> PinPairs;
				PinPairs.Add(AgentJson::Pair(TEXT("name"), Pin->PinName.ToString()));
				PinPairs.Add(AgentJson::Pair(TEXT("type"), Pin->PinType.PinCategory.ToString()));
				if (Pin->PinType.PinSubCategoryObject.IsValid())
				{
					PinPairs.Add(AgentJson::Pair(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName()));
				}
				InputItems.Add(AgentJson::Object(PinPairs));
			}
			continue;
		}

		if (Node && Node->GetClass()->GetName().Contains(TEXT("FunctionResult")))
		{
			for (UEdGraphPin* Pin : Node->Pins)
			{
				if (!Pin || Pin->Direction != EGPD_Input) continue;
				if (Pin->PinName == UEdGraphSchema_K2::PN_Execute) continue;

				TArray<FString> PinPairs;
				PinPairs.Add(AgentJson::Pair(TEXT("name"), Pin->PinName.ToString()));
				PinPairs.Add(AgentJson::Pair(TEXT("type"), Pin->PinType.PinCategory.ToString()));
				if (Pin->PinType.PinSubCategoryObject.IsValid())
				{
					PinPairs.Add(AgentJson::Pair(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName()));
				}
				OutputItems.Add(AgentJson::Object(PinPairs));
			}
		}
	}

	Pairs.Add(AgentJson::Pair(TEXT("description"), Description));
	Pairs.Add(AgentJson::PairRaw(TEXT("inputs"), AgentJson::Array(InputItems)));
	Pairs.Add(AgentJson::PairRaw(TEXT("outputs"), AgentJson::Array(OutputItems)));

	return AgentJson::Object(Pairs);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetFunctionGraphNodes(const FString& AssetPath, const FString& FunctionName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			TargetGraph = Graph;
			break;
		}
	}

	if (!TargetGraph)
	{
		return FString::Printf(TEXT("{\"error\":\"Function '%s' not found\"}"), *AgentJson::EscapeString(FunctionName));
	}

	TArray<FString> Items;
	for (UEdGraphNode* Node : TargetGraph->Nodes)
	{
		if (!Node) continue;
		Items.Add(NodeToJson(Node, true));
	}

	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetFunctionParams(const FString& AssetPath, const FString& FunctionName)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("{\"error\":\"Failed to load WidgetBlueprint\"}");
	}

	UEdGraph* TargetGraph = nullptr;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			TargetGraph = Graph;
			break;
		}
	}

	if (!TargetGraph)
	{
		return FString::Printf(TEXT("{\"error\":\"Function '%s' not found\"}"), *AgentJson::EscapeString(FunctionName));
	}

	TArray<FString> InputItems;
	TArray<FString> OutputItems;

	for (UEdGraphNode* Node : TargetGraph->Nodes)
	{
		UK2Node_FunctionEntry* EntryNode = Cast<UK2Node_FunctionEntry>(Node);
		if (EntryNode)
		{
			for (UEdGraphPin* Pin : EntryNode->Pins)
			{
				if (!Pin || Pin->Direction != EGPD_Output) continue;
				if (Pin->PinName == UEdGraphSchema_K2::PN_Then) continue;

				TArray<FString> PinPairs;
				PinPairs.Add(AgentJson::Pair(TEXT("name"), Pin->PinName.ToString()));
				PinPairs.Add(AgentJson::Pair(TEXT("type"), Pin->PinType.PinCategory.ToString()));
				if (Pin->PinType.PinSubCategoryObject.IsValid())
				{
					PinPairs.Add(AgentJson::Pair(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName()));
				}
				InputItems.Add(AgentJson::Object(PinPairs));
			}
			continue;
		}

		if (Node && Node->GetClass()->GetName().Contains(TEXT("FunctionResult")))
		{
			for (UEdGraphPin* Pin : Node->Pins)
			{
				if (!Pin || Pin->Direction != EGPD_Input) continue;
				if (Pin->PinName == UEdGraphSchema_K2::PN_Execute) continue;

				TArray<FString> PinPairs;
				PinPairs.Add(AgentJson::Pair(TEXT("name"), Pin->PinName.ToString()));
				PinPairs.Add(AgentJson::Pair(TEXT("type"), Pin->PinType.PinCategory.ToString()));
				if (Pin->PinType.PinSubCategoryObject.IsValid())
				{
					PinPairs.Add(AgentJson::Pair(TEXT("sub_type"), Pin->PinType.PinSubCategoryObject->GetName()));
				}
				OutputItems.Add(AgentJson::Object(PinPairs));
			}
		}
	}

	TArray<FString> Pairs;
	Pairs.Add(AgentJson::PairRaw(TEXT("inputs"), AgentJson::Array(InputItems)));
	Pairs.Add(AgentJson::PairRaw(TEXT("outputs"), AgentJson::Array(OutputItems)));
	return AgentJson::Object(Pairs);
}

FString UAgentWidgetBlueprintInfoFunctionLib::SearchBlueprintFunctions(const FString& AssetPath, const FString& Keyword)
{
	UWidgetBlueprint* WidgetBP = LoadWidgetBlueprint(AssetPath);
	if (!WidgetBP)
	{
		return TEXT("[]");
	}

	TArray<FString> Items;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (!Graph) continue;

		const FString GraphName = Graph->GetName();
		if (!GraphName.Contains(Keyword, ESearchCase::IgnoreCase)) continue;

		int32 InputCount = 0;
		int32 OutputCount = 0;
		FString Description;

		for (UEdGraphNode* Node : Graph->Nodes)
		{
			UK2Node_FunctionEntry* EntryNode = Cast<UK2Node_FunctionEntry>(Node);
			if (EntryNode)
			{
				Description = EntryNode->MetaData.ToolTip.ToString();
				for (UEdGraphPin* Pin : EntryNode->Pins)
				{
					if (!Pin || Pin->Direction != EGPD_Output) continue;
					if (Pin->PinName == UEdGraphSchema_K2::PN_Then) continue;
					InputCount++;
				}
				continue;
			}

			if (Node && Node->GetClass()->GetName().Contains(TEXT("FunctionResult")))
			{
				for (UEdGraphPin* Pin : Node->Pins)
				{
					if (!Pin || Pin->Direction != EGPD_Input) continue;
					if (Pin->PinName == UEdGraphSchema_K2::PN_Execute) continue;
					OutputCount++;
				}
			}
		}

		TArray<FString> Pairs;
		Pairs.Add(AgentJson::Pair(TEXT("name"), GraphName));
		Pairs.Add(AgentJson::PairInt(TEXT("input_count"), InputCount));
		Pairs.Add(AgentJson::PairInt(TEXT("output_count"), OutputCount));
		Pairs.Add(AgentJson::Pair(TEXT("description"), Description));
		Items.Add(AgentJson::Object(Pairs));
	}

	return AgentJson::Array(Items);
}
