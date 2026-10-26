// Fill out your copyright notice in the Description page of Project Settings.

#include "AgentWidgetBlueprintInfoFunctionLib.h"

#include "AgentJson.h"
#include "Animation/WidgetAnimation.h"
#include "Blueprint/WidgetNavigation.h"
#include "Blueprint/WidgetTree.h"
#include "Components/PanelSlot.h"
#include "Components/PanelWidget.h"
#include "Components/Widget.h"
#include "EdGraph/EdGraph.h"
#include "EdGraphSchema_K2.h"
#include "K2Node_Event.h"
#include "K2Node_FunctionEntry.h"
#include "K2Node_FunctionResult.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/Kismet2NameValidators.h"
#include "MovieScene.h"
#include "MovieScenePossessable.h"
#include "WidgetBlueprint.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Components/CanvasPanel.h"
#include "Misc/AutomationTest.h"
#endif

// ==================== 公共辅助 ====================

static FString WBPFail(const FString& Message)
{
	return AgentJson::Object({AgentJson::PairBool(TEXT("success"), false), AgentJson::Pair(TEXT("message"), Message)});
}

static FString WBPOk(const FString& Message, TArray<FString> Fields = TArray<FString>())
{
	Fields.Insert(AgentJson::Pair(TEXT("message"), Message), 0);
	Fields.Insert(AgentJson::PairBool(TEXT("success"), true), 0);
	return AgentJson::Object(Fields);
}

static UWidgetBlueprint* WBPLoad(const FString& AssetPath, FString& OutError)
{
	FString FullPath = AssetPath;
	if (!FullPath.Contains(TEXT(".")))
	{
		FullPath += TEXT(".") + FPackageName::GetShortName(FullPath);
	}
	UWidgetBlueprint* WidgetBP = Cast<UWidgetBlueprint>(StaticLoadObject(UWidgetBlueprint::StaticClass(), nullptr, *FullPath));
	if (!WidgetBP || !WidgetBP->WidgetTree)
	{
		OutError = FString::Printf(TEXT("Not a WidgetBlueprint: %s"), *AssetPath);
		return nullptr;
	}
	return WidgetBP;
}

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWBPPrepareFixtureTest, "AgentTools.WBP.PrepareFixture", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWBPPrepareFixtureTest::RunTest(const FString& Parameters)
{
	FString Error;
	UWidgetBlueprint* Blueprint = WBPLoad(TEXT("/Game/__AgentToolsTests/IssuesFixture"), Error);
	if (!TestNotNull(TEXT("Explicitly created test fixture exists"), Blueprint))
	{
		return false;
	}
	if (Blueprint->WidgetTree->RootWidget)
	{
		return TestTrue(TEXT("Fixture root is a canvas"), Blueprint->WidgetTree->RootWidget->IsA<UCanvasPanel>());
	}
	Blueprint->WidgetTree->RootWidget = Blueprint->WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("FixtureCanvas"));
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
	return TestNotNull(TEXT("Fixture root was created"), Blueprint->WidgetTree->RootWidget.Get());
}
#endif

static UWidget* WBPFindWidget(UWidgetBlueprint* WidgetBP, const FString& WidgetName, FString& OutError)
{
	UWidget* Widget = WidgetBP->WidgetTree->FindWidget(FName(*WidgetName));
	if (!Widget)
	{
		OutError = FString::Printf(TEXT("Widget not found in WidgetTree: %s"), *WidgetName);
	}
	return Widget;
}

static UEdGraph* WBPFindFunction(UWidgetBlueprint* WidgetBP, const FString& FunctionName, FString& OutError)
{
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (Graph && Graph->GetName() == FunctionName)
		{
			return Graph;
		}
	}
	OutError = FString::Printf(TEXT("Function not found: %s"), *FunctionName);
	return nullptr;
}

static UK2Node_FunctionEntry* WBPFindEntry(UEdGraph* Graph)
{
	TArray<UK2Node_FunctionEntry*> Entries;
	Graph->GetNodesOfClass(Entries);
	return Entries.Num() > 0 ? Entries[0] : nullptr;
}

static UK2Node_FunctionResult* WBPFindResult(UEdGraph* Graph)
{
	TArray<UK2Node_FunctionResult*> Results;
	Graph->GetNodesOfClass(Results);
	return Results.Num() > 0 ? Results[0] : nullptr;
}

