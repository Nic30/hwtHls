#pragma once

#include <llvm/IR/Function.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Analysis/AliasAnalysis.h>
#include <llvm/Analysis/BasicAliasAnalysis.h>
#include <llvm/Analysis/GlobalsModRef.h>

namespace hwtHls {
/**
 * [fixme] rename to SlicedParallelPathMerge
 * In trivial cases this pass does concatentation hoisting and merging the bitwise instructions
 * if they are used only by same concatenation.
 * However this also supports loops with PHIs, recognizes shifts using PHIs and others extra things.
 * The actual merging condition is more general and can be found in functions called from run().
 * */
class SlicesMergePass: public llvm::PassInfoMixin<SlicesMergePass> {

public:
	llvm::PreservedAnalyses run(llvm::Function &F,
			llvm::FunctionAnalysisManager &AM);
};

}
