using UnrealBuildTool;

public class AgentWidgetBlueprintInfoLib : ModuleRules
{
	public AgentWidgetBlueprintInfoLib(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine",
				"UMG",
				"UMGEditor",
			}
		);

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"Slate",
				"SlateCore",
				"UnrealEd",
				"BlueprintGraph",
				"Kismet",
				"MovieScene",
				"AgentToolsCommon",
			}
		);
	}
}
