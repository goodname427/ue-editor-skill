#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"
#include "Tests/AutomationCommon.h"
#include "AgentSlateDriverFunctionLib.h"
#include "AgentJson.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SWindow.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Text/STextBlock.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSDRootMatchIndexTest, "AgentTools.Slate.RootMatchIndex", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

struct FSDRootMatchIndexFixture
{
	TSharedPtr<SWindow> Window;
};

DEFINE_LATENT_AUTOMATION_COMMAND_TWO_PARAMETER(FSDCheckRootMatchIndex, FAutomationTestBase*, Test, TSharedPtr<FSDRootMatchIndexFixture>, Fixture);

bool FSDCheckRootMatchIndex::Update()
{
	const FString Locator = TEXT("tag=AgentToolsRootMatchIndex");
	const FString WindowFilter = TEXT("AgentTools Root Match Index Fixture");
	const FString Found = UAgentSlateDriverFunctionLib::FindWidgets(Locator, WindowFilter);
	const FString TagField = AgentJson::Pair(TEXT("tag"), TEXT("AgentToolsRootMatchIndex"));
	Test->TestEqual(TEXT("Fully clipped first root is excluded from visible matches"), Found.Len() - Found.Replace(*TagField, TEXT("")).Len(), TagField.Len());

	const FString Dump = UAgentSlateDriverFunctionLib::DumpSlateTree(WindowFilter, Locator, 4, false, false, 50, 0);
	Test->TestTrue(TEXT("Tree and find count the same visible roots"), Dump.Contains(AgentJson::PairInt(TEXT("root_match_count"), 1)));
	Test->TestTrue(TEXT("Index zero exports the visible second root"), Dump.Contains(TEXT("visible-root")));
	Test->TestFalse(TEXT("Index zero does not export the fully clipped first root"), Dump.Contains(TEXT("clipped-root")));

	FSlateApplication::Get().RequestDestroyWindow(Fixture->Window.ToSharedRef());
	Fixture->Window.Reset();
	return true;
}

bool FSDRootMatchIndexTest::RunTest(const FString& Parameters)
{
	TSharedPtr<FSDRootMatchIndexFixture> Fixture = MakeShared<FSDRootMatchIndexFixture>();
	Fixture->Window = SNew(SWindow)
		.Title(FText::FromString(TEXT("AgentTools Root Match Index Fixture")))
		.ClientSize(FVector2D(400, 200))
		.SupportsMaximize(false)
		.SupportsMinimize(false)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(SBox).HeightOverride(60).Clipping(EWidgetClipping::ClipToBoundsAlways)
				[
					SNew(SScrollBox)
					+ SScrollBox::Slot()
					[
						SNew(SBox).HeightOverride(200)
					]
					+ SScrollBox::Slot()
					[
						SNew(SBorder).Tag(FName(TEXT("AgentToolsRootMatchIndex")))
						[
							SNew(STextBlock).Text(FText::FromString(TEXT("clipped-root")))
						]
					]
				]
			]
			+ SVerticalBox::Slot().AutoHeight()
			[
				SNew(SBorder).Tag(FName(TEXT("AgentToolsRootMatchIndex")))
				[
					SNew(STextBlock).Text(FText::FromString(TEXT("visible-root")))
				]
			]
		];
	FSlateApplication::Get().AddWindow(Fixture->Window.ToSharedRef());
	ADD_LATENT_AUTOMATION_COMMAND(FWaitLatentCommand(0.2f));
	ADD_LATENT_AUTOMATION_COMMAND(FSDCheckRootMatchIndex(this, Fixture));
	return true;
}

#endif
