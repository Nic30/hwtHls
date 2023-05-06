#pragma once

#include "hwtFpga.h"
#include <llvm/MC/TargetRegistry.h>

llvm::Target& getTheHwtFpgaTarget();
