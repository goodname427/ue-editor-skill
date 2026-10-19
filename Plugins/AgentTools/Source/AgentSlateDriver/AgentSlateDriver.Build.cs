using UnrealBuildTool;

public class AgentSlateDriver : ModuleRules
{
	public AgentSlateDriver(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(
			new string[]
			{
				"Core",
				"CoreUObject",
				"Engine",
			}
		);

		PrivateDependencyModuleNames.AddRange(
			new string[]
			{
				"ApplicationCore",
				"InputCore",
				"Slate",
				"SlateCore",
				"AgentToolsCommon",
			}
		);
	}
}
