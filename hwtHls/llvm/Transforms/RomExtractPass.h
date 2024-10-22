#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/**
 *  A pass to rewrite ROMs hardcoded in select tree as a load from GlobalVariable
 *
 *  %c0 = icmp eq i2 %index, 0
 *  %c1 = icmp eq i2 %index, 1
 *  %c2 = icmp eq i2 %index, -2
 *  %v0 = select i1 %c2, i2 1, i2 -2
 *  %v1 = select i1 %c1, i2 1, i2 %v0
 *  %v2 = select i1 %c0, i2 0, i2 %v1
 *
 *  to
 *
 *  @0 = private unnamed_addr constant [4 x i2] [i2 0, i2 1, i2 1, i2 -2], align 1
 *  %addr = getelementptr inbounds [4 x i2], ptr @0, i2 0, i2 %index
 *  %v2 = load volatile i2, ptr %addr, align 1
 *
 *  :note: This should be run before InstrCombine because it can make search for %index and values much harder
 */
class RomExtractPass: public llvm::PassInfoMixin<RomExtractPass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