static FString WBPPinTypeJson(const FEdGraphPinType& PinType, TArray<FString> Fields = TArray<FString>())
{
	Fields.Add(AgentJson::Pair(TEXT("type"), PinType.PinCategory.ToString()));
	if (PinType.IsContainer())
	{
		Fields.Add(AgentJson::Pair(TEXT("container"), PinType.IsArray() ? TEXT("array") : PinType.IsSet() ? TEXT("set") : TEXT("map")));
	}
	if (PinType.PinSubCategoryObject.IsValid())
	{
		Fields.Add(AgentJson::Pair(TEXT("sub_type"), PinType.PinSubCategoryObject->GetName()));
	}
	else if (!PinType.PinSubCategory.IsNone())
	{
		Fields.Add(AgentJson::Pair(TEXT("sub_type"), PinType.PinSubCategory.ToString()));
	}
	return AgentJson::Object(Fields);
}

// 函数参数：入口节点的输出引脚（去掉执行引脚）或结果节点的输入引脚
static FString WBPParamsJson(UEdGraphNode* Node, EEdGraphPinDirection Direction)
{
	TArray<FString> Items;
	if (Node)
	{
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin && Pin->Direction == Direction && Pin->PinType.PinCategory != UEdGraphSchema_K2::PC_Exec)
			{
				Items.Add(WBPPinTypeJson(Pin->PinType, {AgentJson::Pair(TEXT("name"), Pin->PinName.ToString())}));
			}
		}
	}
	return AgentJson::Array(Items);
}

static FString WBPPropertiesJson(UObject* Target)
{
	TArray<FString> Items;
	for (TFieldIterator<FProperty> It(Target->GetClass()); It; ++It)
	{
		FProperty* Prop = *It;
		if (!Prop->HasAnyPropertyFlags(CPF_Edit | CPF_BlueprintVisible))
		{
			continue;
		}
		FString Value;
		Prop->ExportTextItem_Direct(Value, Prop->ContainerPtrToValuePtr<void>(Target), nullptr, Target, PPF_None);
		Items.Add(AgentJson::Object({AgentJson::Pair(TEXT("name"), Prop->GetName()), AgentJson::Pair(TEXT("type"), Prop->GetCPPType()), AgentJson::Pair(TEXT("value"), Value)}));
	}
	return AgentJson::Array(Items);
}

static FString WBPPinJson(UEdGraphPin* Pin)
{
	TArray<FString> Fields;
	Fields.Add(AgentJson::Pair(TEXT("name"), Pin->PinName.ToString()));
	Fields.Add(AgentJson::Pair(TEXT("direction"), Pin->Direction == EGPD_Input ? TEXT("Input") : TEXT("Output")));
	Fields.Add(AgentJson::PairBool(TEXT("is_array"), Pin->PinType.IsArray()));
	Fields.Add(AgentJson::PairBool(TEXT("is_reference"), Pin->PinType.bIsReference));
	Fields.Add(AgentJson::PairBool(TEXT("is_hidden"), Pin->bHidden));
	if (!Pin->DefaultValue.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("default_value"), Pin->DefaultValue));
	}
	if (!Pin->DefaultTextValue.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("default_text_value"), Pin->DefaultTextValue.ToString()));
	}
	TArray<FString> Links;
	for (UEdGraphPin* Linked : Pin->LinkedTo)
	{
		if (Linked && Linked->GetOwningNode())
		{
			Links.Add(AgentJson::Object({
				AgentJson::Pair(TEXT("node_name"), Linked->GetOwningNode()->GetNodeTitle(ENodeTitleType::ListView).ToString()),
				AgentJson::Pair(TEXT("node_guid"), Linked->GetOwningNode()->NodeGuid.ToString()),
				AgentJson::Pair(TEXT("pin_name"), Linked->PinName.ToString())}));
		}
	}
	Fields.Add(AgentJson::PairRaw(TEXT("links"), AgentJson::Array(Links)));
	return WBPPinTypeJson(Pin->PinType, Fields);
}

