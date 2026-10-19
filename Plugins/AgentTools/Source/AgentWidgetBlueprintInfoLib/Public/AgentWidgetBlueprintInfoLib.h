#pragma once

#include "Modules/ModuleManager.h"

class FAgentWidgetBlueprintInfoLibModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
};
