#pragma once

#include "genericFpga.h"
#include <llvm/MC/TargetRegistry.h>

llvm::Target& getTheGenericFpgaTarget();
