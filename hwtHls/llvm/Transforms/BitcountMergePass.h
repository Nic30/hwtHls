#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>

namespace hwtHls {

/*
 * Discover all bitcounts (ctlz/cttz/ctpop) which are operating on some overlapping bits
 * and rewrite them to use the most wide bitcount instructions. To reduce total number
 * of bitcount instructions.
 * */
class BitcountMergePass: public llvm::PassInfoMixin<BitcountMergePass> {
public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
