#pragma once

#include <hwtHls/llvm/targets/hwtFpga.h>
#include <llvm/MC/TargetRegistry.h>

llvm::Target& getTheHwtFpgaTarget();
