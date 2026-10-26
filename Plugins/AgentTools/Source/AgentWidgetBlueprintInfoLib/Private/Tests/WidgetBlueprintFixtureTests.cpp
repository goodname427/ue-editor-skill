#if WITH_DEV_AUTOMATION_TESTS

#include "Blueprint/WidgetTree.h"
#include "Components/CanvasPanel.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Misc/AutomationTest.h"
#include "WidgetBlueprint.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FWBPPrepareFixtureTest, "AgentTools.WBP.PrepareFixture", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FWBPPrepareFixtureTest::RunTest(const FString& Parameters)
{
	UWidgetBlueprint* Blueprint = LoadObject<UWidgetBlueprint>(nullptr, TEXT("/Game/__AgentToolsTests/IssuesFixture.IssuesFixture"));
	if (!TestNotNull(TEXT("Explicitly created test fixture exists"), Blueprint)
		|| !TestNotNull(TEXT("Fixture has a widget tree"), Blueprint->WidgetTree.Get()))
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
