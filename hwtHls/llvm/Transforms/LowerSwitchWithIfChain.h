#pragma once

#include <llvm/IR/PassManager.h>

namespace llvm {
class Function;
}

namespace hwtHls {

//===----------------------------------------------------------------------===//
//
// Simplified version of LowerSwitch which does not use pivoting and constructs linear chain
// of case blocks instead (which is then more simple to reduce in vreg-if-converter)
//===----------------------------------------------------------------------===//
class LowerSwitchWithIfChain: public llvm::PassInfoMixin<LowerSwitchWithIfChain> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
