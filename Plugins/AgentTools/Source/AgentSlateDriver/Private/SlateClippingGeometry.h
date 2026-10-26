#pragma once

#include "CoreMinimal.h"
#include "Layout/Clipping.h"

inline TArray<FVector2D> SDClipPolygon(TArray<FVector2D> Polygon, const FSlateClippingZone& Zone)
{
	const FVector2D Corners[] = {FVector2D(Zone.TopLeft), FVector2D(Zone.TopRight), FVector2D(Zone.BottomRight), FVector2D(Zone.BottomLeft)};
	const FVector2D Center = (Corners[0] + Corners[1] + Corners[2] + Corners[3]) * 0.25;
	for (int32 Edge = 0; Edge < 4 && Polygon.Num() > 0; ++Edge)
	{
		const FVector2D A = Corners[Edge], Direction = Corners[(Edge + 1) % 4] - A;
		const double Side = FVector2D::CrossProduct(Direction, Center - A);
		if (FMath::IsNearlyZero(Side, 1.e-8))
		{
			return {};
		}
		const double Sign = Side > 0 ? 1.0 : -1.0;
		auto Distance = [&](const FVector2D& Point) { return Sign * FVector2D::CrossProduct(Direction, Point - A); };
		TArray<FVector2D> Result;
		FVector2D Previous = Polygon.Last();
		double PreviousDistance = Distance(Previous);
		for (const FVector2D& Point : Polygon)
		{
			const double CurrentDistance = Distance(Point);
			if ((PreviousDistance >= 0) != (CurrentDistance >= 0))
			{
				Result.Add(Previous + (Point - Previous) * (PreviousDistance / (PreviousDistance - CurrentDistance)));
			}
			if (CurrentDistance >= 0)
			{
				Result.Add(Point);
			}
			Previous = Point;
			PreviousDistance = CurrentDistance;
		}
		Polygon = MoveTemp(Result);
	}
	return Polygon;
}

inline TArray<FVector2D> SDVisiblePolygon(const FSlateClippingZone& WidgetZone, const TOptional<FSlateClippingState>& State)
{
	TArray<FVector2D> Polygon = {FVector2D(WidgetZone.TopLeft), FVector2D(WidgetZone.TopRight), FVector2D(WidgetZone.BottomRight), FVector2D(WidgetZone.BottomLeft)};
	if (State.IsSet())
	{
		if (State->ScissorRect.IsSet())
		{
			Polygon = SDClipPolygon(MoveTemp(Polygon), State->ScissorRect.GetValue());
		}
		else
		{
			for (const FSlateClippingZone& Zone : State->StencilQuads)
			{
				Polygon = SDClipPolygon(MoveTemp(Polygon), Zone);
			}
		}
	}
	if (Polygon.Num() < 3)
	{
		return {};
	}
	double Area = 0;
	const FVector2D Origin = Polygon[0];
	for (int32 Index = 1; Index + 1 < Polygon.Num(); ++Index)
	{
		Area += FVector2D::CrossProduct(Polygon[Index] - Origin, Polygon[Index + 1] - Origin);
	}
	return FMath::Abs(Area) > 1.e-6 ? Polygon : TArray<FVector2D>();
}
