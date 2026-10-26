#if WITH_DEV_AUTOMATION_TESTS

#include "Misc/AutomationTest.h"
#include "SlateClippingGeometry.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSDClippingGeometryTest, "AgentTools.Slate.ClippingGeometry", EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FSDClippingGeometryTest::RunTest(const FString& Parameters)
{
	FSlateClippingState State;
	State.StencilQuads.Add(FSlateClippingZone(FVector2D(0, 50), FVector2D(50, 0), FVector2D(50, 100), FVector2D(100, 50)));
	TestEqual(TEXT("AABB overlap outside a diamond has no visible polygon"), SDVisiblePolygon(FSlateClippingZone(FSlateRect(0, 0, 10, 10)), State).Num(), 0);
	const TArray<FVector2D> Partial = SDVisiblePolygon(FSlateClippingZone(FSlateRect(0, 0, 40, 40)), State);
	TestTrue(TEXT("Partial intersection exists"), Partial.Num() >= 3);
	FVector2D Center = FVector2D::ZeroVector;
	for (const FVector2D& Point : Partial)
	{
		Center += Point;
	}
	if (Partial.Num() > 0)
	{
		TestTrue(TEXT("Vertex centroid stays inside the stencil"), State.IsPointInside(Center / Partial.Num()));
	}
	TestEqual(TEXT("Touching a corner is not positive area"), SDVisiblePolygon(FSlateClippingZone(FSlateRect(0, 0, 25, 25)), State).Num(), 0);
	State.StencilQuads.Add(FSlateClippingZone(FSlateRect(0, 0, 20, 20)));
	TestEqual(TEXT("Each stencil quad participates in intersection"), SDVisiblePolygon(FSlateClippingZone(FSlateRect(0, 0, 100, 100)), State).Num(), 0);
	FSlateClippingState Scissor;
	Scissor.ScissorRect = FSlateClippingZone(FSlateRect(-100, 20, 0, 60));
	const TArray<FVector2D> AxisAligned = SDVisiblePolygon(FSlateClippingZone(FSlateRect(-80, 50, -20, 90)), Scissor);
	TestEqual(TEXT("Axis-aligned clipping remains a rectangle"), AxisAligned.Num(), 4);
	for (const FVector2D& Point : AxisAligned)
	{
		TestTrue(TEXT("Axis-aligned vertices remain inside clip"), Point.Y <= 60);
	}
	const FSlateClippingZone Mirrored(FVector2D(10, 0), FVector2D(0, 0), FVector2D(10, 10), FVector2D(0, 10));
	TestEqual(TEXT("Mirrored winding remains valid"), SDVisiblePolygon(Mirrored, TOptional<FSlateClippingState>()).Num(), 4);
	TestEqual(TEXT("Degenerate widget is invisible"), SDVisiblePolygon(FSlateClippingZone(FSlateRect(0, 0, 0, 10)), TOptional<FSlateClippingState>()).Num(), 0);
	return true;
}

#endif