static FString WBPNodeJson(UEdGraphNode* Node, bool bDetailed)
{
	TArray<FString> Fields;
	Fields.Add(AgentJson::Pair(TEXT("node_class"), Node->GetClass()->GetName()));
	Fields.Add(AgentJson::Pair(TEXT("title"), Node->GetNodeTitle(ENodeTitleType::FullTitle).ToString()));
	Fields.Add(AgentJson::Pair(TEXT("compact_title"), Node->GetNodeTitle(ENodeTitleType::ListView).ToString()));
	Fields.Add(AgentJson::Pair(TEXT("guid"), Node->NodeGuid.ToString()));
	Fields.Add(AgentJson::PairInt(TEXT("pos_x"), Node->NodePosX));
	Fields.Add(AgentJson::PairInt(TEXT("pos_y"), Node->NodePosY));
	Fields.Add(AgentJson::PairBool(TEXT("enabled"), Node->IsNodeEnabled()));
	if (!Node->NodeComment.IsEmpty())
	{
		Fields.Add(AgentJson::Pair(TEXT("comment"), Node->NodeComment));
	}
	// 事件节点的标题是显示名，事件名要单独给（自定义事件即 CustomFunctionName）
	if (const UK2Node_Event* Event = Cast<UK2Node_Event>(Node))
	{
		Fields.Add(AgentJson::Pair(TEXT("function_name"), Event->GetFunctionName().ToString()));
	}
	if (bDetailed)
	{
		TArray<FString> Pins;
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin)
			{
				Pins.Add(WBPPinJson(Pin));
			}
		}
		Fields.Add(AgentJson::PairRaw(TEXT("pins"), AgentJson::Array(Pins)));
	}
	else
	{
		int32 Inputs = 0;
		int32 Outputs = 0;
		for (UEdGraphPin* Pin : Node->Pins)
		{
			if (Pin && !Pin->bHidden)
			{
				(Pin->Direction == EGPD_Input ? Inputs : Outputs)++;
			}
		}
		Fields.Add(AgentJson::PairInt(TEXT("input_pin_count"), Inputs));
		Fields.Add(AgentJson::PairInt(TEXT("output_pin_count"), Outputs));
	}
	return AgentJson::Object(Fields);
}

static FString WBPGraphType(UWidgetBlueprint* WidgetBP, UEdGraph* Graph)
{
	if (WidgetBP->FunctionGraphs.Contains(Graph))
	{
		return TEXT("Function");
	}
	if (WidgetBP->UbergraphPages.Contains(Graph))
	{
		return TEXT("EventGraph");
	}
	if (WidgetBP->MacroGraphs.Contains(Graph))
	{
		return TEXT("Macro");
	}
	if (WidgetBP->DelegateSignatureGraphs.Contains(Graph))
	{
		return TEXT("DelegateSignature");
	}
	return TEXT("Other");
}

// ==================== 读取 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgets(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	if (!WidgetBP)
	{
		return WBPFail(Error);
	}
	TArray<UWidget*> Widgets;
	WidgetBP->WidgetTree->GetAllWidgets(Widgets);
	TArray<FString> Items;
	for (UWidget* Widget : Widgets)
	{
		if (!Widget)
		{
			continue;
		}
		int32 ChildIndex = INDEX_NONE;
		const UPanelWidget* Parent = UWidgetTree::FindWidgetParent(Widget, ChildIndex);
		Items.Add(AgentJson::Object({
			AgentJson::Pair(TEXT("name"), Widget->GetName()),
			AgentJson::Pair(TEXT("type"), Widget->GetClass()->GetName()),
			AgentJson::PairBool(TEXT("is_variable"), Widget->bIsVariable),
			AgentJson::Pair(TEXT("visibility"), UEnum::GetValueAsString(Widget->GetVisibility())),
			AgentJson::Pair(TEXT("parent"), Parent ? Parent->GetName() : FString()),
			AgentJson::PairInt(TEXT("child_index"), ChildIndex)}));
	}
	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetProperties(const FString& AssetPath, const FString& WidgetName, bool bSlot)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	UWidget* Widget = WidgetBP ? WBPFindWidget(WidgetBP, WidgetName, Error) : nullptr;
	if (!Widget)
	{
		return WBPFail(Error);
	}
	UObject* Target = bSlot ? static_cast<UObject*>(Widget->Slot) : Widget;
	if (!Target)
	{
		return WBPFail(FString::Printf(TEXT("Widget has no slot (it is the root): %s"), *WidgetName));
	}
	return AgentJson::Object({
		AgentJson::Pair(TEXT("name"), WidgetName),
		AgentJson::Pair(TEXT("type"), Target->GetClass()->GetName()),
		AgentJson::PairRaw(TEXT("properties"), WBPPropertiesJson(Target))});
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetBlueprintVariables(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	if (!WidgetBP)
	{
		return WBPFail(Error);
	}
	TArray<FString> Items;
	for (const FBPVariableDescription& Var : WidgetBP->NewVariables)
	{
		Items.Add(WBPPinTypeJson(Var.VarType, {
			AgentJson::Pair(TEXT("name"), Var.VarName.ToString()),
			AgentJson::PairBool(TEXT("is_array"), Var.VarType.IsArray()),
			AgentJson::PairBool(TEXT("is_set"), Var.VarType.IsSet()),
			AgentJson::PairBool(TEXT("is_map"), Var.VarType.IsMap()),
			AgentJson::PairBool(TEXT("instance_editable"), (Var.PropertyFlags & CPF_DisableEditOnInstance) == 0 && (Var.PropertyFlags & CPF_Edit) != 0),
			AgentJson::PairBool(TEXT("blueprint_read_only"), (Var.PropertyFlags & CPF_BlueprintReadOnly) != 0),
			AgentJson::Pair(TEXT("category"), Var.Category.ToString()),
			AgentJson::Pair(TEXT("default_value"), Var.DefaultValue)}));
	}
	return AgentJson::Array(Items);
}

