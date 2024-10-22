#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {
/*
 * Lower HFloatTmp constants and intrinsic functions to specialized functions for specific float type.
 * * this also transforms type of all variables between hwtHls.castToHFloatTmp/hwtHls.castFromHFloatTmp
 * * hwtHls.castToHFloatTmp /hwtHls.castFromHFloatTmp are removed
 * */
class HFloatTmpLoweringPass: public llvm::PassInfoMixin<HFloatTmpLoweringPass> {

public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
