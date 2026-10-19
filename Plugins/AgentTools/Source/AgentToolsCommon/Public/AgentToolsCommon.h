#pragma once

#include "Modules/ModuleManager.h"

class FAgentToolsCommonModule : public IModuleInterface
{
public:
	virtual void StartupModule() override;
	virtual void ShutdownModule() override;
};