static FString WBPTracksJson(const TArray<UMovieSceneTrack*>& Tracks)
{
	TArray<FString> Items;
	for (const UMovieSceneTrack* Track : Tracks)
	{
		if (Track)
		{
			Items.Add(AgentJson::Object({AgentJson::Pair(TEXT("track_name"), Track->GetTrackName().ToString()), AgentJson::Pair(TEXT("track_type"), Track->GetClass()->GetName())}));
		}
	}
	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetWidgetAnimations(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	if (!WidgetBP)
	{
		return WBPFail(Error);
	}
	TArray<FString> Items;
	for (UWidgetAnimation* Anim : WidgetBP->Animations)
	{
		UMovieScene* Scene = Anim ? Anim->GetMovieScene() : nullptr;
		if (!Scene)
		{
			continue;
		}
		const TRange<FFrameNumber> Range = Scene->GetPlaybackRange();
		const double Duration = Scene->GetTickResolution().AsSeconds(FFrameTime(Range.GetUpperBoundValue() - Range.GetLowerBoundValue()));
		// 动画绑定到控件靠 AnimationBindings.WidgetName（改名时会同步），MovieScene 绑定名只是显示用
		TArray<FString> Bindings;
		for (const FWidgetAnimationBinding& AnimBinding : Anim->AnimationBindings)
		{
			const FMovieSceneBinding* Binding = Scene->FindBinding(AnimBinding.AnimationGuid);
			Bindings.Add(AgentJson::Object({
				AgentJson::Pair(TEXT("widget_name"), AnimBinding.WidgetName.ToString()),
				AgentJson::Pair(TEXT("slot_widget_name"), AnimBinding.SlotWidgetName.IsNone() ? FString() : AnimBinding.SlotWidgetName.ToString()),
				AgentJson::Pair(TEXT("name"), Binding ? Binding->GetName() : FString()),
				AgentJson::PairRaw(TEXT("tracks"), Binding ? WBPTracksJson(Binding->GetTracks()) : TEXT("[]"))}));
		}
		Items.Add(AgentJson::Object({
			AgentJson::Pair(TEXT("name"), Anim->GetName()),
			AgentJson::PairFloat(TEXT("duration"), static_cast<float>(Duration)),
			AgentJson::PairRaw(TEXT("bindings"), AgentJson::Array(Bindings)),
			AgentJson::PairRaw(TEXT("master_tracks"), WBPTracksJson(Scene->GetTracks()))}));
	}
	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetPropertyBindings(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	if (!WidgetBP)
	{
		return WBPFail(Error);
	}
	TArray<FString> Items;
	for (const FDelegateEditorBinding& Binding : WidgetBP->Bindings)
	{
		Items.Add(AgentJson::Object({
			AgentJson::Pair(TEXT("widget_name"), Binding.ObjectName),
			AgentJson::Pair(TEXT("property_name"), Binding.PropertyName.ToString()),
			AgentJson::Pair(TEXT("function_name"), Binding.FunctionName.ToString()),
			AgentJson::Pair(TEXT("source_property"), Binding.SourceProperty.ToString()),
			AgentJson::Pair(TEXT("kind"), UEnum::GetValueAsString(Binding.Kind))}));
	}
	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetNamedSlotBindings(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	if (!WidgetBP)
	{
		return WBPFail(Error);
	}
	TArray<FString> Items;
	for (const TPair<FName, TObjectPtr<UWidget>>& Binding : WidgetBP->WidgetTree->NamedSlotBindings)
	{
		const UWidget* Content = Binding.Value;
		Items.Add(AgentJson::Object({
			AgentJson::Pair(TEXT("name"), Binding.Key.ToString()),
			AgentJson::Pair(TEXT("content_name"), Content ? Content->GetName() : FString()),
			AgentJson::Pair(TEXT("content_type"), Content ? Content->GetClass()->GetName() : FString())}));
	}
	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetAllGraphs(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	if (!WidgetBP)
	{
		return WBPFail(Error);
	}
	TArray<UEdGraph*> Graphs;
	WidgetBP->GetAllGraphs(Graphs);
	TArray<FString> Items;
	for (UEdGraph* Graph : Graphs)
	{
		if (Graph)
		{
			Items.Add(AgentJson::Object({
				AgentJson::Pair(TEXT("name"), Graph->GetName()),
				AgentJson::Pair(TEXT("type"), WBPGraphType(WidgetBP, Graph)),
				AgentJson::PairInt(TEXT("node_count"), Graph->Nodes.Num())}));
		}
	}
	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetGraphNodes(const FString& AssetPath, const FString& GraphName, bool bDetailed)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	if (!WidgetBP)
	{
		return WBPFail(Error);
	}
	TArray<UEdGraph*> Graphs;
	WidgetBP->GetAllGraphs(Graphs);
	UEdGraph* const* Found = Graphs.FindByPredicate([&](const UEdGraph* Graph) { return Graph && Graph->GetName() == GraphName; });
	if (!Found)
	{
		return WBPFail(FString::Printf(TEXT("Graph not found: %s"), *GraphName));
	}
	TArray<FString> Items;
	for (UEdGraphNode* Node : (*Found)->Nodes)
	{
		if (Node)
		{
			Items.Add(WBPNodeJson(Node, bDetailed));
		}
	}
	return AgentJson::Array(Items);
}

FString UAgentWidgetBlueprintInfoFunctionLib::GetBlueprintFunctions(const FString& AssetPath)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	if (!WidgetBP)
	{
		return WBPFail(Error);
	}
	TArray<FString> Items;
	for (UEdGraph* Graph : WidgetBP->FunctionGraphs)
	{
		if (!Graph)
		{
			continue;
		}
		UK2Node_FunctionEntry* Entry = WBPFindEntry(Graph);
		Items.Add(AgentJson::Object({
			AgentJson::Pair(TEXT("name"), Graph->GetName()),
			AgentJson::Pair(TEXT("description"), Entry ? Entry->MetaData.ToolTip.ToString() : FString()),
			AgentJson::PairInt(TEXT("node_count"), Graph->Nodes.Num()),
			AgentJson::PairRaw(TEXT("inputs"), WBPParamsJson(Entry, EGPD_Output)),
			AgentJson::PairRaw(TEXT("outputs"), WBPParamsJson(WBPFindResult(Graph), EGPD_Input))}));
	}
	return AgentJson::Array(Items);
}

// ==================== 写入 ====================

FString UAgentWidgetBlueprintInfoFunctionLib::ShiftChild(const FString& AssetPath, const FString& WidgetName, int32 Index)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	UWidget* Widget = WidgetBP ? WBPFindWidget(WidgetBP, WidgetName, Error) : nullptr;
	if (!Widget)
	{
		return WBPFail(Error);
	}
	UPanelWidget* Parent = Widget->GetParent();
	if (!Parent || Index < 0 || Index >= Parent->GetChildrenCount())
	{
		return WBPFail(TEXT("Child needs a panel parent and an index within its existing children"));
	}
	WidgetBP->Modify();
	Parent->Modify();
	Parent->ShiftChild(Index, Widget);
	if (Parent->GetChildIndex(Widget) != Index)
	{
		return WBPFail(TEXT("ShiftChild did not produce the requested index"));
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WidgetBP);
	return WBPOk(FString(), {AgentJson::PairInt(TEXT("index"), Index)});
}

FString UAgentWidgetBlueprintInfoFunctionLib::RenameChildWidget(const FString& AssetPath, const FString& OldWidgetName, const FString& NewWidgetName)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	UWidget* Widget = WidgetBP ? WBPFindWidget(WidgetBP, OldWidgetName, Error) : nullptr;
	if (!Widget)
	{
		return WBPFail(Error);
	}
	const FName OldName(*OldWidgetName);
	const FName NewName(*NewWidgetName);
	// 名字校验器只管变量、函数等成员名，不管 WidgetTree 里没勾"是变量"的控件；撞上同名对象时 Rename 会直接 fatal，所以先自己查
	if (NewWidgetName.IsEmpty() || !FName::IsValidXName(NewWidgetName, INVALID_OBJECTNAME_CHARACTERS TEXT(" ")) || FChar::IsDigit(NewWidgetName[0]))
	{
		return WBPFail(FString::Printf(TEXT("Invalid widget name '%s': use letters, digits and _, not starting with a digit"), *NewWidgetName));
	}
	if (WidgetBP->WidgetTree->FindWidget(NewName) || !Widget->Rename(*NewWidgetName, nullptr, REN_Test))
	{
		return WBPFail(FString::Printf(TEXT("Name already used in WidgetTree: %s"), *NewWidgetName));
	}
	// 与设计器同一套校验：不与其它控件变量、成员变量、函数重名，名字本身合法
	FKismetNameValidator Validator(WidgetBP, OldName);
	const EValidatorResult Valid = Validator.IsValid(NewName);
	if (Valid != EValidatorResult::Ok)
	{
		return WBPFail(FString::Printf(TEXT("Invalid new name '%s': %s"), *NewWidgetName, *INameValidatorInterface::GetErrorString(NewWidgetName, Valid)));
	}

	// 以下与 FWidgetBlueprintEditorUtils::RenameWidget 一致，只是不依赖打开的蓝图编辑器（没有预览控件要同步）
	WidgetBP->Modify();
	Widget->Modify();
	Widget->SetDisplayLabel(NewWidgetName);
	Widget->Rename(*NewWidgetName, nullptr, REN_DontCreateRedirectors);
	FBlueprintEditorUtils::ReplaceVariableReferences(WidgetBP, OldName, NewName);
	for (FDelegateEditorBinding& Binding : WidgetBP->Bindings)
	{
		if (Binding.ObjectName == OldWidgetName)
		{
			Binding.ObjectName = NewWidgetName;
		}
	}
	for (UWidgetAnimation* Anim : WidgetBP->Animations)
	{
		if (!Anim)
		{
			continue;
		}
		for (FWidgetAnimationBinding& AnimBinding : Anim->AnimationBindings)
		{
			if (AnimBinding.WidgetName != OldName)
			{
				continue;
			}
			AnimBinding.WidgetName = NewName;
			Anim->MovieScene->Modify();
			if (AnimBinding.SlotWidgetName == NAME_None)
			{
				if (FMovieScenePossessable* Possessable = Anim->MovieScene->FindPossessable(AnimBinding.AnimationGuid))
				{
					Possessable->SetName(NewWidgetName);
				}
			}
		}
	}
	WidgetBP->WidgetTree->ForEachWidget([&](UWidget* Each)
	{
		if (Each->Navigation)
		{
			Each->Navigation->SetFlags(RF_Transactional);
			Each->Navigation->Modify();
			Each->Navigation->TryToRenameBinding(OldName, NewName);
		}
	});
	FBlueprintEditorUtils::ValidateBlueprintChildVariables(WidgetBP, NewName);
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WidgetBP);
	return WBPOk(FString::Printf(TEXT("Renamed '%s' to '%s'"), *OldWidgetName, *NewWidgetName));
}

