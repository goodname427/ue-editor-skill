#pragma once

#include "CoreMinimal.h"

/**
 * Agent 工具库共用的 JSON 拼装辅助
 * 各工具函数以 JSON 字符串返回结果，供 Agent 通过 Python Remote Execution 解析。
 */
namespace AgentJson
{
	/** 转义 JSON 字符串内容（不含两侧引号） */
	AGENTTOOLSCOMMON_API FString EscapeString(const FString& Input);

	/** "Key":"Value"（Value 会转义） */
	AGENTTOOLSCOMMON_API FString Pair(const FString& Key, const FString& Value);

	/** "Key":Value（Value 为已拼好的 JSON） */
	AGENTTOOLSCOMMON_API FString PairRaw(const FString& Key, const FString& Value);

	AGENTTOOLSCOMMON_API FString PairBool(const FString& Key, bool Value);

	AGENTTOOLSCOMMON_API FString PairInt(const FString& Key, int32 Value);

	AGENTTOOLSCOMMON_API FString PairFloat(const FString& Key, float Value);

	/** {Pair1,Pair2,...} */
	AGENTTOOLSCOMMON_API FString Object(const TArray<FString>& Pairs);

	/** [Item1,Item2,...]（Item 为已拼好的 JSON） */
	AGENTTOOLSCOMMON_API FString Array(const TArray<FString>& Items);
}
