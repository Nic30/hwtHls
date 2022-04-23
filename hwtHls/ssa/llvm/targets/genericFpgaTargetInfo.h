#pragma once

#include <llvm/Support/TargetRegistry.h>
#include "genericFpga.h"

llvm::Target& getTheGenericFpgaTarget();