FString UAgentWidgetBlueprintInfoFunctionLib::SetWidgetProperty(const FString& AssetPath, const FString& WidgetName, const FString& PropertyName, const FString& PropertyValue, bool bSlot)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	UWidget* Widget = WidgetBP ? WBPFindWidget(WidgetBP, WidgetName, Error) : nullptr;
	if (!Widget)
	{
		return WBPFail(Error);
	}
	UObject* Target = bSlot ? static_cast<UObject*>(Widget->Slot) : Widget;
	if (!Target)
	{
		return WBPFail(FString::Printf(TEXT("Widget has no slot (it is the root): %s"), *WidgetName));
	}
	FProperty* Prop = FindFProperty<FProperty>(Target->GetClass(), *PropertyName);
	if (!Prop)
	{
		return WBPFail(FString::Printf(TEXT("Property '%s' not found on %s"), *PropertyName, *Target->GetClass()->GetName()));
	}
	void* ValuePtr = Prop->ContainerPtrToValuePtr<void>(Target);
	Target->Modify();
	Target->PreEditChange(Prop);
	const TCHAR* Parsed = Prop->ImportText_Direct(*PropertyValue, ValuePtr, Target, PPF_None);
	FPropertyChangedEvent ChangedEvent(Prop, EPropertyChangeType::ValueSet);
	Target->PostEditChangeProperty(ChangedEvent);
	if (!Parsed)
	{
		return WBPFail(FString::Printf(TEXT("Cannot parse '%s' as %s (%s)"), *PropertyValue, *Prop->GetCPPType(), *PropertyName));
	}
	// 改变是否为变量会增删生成类的成员，按结构性修改处理
	if (Prop->GetFName() == GET_MEMBER_NAME_CHECKED(UWidget, bIsVariable))
	{
		FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WidgetBP);
	}
	else
	{
		FBlueprintEditorUtils::MarkBlueprintAsModified(WidgetBP);
	}
	FString Value;
	Prop->ExportTextItem_Direct(Value, ValuePtr, nullptr, Target, PPF_None);
	return WBPOk(FString::Printf(TEXT("%s set"), *PropertyName), {AgentJson::Pair(TEXT("value"), Value)});
}

