#pragma once
#include <llvm/PassRegistry.h>

namespace hwtHls {
extern char &EarlyMachineCopyPropagationID;
}
namespace llvm {
void initializeEarlyMachineCopyPropagationPass(PassRegistry&);
}
