#include "AgentJson.h"

namespace AgentJson
{
	FString EscapeString(const FString& Input)
	{
		FString Output;
		Output.Reserve(Input.Len());
		for (const TCHAR Character : Input)
		{
			switch (Character)
			{
			case TEXT('\\'): Output += TEXT("\\\\"); break;
			case TEXT('"'): Output += TEXT("\\\""); break;
			case TEXT('\n'): Output += TEXT("\\n"); break;
			case TEXT('\r'): Output += TEXT("\\r"); break;
			case TEXT('\t'): Output += TEXT("\\t"); break;
			default:
				if (Character < 0x20)
				{
					Output += FString::Printf(TEXT("\\u%04x"), static_cast<uint32>(Character));
				}
				else
				{
					Output.AppendChar(Character);
				}
				break;
			}
		}
		return Output;
	}

	FString Pair(const FString& Key, const FString& Value)
	{
		return FString::Printf(TEXT("\"%s\":\"%s\""), *Key, *EscapeString(Value));
	}

	FString PairRaw(const FString& Key, const FString& Value)
	{
		return FString::Printf(TEXT("\"%s\":%s"), *Key, *Value);
	}

	FString PairBool(const FString& Key, bool Value)
	{
		return FString::Printf(TEXT("\"%s\":%s"), *Key, Value ? TEXT("true") : TEXT("false"));
	}

	FString PairInt(const FString& Key, int32 Value)
	{
		return FString::Printf(TEXT("\"%s\":%d"), *Key, Value);
	}

	FString PairFloat(const FString& Key, float Value)
	{
		return FString::Printf(TEXT("\"%s\":%.4f"), *Key, Value);
	}

	FString Object(const TArray<FString>& Pairs)
	{
		return TEXT("{") + FString::Join(Pairs, TEXT(",")) + TEXT("}");
	}

	FString Array(const TArray<FString>& Items)
	{
		return TEXT("[") + FString::Join(Items, TEXT(",")) + TEXT("]");
	}
}
