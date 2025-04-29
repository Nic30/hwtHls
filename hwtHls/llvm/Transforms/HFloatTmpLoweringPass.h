#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {
/*
 * Lower HFloatTmp constants and intrinsic functions to specialized functions for specific float type.
 * * this also transforms type of all variables between hwtHls.fp.castToHFloatTmp/hwtHls.fp.castFromHFloatTmp
 * * hwtHls.fp.castToHFloatTmp /hwtHls.fp.castFromHFloatTmp are removed
 * */
class HFloatTmpLoweringPass: public llvm::PassInfoMixin<HFloatTmpLoweringPass> {

public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