FString UAgentWidgetBlueprintInfoFunctionLib::AddFunctionParam(const FString& AssetPath, const FString& FunctionName, const FString& ParamName, const FEdGraphPinType& PinType, bool bOutput)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	UEdGraph* Graph = WidgetBP ? WBPFindFunction(WidgetBP, FunctionName, Error) : nullptr;
	if (!Graph)
	{
		return WBPFail(Error);
	}
	UK2Node_FunctionEntry* Entry = WBPFindEntry(Graph);
	if (!Entry)
	{
		return WBPFail(TEXT("Function entry node not found"));
	}
	UK2Node_EditablePinBase* Node = bOutput ? static_cast<UK2Node_EditablePinBase*>(FBlueprintEditorUtils::FindOrCreateFunctionResultNode(Entry)) : Entry;
	if (!Node)
	{
		return WBPFail(TEXT("Function result node not found and could not be created"));
	}
	const FName PinName(*ParamName);
	// UserDefinedPinExists 没有导出，直接查 UserDefinedPins
	const bool bExists = Node->UserDefinedPins.ContainsByPredicate([&](const TSharedPtr<FUserPinInfo>& Info) { return Info.IsValid() && Info->PinName == PinName; });
	if (bExists)
	{
		return WBPFail(FString::Printf(TEXT("Parameter already exists: %s"), *ParamName));
	}
	Node->Modify();
	if (!Node->CreateUserDefinedPin(PinName, PinType, bOutput ? EGPD_Input : EGPD_Output))
	{
		return WBPFail(FString::Printf(TEXT("Failed to create parameter: %s"), *ParamName));
	}
	FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(WidgetBP);
	return WBPOk(FString::Printf(TEXT("%s '%s' added to %s"), bOutput ? TEXT("Output") : TEXT("Input"), *ParamName, *FunctionName),
		{AgentJson::PairRaw(TEXT("param"), WBPPinTypeJson(PinType, {AgentJson::Pair(TEXT("name"), ParamName)}))});
}

FString UAgentWidgetBlueprintInfoFunctionLib::SetFunctionDescription(const FString& AssetPath, const FString& FunctionName, const FString& Description)
{
	FString Error;
	UWidgetBlueprint* WidgetBP = WBPLoad(AssetPath, Error);
	UEdGraph* Graph = WidgetBP ? WBPFindFunction(WidgetBP, FunctionName, Error) : nullptr;
	if (!Graph)
	{
		return WBPFail(Error);
	}
	UK2Node_FunctionEntry* Entry = WBPFindEntry(Graph);
	if (!Entry)
	{
		return WBPFail(TEXT("Function entry node not found"));
	}
	Entry->Modify();
	Entry->MetaData.ToolTip = FText::FromString(Description);
	FBlueprintEditorUtils::MarkBlueprintAsModified(WidgetBP);
	return WBPOk(FString::Printf(TEXT("Description set for %s"), *FunctionName));
}
